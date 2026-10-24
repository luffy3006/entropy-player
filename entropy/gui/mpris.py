"""MPRIS controls for Linux desktop and headset media buttons."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import NameFlag
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method, signal
from PyQt6.QtCore import QObject, pyqtSignal

SERVICE_NAME = "org.mpris.MediaPlayer2.entropyplayer"
OBJECT_PATH = "/org/mpris/MediaPlayer2"


class _GuiActions(QObject):
    raise_requested = pyqtSignal()
    quit_requested = pyqtSignal()


class _RootInterface(ServiceInterface):
    def __init__(self, actions: _GuiActions) -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self._actions = actions

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":
        return "Entropy Player"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":
        return "entropy-player"

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":
        return ["audio/mpeg", "audio/flac", "audio/ogg", "audio/wav", "video/mp4", "video/x-matroska"]

    @method()
    def Raise(self) -> "":
        self._actions.raise_requested.emit()

    @method()
    def Quit(self) -> "":
        self._actions.quit_requested.emit()


class _PlayerInterface(ServiceInterface):
    def __init__(self, controller: Any, changed: Any) -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._controller = controller
        self._changed = changed

    def _publish(self) -> None:
        self._changed()

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        state = self._controller.state()
        if state["current"] is None:
            return "Stopped"
        return "Paused" if state["paused"] else "Playing"

    @dbus_property(access=PropertyAccess.READ)
    def LoopStatus(self) -> "s":
        return "None"

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def Shuffle(self) -> "b":
        return self._controller.shuffle_mode != "standard"

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        state = self._controller.state()
        current = state["current"]
        if current is None:
            return {}
        return {
            "mpris:trackid": Variant("o", f"/org/mpris/MediaPlayer2/track/{current['id']}"),
            "xesam:title": Variant("s", current["title"]),
            "xesam:artist": Variant("as", [current["artist"]]),
            "xesam:album": Variant("s", current["album"]),
            "mpris:length": Variant("x", int(state["duration"] * 1_000_000)),
        }

    @dbus_property(access=PropertyAccess.READWRITE)
    def Volume(self) -> "d":
        return float(self._controller.audio.volume) / 100.0

    @Volume.setter
    def Volume(self, value: "d") -> None:
        self._controller.audio.volume = round(max(0.0, min(1.0, value)) * 100)
        self._publish()

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        return int(self._controller.audio.time_pos * 1_000_000)

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return True

    @method()
    def Play(self) -> "":
        if self._controller.current_id is None:
            self._controller.next_track()
        elif self._controller.audio.paused:
            self._controller.play_pause()
        self._publish()

    @method()
    def Pause(self) -> "":
        if self._controller.current_id is not None and not self._controller.audio.paused:
            self._controller.play_pause()
        self._publish()

    @method()
    def PlayPause(self) -> "":
        self._controller.play_pause()
        self._publish()

    @method()
    def Stop(self) -> "":
        self._controller.stop()
        self._publish()

    @method()
    def Next(self) -> "":
        self._controller.next_track()
        self._publish()

    @method()
    def Previous(self) -> "":
        self._controller.previous_track()
        self._publish()

    @method()
    def Seek(self, offset: "x") -> "":
        target = max(0.0, self._controller.audio.time_pos + offset / 1_000_000)
        self._controller.audio.seek(target)
        self.Seeked(int(target * 1_000_000))
        self._publish()

    @method()
    def SetPosition(self, track_id: "o", position: "x") -> "":
        current = self._controller.current_track()
        expected = f"/org/mpris/MediaPlayer2/track/{current['id']}" if current else ""
        if track_id == expected:
            self._controller.audio.seek(max(0.0, position / 1_000_000))
            self._publish()

    @method()
    def OpenUri(self, uri: "s") -> "":
        if uri.startswith("file://"):
            from urllib.parse import unquote, urlparse

            track_id = self._controller.database.add_track(unquote(urlparse(uri).path))
            if track_id is not None:
                self._controller.play_track(track_id)
                self._publish()

    @method()
    def SetShuffle(self, enabled: "b") -> "":
        self._controller.set_shuffle_mode("entropy" if enabled else "standard")
        self._publish()

    @signal()
    def Seeked(self, position: "x") -> "x":
        return position


class MprisBridge:
    def __init__(self, controller: Any, window: Any) -> None:
        self.controller = controller
        self.window = window
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._thread = threading.Thread(target=self._run, name="entropy-mpris", daemon=True)
        self._ready = threading.Event()
        self._failure: Exception | None = None
        self.registered = False
        self._actions = _GuiActions(window)
        self._actions.raise_requested.connect(self._raise_window)
        self._actions.quit_requested.connect(window.close)
        self._player_interface = _PlayerInterface(controller, self._publish_state)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _raise_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
            self._loop.run_forever()
        except Exception as exc:
            self._failure = exc
        finally:
            if self._bus is not None:
                self._bus.disconnect()
            self._loop.close()
            self._ready.set()

    async def _connect(self) -> None:
        self._bus = await MessageBus().connect()
        root_interface = _RootInterface(self._actions)
        self._bus.export(OBJECT_PATH, root_interface)
        self._bus.export(OBJECT_PATH, self._player_interface)
        await self._bus.request_name(SERVICE_NAME)
        self.registered = True
        if hasattr(self.controller, "subscribe"):
            self.controller.subscribe(self._publish_state)
        self._ready.set()

    def _publish_state(self) -> None:
        if self._loop is None or not self._loop.is_running():
            return

        def publish() -> None:
            state = self.controller.state()
            current = state["current"]
            metadata = self._player_interface.Metadata
            changed = {
                "PlaybackStatus": self._player_interface.PlaybackStatus,
                "Metadata": metadata,
                "Position": int(state["position"] * 1_000_000),
                "Volume": float(state["volume"]) / 100.0,
            }
            self._player_interface.emit_properties_changed(changed)

        self._loop.call_soon_threadsafe(publish)

    def close(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)
