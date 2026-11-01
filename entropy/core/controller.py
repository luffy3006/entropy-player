"""Interface-independent player state and commands."""

from __future__ import annotations

import logging
import random
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any

from entropy.core.audio import AudioBackend, AudioEngine, normalize_end_reason
from entropy.core.database import LibraryDatabase
from entropy.core.preferences import load_volume, save_volume
from entropy.core.scheduler import EntropyScheduler, track_weight, weight_percentages
from entropy.core.watcher import LibraryWatcher

logger = logging.getLogger(__name__)


class PlayerController:
    MAX_CONSECUTIVE_AUDIO_ERRORS = 3
    VOLUME_SAVE_DELAY = 0.4

    def __init__(self, database: LibraryDatabase | None = None, audio: AudioBackend | None = None,
                 watcher: LibraryWatcher | None = None) -> None:
        self.database = database or LibraryDatabase()
        self.scheduler = EntropyScheduler()
        self.shuffle_mode = "entropy"
        self.current_id: int | None = None
        self._forced_next: int | None = None
        self._queued_id: int | None = None
        self._queued_history_index: int | None = None
        self._session_history: list[int] = []
        self._session_history_index = -1
        self._recent_ids: deque[int] = deque(reversed(self.database.recent_played_track_ids()), maxlen=12)
        self._shuffle_playlist_id: int | None = None
        self._lock = threading.RLock()
        self._listeners: list[Any] = []
        self.audio: AudioBackend = audio or AudioEngine(self._on_end_file)
        self.mpris_enabled = sys.platform != "win32"
        self.audio.set_end_callback(self._on_end_file)
        self.audio.set_file_loaded_callback(self._on_file_loaded)
        self.audio.volume = load_volume(self.audio.volume)
        self._consecutive_errors = 0
        self._volume_lock = threading.Lock()
        self._volume_timer: threading.Timer | None = None
        self._pending_volume: int | None = None
        self._closed = False
        self._close_lock = threading.Lock()
        self.watcher = watcher or LibraryWatcher(self.database, self._library_changed)
        self.watcher.start()

    def subscribe(self, callback: Any) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in tuple(self._listeners):
            try:
                callback()
            except RuntimeError:
                self._listeners.remove(callback)

    def _library_changed(self) -> None:
        removed_current = False
        with self._lock:
            if self.current_id is not None and self.database.get_track(self.current_id) is None:
                self.current_id = None
                removed_current = True
        if removed_current:
            self.audio.stop()
            self.next_track()
            return
        self._notify()

    def tracks(self, include_excluded: bool = False) -> list[dict[str, Any]]:
        rows = self.database.get_tracks(include_excluded=include_excluded)
        for row in rows:
            row["weight"] = track_weight(row)
        percentages = weight_percentages(rows)
        for row in rows:
            row["weight_percent"] = percentages.get(int(row["id"]), 0.0)
        return rows

    def current_track(self) -> dict[str, Any] | None:
        return self.database.get_track(self.current_id) if self.current_id is not None else None

    def play_track(self, track_id: int) -> None:
        track = self.database.get_track(track_id)
        if track is None or track["is_excluded"]:
            return
        with self._lock:
            self._consecutive_errors = 0
            if self.current_id is not None and self.current_id != track_id:
                self.database.record_skip(self.current_id, self.audio.time_pos)
                self._remember_recent(self.current_id)
            self._start_track(track)
        self._notify()

    def _start_track(self, track: dict[str, Any], history_index: int | None = None) -> None:
        self.current_id = int(track["id"])
        self._queued_id = None
        self._queued_history_index = None
        if history_index is None:
            if self._session_history_index + 1 < len(self._session_history):
                del self._session_history[self._session_history_index + 1:]
            self._session_history.append(self.current_id)
            self._session_history_index = len(self._session_history) - 1
        else:
            self._session_history_index = history_index
        self.audio.play(track["filepath"])
        self._queue_current_successor()

    def play_pause(self) -> None:
        if self.current_id is None:
            self.next_track()
        else:
            self.audio.pause()
            self._notify()

    def set_volume(self, volume: int) -> None:
        value = max(0, min(100, int(volume)))
        with self._volume_lock:
            self.audio.volume = value
            self._pending_volume = value
            if self._volume_timer is not None:
                self._volume_timer.cancel()
            timer = threading.Timer(
                self.VOLUME_SAVE_DELAY,
                lambda: self._flush_pending_volume(timer),
            )
            self._volume_timer = timer
            self._volume_timer.daemon = True
            timer.start()
        self._notify()

    def stop(self) -> None:
        with self._lock:
            self.current_id = None
            self._queued_id = None
            self._queued_history_index = None
            self._consecutive_errors = 0
        self.audio.stop()
        self._notify()

    def next_track(self) -> None:
        self._advance(reset_error_streak=True)

    def _advance(self, reset_error_streak: bool) -> None:
        with self._lock:
            if reset_error_streak:
                self._consecutive_errors = 0
            current_id = self.current_id
            if current_id is not None:
                self.database.record_skip(current_id, self.audio.time_pos)
                self._remember_recent(current_id)
            if self._forced_next is not None:
                chosen_id, self._forced_next = self._forced_next, None
                track = self.database.get_track(chosen_id)
                if track is not None and not track["is_excluded"]:
                    self._start_track(track)
                    self._notify()
                return
            next_entry = self._find_session_history_entry(1)
            if next_entry is not None:
                history_index, track = next_entry
                self._start_track(track, history_index=history_index)
                self._notify()
                return
            tracks = self._shuffle_candidates()
            if not tracks:
                self.current_id = None
                self._notify()
                return
            chosen = self._choose_successor(tracks, current_id)
            if chosen is not None:
                self._start_track(chosen)
                self._notify()

    def previous_track(self) -> None:
        with self._lock:
            self._consecutive_errors = 0
            previous_entry = self._find_session_history_entry(-1)
            if previous_entry is None:
                return
            history_index, track = previous_entry
            if self.current_id is not None and self.current_id != int(track["id"]):
                self.database.record_skip(self.current_id, self.audio.time_pos)
                self._remember_recent(self.current_id)
            self._start_track(track, history_index=history_index)
        self._notify()

    def _find_session_history_entry(self, direction: int) -> tuple[int, dict[str, Any]] | None:
        index = self._session_history_index + direction
        while 0 <= index < len(self._session_history):
            track = self.database.get_track(self._session_history[index])
            if track is not None and not track["is_excluded"]:
                return index, track
            index += direction
        return None

    def force_play_next(self, track_id: int) -> None:
        self._forced_next = track_id
        if self.current_id is None:
            self.next_track()

    def _on_end_file(self, reason: str) -> None:
        reason = normalize_end_reason(reason)
        if reason == "unknown":
            logger.debug("Ignoring unknown mpv end-file reason")
            return
        if reason in {"stop", "quit", "redirect"}:
            return

        if reason == "error":
            with self._lock:
                failed_id = self.current_id
                if failed_id is None:
                    logger.debug("Ignoring mpv playback error without an active track")
                    return
                self._consecutive_errors += 1
                self._remember_recent(failed_id)
                self.current_id = None
                self._queued_id = None
                self._queued_history_index = None
                if self._consecutive_errors >= self.MAX_CONSECUTIVE_AUDIO_ERRORS:
                    self.audio.stop()
                    should_advance = False
                else:
                    try:
                        self.audio.clear_queue()
                    except (OSError, RuntimeError):
                        logger.debug("Could not clear mpv queue after playback error", exc_info=True)
                    self._advance(reset_error_streak=False)
                    should_advance = True
            if not should_advance:
                self._notify()
            return

        with self._lock:
            finished_id = self.current_id
            if finished_id is None:
                logger.debug("Ignoring mpv EOF without an active track")
                return
            self._consecutive_errors = 0
            self.database.record_play(finished_id)
            self._remember_recent(finished_id)
            if self._queued_id is not None:
                self.current_id, self._queued_id = self._queued_id, None
                if self._queued_history_index is None:
                    if self._session_history_index + 1 < len(self._session_history):
                        del self._session_history[self._session_history_index + 1:]
                    self._session_history.append(self.current_id)
                    self._session_history_index = len(self._session_history) - 1
                else:
                    self._session_history_index = self._queued_history_index
                self._queued_history_index = None
                next_track_queued = True
            else:
                next_track_queued = False
                self.current_id = None
                self._advance(reset_error_streak=False)
                return
        self._notify()
        if next_track_queued:
            self._queue_current_successor()

    def _on_file_loaded(self) -> None:
        with self._lock:
            self._consecutive_errors = 0

    def _queue_current_successor(self) -> None:
        with self._lock:
            if self.current_id is None:
                return
            history_entry = self._find_session_history_entry(1)
            if history_entry is not None:
                history_index, queued = history_entry
            else:
                history_index = None
                candidates = self._shuffle_candidates()
                queued = self._choose_successor(candidates, self.current_id)
            if queued is not None:
                try:
                    self.audio.queue_next(queued["filepath"])
                except (OSError, RuntimeError):
                    logger.debug("Could not queue successor track", exc_info=True)
                    return
                self._queued_id = int(queued["id"])
                self._queued_history_index = history_index

    def statistics(self) -> dict[str, Any]:
        return self.database.get_statistics()

    def _choose_successor(self, tracks: list[dict[str, Any]], current_id: int | None) -> dict[str, Any] | None:
        recent_ids = tuple(self._recent_ids)
        if self.shuffle_mode == "standard":
            choices = self.scheduler.eligible_tracks(tracks, current_id, recent_ids)
            return random.choice(choices) if choices else None
        return self.scheduler.choose(tracks, current_id, recent_ids)

    def _remember_recent(self, track_id: int) -> None:
        if not self._recent_ids or self._recent_ids[-1] != track_id:
            self._recent_ids.append(track_id)

    def _shuffle_candidates(self) -> list[dict[str, Any]]:
        if self._shuffle_playlist_id is not None:
            return self.playlist_tracks(self._shuffle_playlist_id)
        return self.database.get_tracks()

    def set_shuffle_playlist(self, playlist_id: int | None) -> None:
        with self._lock:
            self._shuffle_playlist_id = playlist_id
            if self.current_id is not None:
                try:
                    self.audio.clear_queue()
                except (OSError, RuntimeError):
                    logger.debug("Could not clear mpv queue after playlist change", exc_info=True)
                self._queued_id = None
                self._queue_current_successor()
        self._notify()

    def reset_shuffle_history(self) -> None:
        with self._lock:
            self.database.reset_shuffle_history()
            self._recent_ids.clear()
            try:
                self.audio.clear_queue()
            except (OSError, RuntimeError):
                logger.debug("Could not clear mpv queue after shuffle reset", exc_info=True)
            self._queued_id = None
            self._queue_current_successor()
        self._notify()

    def add_watch_folder(self, folder: str, playlist_id: int) -> str:
        return self.watcher.add_folder(folder, playlist_id)

    def remove_watch_folder(self, folder: str) -> None:
        self.watcher.remove_folder(folder)

    def set_excluded(self, track_id: int, excluded: bool = True) -> None:
        self.database.set_excluded(track_id, excluded)
        if excluded and track_id == self.current_id:
            self.next_track()
        self._notify()

    def reset_statistics(self, track_id: int) -> None:
        self.database.reset_statistics(track_id)
        self._notify()

    def create_playlist(self, name: str) -> int:
        playlist_id = self.database.create_playlist(name)
        self._notify()
        return playlist_id

    def delete_playlist(self, playlist_id: int) -> None:
        self.database.delete_playlist(playlist_id)
        self.watcher.refresh_folders()
        self._notify()

    def add_track_to_playlist(self, playlist_id: int, track_id: int) -> None:
        self.database.add_to_playlist(playlist_id, track_id)
        self._notify()

    def playlist_tracks(self, playlist_id: int) -> list[dict[str, Any]]:
        rows = self.database.get_playlist_tracks(playlist_id)
        folders = [Path(path).resolve() for path in self.database.get_playlist_folders(playlist_id)]
        if folders:
            known_ids = {int(row["id"]) for row in rows}
            for row in self.database.get_tracks():
                filepath = Path(str(row["filepath"])).resolve()
                if int(row["id"]) not in known_ids and any(
                    filepath == folder or folder in filepath.parents for folder in folders
                ):
                    rows.append(row)
        for row in rows:
            row["weight"] = track_weight(row)
        percentages = weight_percentages(rows)
        for row in rows:
            row["weight_percent"] = percentages.get(int(row["id"]), 0.0)
        return rows

    def set_shuffle_mode(self, mode: str) -> None:
        if mode not in {"standard", "entropy"}:
            raise ValueError("Shuffle mode must be 'standard' or 'entropy'")
        self.shuffle_mode = mode
        self._notify()

    def state(self) -> dict[str, Any]:
        return {
            "current": self.current_track(),
            "position": self.audio.time_pos,
            "duration": self.audio.duration,
            "paused": self.audio.paused,
            "volume": self.audio.volume,
            "muted": self.audio.muted,
            "shuffle_mode": self.shuffle_mode,
        }

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._flush_pending_volume()
        self.watcher.close()
        self.audio.close()
        self.database.close()

    def _flush_pending_volume(self, expected_timer: threading.Timer | None = None) -> None:
        with self._volume_lock:
            if expected_timer is not None and self._volume_timer is not expected_timer:
                return
            volume = self._pending_volume
            self._pending_volume = None
            timer = self._volume_timer
            self._volume_timer = None
            if timer is not None and timer is not threading.current_thread():
                timer.cancel()
            if volume is not None:
                save_volume(volume)