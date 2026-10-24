"""Interface-independent player state and commands."""

from __future__ import annotations

import random
import threading
from collections import deque
from typing import Any

from entropy.core.audio import AudioEngine
from entropy.core.database import LibraryDatabase
from entropy.core.scheduler import EntropyScheduler, track_weight, weight_percentages
from entropy.core.watcher import LibraryWatcher


class PlayerController:
    def __init__(self, database: LibraryDatabase | None = None, audio: AudioEngine | None = None,
                 watcher: LibraryWatcher | None = None) -> None:
        self.database = database or LibraryDatabase()
        self.scheduler = EntropyScheduler()
        self.shuffle_mode = "entropy"
        self.current_id: int | None = None
        self._forced_next: int | None = None
        self._queued_id: int | None = None
        self._recent_ids: deque[int] = deque(reversed(self.database.recent_played_track_ids()), maxlen=12)
        self._shuffle_playlist_id: int | None = None
        self._lock = threading.RLock()
        self._listeners: list[Any] = []
        self.audio = audio or AudioEngine(self._on_end_file)
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
            if self.current_id is not None and self.current_id != track_id:
                self.database.record_skip(self.current_id, self.audio.time_pos)
                self._remember_recent(self.current_id)
            self._start_track(track)
        self._notify()

    def _start_track(self, track: dict[str, Any]) -> None:
        self.current_id = int(track["id"])
        self._queued_id = None
        self.audio.play(track["filepath"])
        queue_next = getattr(self.audio, "queue_next", None)
        if queue_next is not None:
            candidates = self._shuffle_candidates()
            if candidates:
                queued = self._choose_successor(candidates, self.current_id)
                if queued is not None:
                    try:
                        queue_next(queued["filepath"])
                    except (OSError, RuntimeError):
                        return
                    self._queued_id = int(queued["id"])

    def play_pause(self) -> None:
        if self.current_id is None:
            self.next_track()
        else:
            self.audio.pause()
            self._notify()

    def stop(self) -> None:
        self.audio.stop()
        self.current_id = None
        self._queued_id = None
        self._notify()

    def next_track(self) -> None:
        with self._lock:
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
        tracks = self.database.get_tracks()
        if not tracks:
            return
        current_index = next((i for i, row in enumerate(tracks) if row["id"] == self.current_id), 0)
        self.play_track(int(tracks[(current_index - 1) % len(tracks)]["id"]))

    def force_play_next(self, track_id: int) -> None:
        self._forced_next = track_id
        if self.current_id is None:
            self.next_track()

    def _on_end_file(self, reason: str) -> None:
        with self._lock:
            finished_id = self.current_id
            if finished_id is not None and reason == "eof":
                self.database.record_play(finished_id)
                self._remember_recent(finished_id)
            if reason == "eof" and self._queued_id is not None:
                self.current_id, self._queued_id = self._queued_id, None
                next_track_queued = True
            else:
                next_track_queued = False
                if reason == "eof":
                    self.current_id = None
        self._notify()
        if reason == "eof":
            if next_track_queued:
                self._queue_current_successor()
            else:
                self.next_track()

    def _queue_current_successor(self) -> None:
        if self.current_id is None:
            return
        queue_next = getattr(self.audio, "queue_next", None)
        if queue_next is None:
            return
        candidates = self._shuffle_candidates()
        queued = self._choose_successor(candidates, self.current_id)
        if queued is not None:
            try:
                queue_next(queued["filepath"])
            except (OSError, RuntimeError):
                return
            self._queued_id = int(queued["id"])

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
        self._shuffle_playlist_id = playlist_id
        clear_queue = getattr(self.audio, "clear_queue", None)
        if clear_queue is not None and self.current_id is not None:
            try:
                clear_queue()
            except Exception:
                pass
            self._queued_id = None
            self._queue_current_successor()
        self._notify()

    def reset_shuffle_history(self) -> None:
        self.database.reset_shuffle_history()
        self._recent_ids.clear()
        clear_queue = getattr(self.audio, "clear_queue", None)
        if clear_queue is not None:
            try:
                clear_queue()
            except Exception:
                pass
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
        folder_prefixes = [path.rstrip("/") + "/" for path in self.database.get_playlist_folders(playlist_id)]
        if folder_prefixes:
            known_ids = {int(row["id"]) for row in rows}
            rows.extend(
                row for row in self.database.get_tracks()
                if int(row["id"]) not in known_ids
                and any(row["filepath"].startswith(prefix) for prefix in folder_prefixes)
            )
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
        self.watcher.close()
        self.audio.close()
        self.database.close()