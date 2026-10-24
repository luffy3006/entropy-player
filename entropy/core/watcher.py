"""Watch configured directories for additions and removals."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from entropy.core.database import LibraryDatabase, SUPPORTED_FORMATS


class LibraryWatcher:
    def __init__(self, database: LibraryDatabase, on_change: Callable[[], None]) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError as exc:
            raise RuntimeError("watchdog is required for directory monitoring. Install Entropy Player dependencies.") from exc
        self._database = database
        self._on_change = on_change
        self._observer = Observer()

        class Handler(FileSystemEventHandler):
            def on_created(handler_self, event: object) -> None:
                if getattr(event, "is_directory", False):
                    self._scan(getattr(event, "src_path"))
                else:
                    self._add(getattr(event, "src_path"))

            def on_moved(handler_self, event: object) -> None:
                if getattr(event, "is_directory", False):
                    self._database.remove_tracks_under(getattr(event, "src_path"))
                    self._scan(getattr(event, "dest_path"))
                    self._on_change()
                else:
                    self._remove(getattr(event, "src_path"))
                    self._add(getattr(event, "dest_path"))

            def on_deleted(handler_self, event: object) -> None:
                if getattr(event, "is_directory", False):
                    self._database.remove_tracks_under(getattr(event, "src_path"))
                    self._on_change()
                else:
                    self._remove(getattr(event, "src_path"))

        self._handler = Handler()
        self._scheduled: set[str] = set()

    @staticmethod
    def _is_audio(path: str) -> bool:
        return Path(path).suffix.lower() in SUPPORTED_FORMATS

    def _add(self, path: str) -> None:
        if self._is_audio(path) and self._database.add_track(path) is not None:
            self._on_change()

    def _remove(self, path: str) -> None:
        if self._is_audio(path):
            self._database.remove_track_by_path(path)
            self._on_change()

    def _scan(self, folder: str) -> None:
        for candidate in Path(folder).rglob("*"):
            if candidate.is_file() and self._is_audio(str(candidate)):
                self._database.add_track(candidate)

    def add_folder(self, folder: str) -> str:
        path = self._database.add_watched_folder(folder)
        if path not in self._scheduled:
            self._observer.schedule(self._handler, path, recursive=True)
            self._scheduled.add(path)
        self._scan(path)
        self._on_change()
        return path

    def remove_folder(self, folder: str) -> None:
        path = str(Path(folder).expanduser().resolve())
        self._database.remove_watched_folder(path)
        if path in self._scheduled:
            self._observer.unschedule_all()
            self._scheduled.clear()
            for watched in self._database.get_watched_folders():
                self._observer.schedule(self._handler, watched, recursive=True)
                self._scheduled.add(watched)
        self._on_change()

    def start(self) -> None:
        for folder in self._database.get_watched_folders():
            if Path(folder).is_dir() and folder not in self._scheduled:
                self._observer.schedule(self._handler, folder, recursive=True)
                self._scheduled.add(folder)
                self._scan(folder)
        if not self._observer.is_alive():
            self._observer.start()

    def close(self) -> None:
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=2)