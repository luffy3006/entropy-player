"""Small python-mpv adapter; importing the package does not require libmpv."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

EndFileReason = Literal["eof", "stop", "quit", "error", "redirect", "unknown"]

_NUMERIC_END_REASONS: dict[int, EndFileReason] = {
    0: "eof",
    1: "stop",
    2: "stop",
    3: "quit",
    4: "error",
    5: "redirect",
}
_STRING_END_REASONS: dict[str, EndFileReason] = {
    "eof": "eof",
    "restarted": "stop",
    "aborted": "stop",
    "stop": "stop",
    "quit": "quit",
    "error": "error",
    "redirect": "redirect",
}


def normalize_end_reason(reason: object) -> EndFileReason:
    if isinstance(reason, int):
        return _NUMERIC_END_REASONS.get(reason, "unknown")
    value = str(reason).strip().casefold()
    if value.isdecimal():
        return _NUMERIC_END_REASONS.get(int(value), "unknown")
    value = value.removeprefix("mpv_end_file_reason_")
    return _STRING_END_REASONS.get(value, "unknown")


class AudioBackend(Protocol):
    @property
    def time_pos(self) -> float: ...

    @property
    def duration(self) -> float: ...

    @property
    def volume(self) -> int: ...

    @volume.setter
    def volume(self, value: int) -> None: ...

    @property
    def muted(self) -> bool: ...

    @muted.setter
    def muted(self, value: bool) -> None: ...

    @property
    def paused(self) -> bool: ...

    def set_end_callback(self, callback: Callable[[str], None]) -> None: ...
    def set_file_loaded_callback(self, callback: Callable[[], None]) -> None: ...
    def play(self, filepath: str) -> None: ...
    def queue_next(self, filepath: str) -> None: ...
    def clear_queue(self) -> None: ...
    def pause(self) -> None: ...
    def seek(self, seconds: float) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class AudioEngine(AudioBackend):
    def __init__(
        self,
        on_end: Callable[[str], None],
        *,
        audio_output: str | None = None,
        video_output: str | None = None,
    ) -> None:
        try:
            import mpv
        except ImportError as exc:
            raise RuntimeError("python-mpv is required. Install Entropy Player and ensure libmpv is available.") from exc
        options: dict[str, str] = {"vid": "no"}
        if audio_output is not None:
            options["ao"] = audio_output
        if video_output is not None:
            options["vo"] = video_output
        self._player: Any = mpv.MPV(**options)
        self._on_end = on_end
        self._player.event_callback("end-file")(self._handle_end_file)
        self._on_file_loaded: Callable[[], None] = lambda: None
        self._player.event_callback("file-loaded")(self._handle_file_loaded)

    def set_end_callback(self, callback: Callable[[str], None]) -> None:
        self._on_end = callback

    def set_file_loaded_callback(self, callback: Callable[[], None]) -> None:
        self._on_file_loaded = callback

    def _handle_file_loaded(self, _event: Any) -> None:
        self._on_file_loaded()

    def _handle_end_file(self, event: Any) -> None:
        event_data = getattr(event, "data", None)
        reason = getattr(event_data, "reason", getattr(event, "reason", "unknown"))
        self._on_end(normalize_end_reason(reason))

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