"""SQLite persistence for the library, watch folders, and play history."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SUPPORTED_FORMATS = {".mp3", ".flac", ".ogg", ".wav", ".mp4", ".mkv"}


class LibraryDatabase:
    def __init__(self, path: str | Path | None = None) -> None:
        default_path = Path.home() / ".config" / "entropy" / "entropy.db"
        self.path = Path(path).expanduser() if path else default_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY,
                    filepath TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL DEFAULT 'Unknown Artist',
                    album TEXT NOT NULL DEFAULT 'Unknown Album',
                    duration REAL NOT NULL DEFAULT 0,
                    date_added REAL NOT NULL,
                    is_excluded INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS play_history (
                    id INTEGER PRIMARY KEY,
                    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skips (
                    id INTEGER PRIMARY KEY,
                    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                    timestamp REAL NOT NULL,
                    elapsed REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watched_folders (
                    path TEXT PRIMARY KEY,
                    date_added REAL NOT NULL,
                    playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    date_added REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(playlist_id, track_id)
                );
                CREATE INDEX IF NOT EXISTS history_track_time ON play_history(track_id, timestamp);
                CREATE INDEX IF NOT EXISTS skips_track_time ON skips(track_id, timestamp);
                """
            )
            folder_columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(watched_folders)")
            }
            if "playlist_id" not in folder_columns:
                self._connection.execute(
                    "ALTER TABLE watched_folders ADD COLUMN playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE"
                )
            unassigned = self._connection.execute(
                "SELECT COUNT(*) FROM watched_folders WHERE playlist_id IS NULL"
            ).fetchone()[0]
            if unassigned:
                playlist = self._connection.execute(
                    "SELECT id FROM playlists WHERE name = 'Imported folders'"
                ).fetchone()
                if playlist is None:
                    cursor = self._connection.execute(
                        "INSERT INTO playlists(name, date_added) VALUES ('Imported folders', ?)", (time.time(),)
                    )
                    playlist_id = int(cursor.lastrowid)
                else:
                    playlist_id = int(playlist["id"])
                self._connection.execute(
                    "UPDATE watched_folders SET playlist_id = ? WHERE playlist_id IS NULL", (playlist_id,)
                )

    @staticmethod
    def _metadata(filepath: str) -> dict[str, Any]:
        path = Path(filepath)
        metadata: dict[str, Any] = {
            "title": path.stem,
            "artist": "Unknown Artist",
            "album": "Unknown Album",
            "duration": 0.0,
        }
        try:
            from mutagen import File

            audio = File(filepath, easy=True)
            if audio is not None:
                tags = audio.tags or {}
                metadata["title"] = str(tags.get("title", [path.stem])[0])
                metadata["artist"] = str(tags.get("artist", ["Unknown Artist"])[0])
                metadata["album"] = str(tags.get("album", ["Unknown Album"])[0])
                metadata["duration"] = float(audio.info.length)
        except Exception:
            pass
        return metadata

    def add_track(self, filepath: str | Path) -> int | None:
        path = Path(filepath).expanduser().resolve()
        if path.suffix.lower() not in SUPPORTED_FORMATS or not path.is_file():
            return None
        metadata = self._metadata(str(path))
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO tracks(filepath, title, artist, album, duration, date_added)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(filepath) DO UPDATE SET title=excluded.title,
                     artist=excluded.artist, album=excluded.album, duration=excluded.duration""",
                (str(path), metadata["title"], metadata["artist"], metadata["album"], metadata["duration"], now),
            )
            row = self._connection.execute("SELECT id FROM tracks WHERE filepath = ?", (str(path),)).fetchone()
            return int(row["id"])

    def remove_track_by_path(self, filepath: str | Path) -> None:
        path = str(Path(filepath).expanduser().resolve())
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM tracks WHERE filepath = ?", (path,))

    def remove_tracks_under(self, folder: str | Path) -> None:
        prefix = str(Path(folder).expanduser().resolve()).rstrip(os.sep) + os.sep
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM tracks WHERE substr(filepath, 1, ?) = ?", (len(prefix), prefix)
            )

    def set_excluded(self, track_id: int, excluded: bool = True) -> None:
        with self._lock, self._connection:
            self._connection.execute("UPDATE tracks SET is_excluded = ? WHERE id = ?", (int(excluded), track_id))

    def get_tracks(self, include_excluded: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        condition = "" if include_excluded else "WHERE t.is_excluded = 0"
        query = f"""SELECT t.*,
            (SELECT COUNT(*) FROM play_history h WHERE h.track_id=t.id) AS play_count,
            (SELECT COUNT(*) FROM skips s WHERE s.track_id=t.id) AS skip_count,
            (SELECT COUNT(*) FROM play_history h WHERE h.track_id=t.id AND h.timestamp>=?) AS plays_day,
            (SELECT COUNT(*) FROM play_history h WHERE h.track_id=t.id AND h.timestamp>=?) AS plays_week,
            (SELECT COUNT(*) FROM play_history h WHERE h.track_id=t.id AND h.timestamp>=?) AS plays_month
            FROM tracks t {condition} ORDER BY t.title COLLATE NOCASE"""
        with self._lock:
            rows = self._connection.execute(query, (now - 86400, now - 604800, now - 2592000)).fetchall()
        return [dict(row) for row in rows]

    def get_track(self, track_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None

    def record_play(self, track_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("INSERT INTO play_history(track_id, timestamp) VALUES (?, ?)", (track_id, time.time()))

    def record_skip(self, track_id: int, elapsed: float) -> None:
        if elapsed >= 30:
            return
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO skips(track_id, timestamp, elapsed) VALUES (?, ?, ?)",
                (track_id, time.time(), max(0.0, elapsed)),
            )

    def reset_statistics(self, track_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM play_history WHERE track_id = ?", (track_id,))
            self._connection.execute("DELETE FROM skips WHERE track_id = ?", (track_id,))

    def add_watched_folder(self, folder: str | Path, playlist_id: int) -> str:
        path = str(Path(folder).expanduser().resolve())
        if not os.path.isdir(path):
            raise ValueError(f"Not a directory: {path}")
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO watched_folders(path, date_added, playlist_id) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET playlist_id=excluded.playlist_id",
                (path, time.time(), playlist_id),
            )
        return path

    def remove_watched_folder(self, folder: str | Path) -> None:
        path = str(Path(folder).expanduser().resolve())
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM watched_folders WHERE path = ?", (path,))

    def get_watched_folders(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute("SELECT path FROM watched_folders ORDER BY path COLLATE NOCASE").fetchall()
        return [str(row["path"]) for row in rows]

    def get_playlist_folders(self, playlist_id: int) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT path FROM watched_folders WHERE playlist_id = ? ORDER BY path COLLATE NOCASE",
                (playlist_id,),
            ).fetchall()
        return [str(row["path"]) for row in rows]

    def create_playlist(self, name: str) -> int:
        playlist_name = name.strip()
        if not playlist_name:
            raise ValueError("Playlist name cannot be empty")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO playlists(name, date_added) VALUES (?, ?)", (playlist_name, time.time())
            )
            return int(cursor.lastrowid)

    def get_playlists(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT p.id, p.name,
                          (SELECT COUNT(*) FROM playlist_tracks pt WHERE pt.playlist_id=p.id) AS track_count,
                          (SELECT COUNT(*) FROM watched_folders wf WHERE wf.playlist_id=p.id) AS folder_count
                   FROM playlists p ORDER BY p.name COLLATE NOCASE"""
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_playlist(self, playlist_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def add_to_playlist(self, playlist_id: int, track_id: int) -> None:
        with self._lock, self._connection:
            position = self._connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
            ).fetchone()[0]
            self._connection.execute(
                "INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position) VALUES (?, ?, ?)",
                (playlist_id, track_id, position),
            )

    def get_playlist_tracks(self, playlist_id: int, include_excluded: bool = False) -> list[dict[str, Any]]:
        tracks = self.get_tracks(include_excluded=include_excluded)
        with self._lock:
            rows = self._connection.execute(
                "SELECT track_id, position FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                (playlist_id,),
            ).fetchall()
        order = {row["track_id"]: row["position"] for row in rows}
        return sorted((track for track in tracks if track["id"] in order), key=lambda track: order[track["id"]])

    def close(self) -> None:
        with self._lock:
            self._connection.close()