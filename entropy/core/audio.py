"""Small python-mpv adapter; importing the package does not require libmpv."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AudioEngine:
    def __init__(self, on_end: Callable[[str], None]) -> None:
        try:
            import mpv
        except ImportError as exc:
            raise RuntimeError("python-mpv is required. Install Entropy Player and ensure libmpv is available.") from exc
        self._player: Any = mpv.MPV(vid="no")
        self._on_end = on_end
        self._player.event_callback("end-file")(self._handle_end_file)

    def _handle_end_file(self, event: Any) -> None:
        reason = getattr(event, "reason", "unknown")
        if isinstance(reason, int):
            reason = {0: "eof", 1: "restarted", 2: "aborted", 3: "quit", 4: "error", 5: "redirect"}.get(reason, str(reason))
        self._on_end(str(reason).casefold())

    @property
    def time_pos(self) -> float:
        try:
            return float(self._player.time_pos or 0.0)
        except (AttributeError, TypeError, ValueError):
            return 0.0

    @property
    def duration(self) -> float:
        try:
            return float(self._player.duration or 0.0)
        except (AttributeError, TypeError, ValueError):
            return 0.0

    @property
    def volume(self) -> int:
        return int(self._player.volume or 0)

    @volume.setter
    def volume(self, value: int) -> None:
        self._player.volume = max(0, min(100, value))

    @property
    def muted(self) -> bool:
        return bool(self._player.mute)

    @muted.setter
    def muted(self, value: bool) -> None:
        self._player.mute = value

    @property
    def paused(self) -> bool:
        return bool(self._player.pause)

    def play(self, filepath: str) -> None:
        self._player.play(filepath)

    def queue_next(self, filepath: str) -> None:
        self._player.command("loadfile", filepath, "append")

    def clear_queue(self) -> None:
        self._player.command("playlist-remove", 1)

    def pause(self) -> None:
        self._player.pause = not self.paused

    def seek(self, seconds: float) -> None:
        self._player.seek(max(0.0, seconds), reference="absolute")

    def stop(self) -> None:
        self._player.stop()

    def close(self) -> None:
        self._player.terminate()