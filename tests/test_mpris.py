import asyncio
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dbus_next.aio import MessageBus
from PyQt6.QtWidgets import QApplication, QWidget

from entropy.gui.mpris import OBJECT_PATH, SERVICE_NAME, MprisBridge


class FakeAudio:
    def __init__(self):
        self.volume = 50
        self.time_pos = 12.0
        self.duration = 90.0
        self.paused = False


class FakeController:
    def __init__(self):
        self.audio = FakeAudio()
        self.current_id = 8
        self.shuffle_mode = "entropy"
        self.play_pause_count = 0

    def state(self):
        return {
            "current": {"id": self.current_id, "title": "Track", "artist": "Artist", "album": "Album"},
            "position": self.audio.time_pos,
            "duration": self.audio.duration,
            "paused": self.audio.paused,
            "volume": self.audio.volume,
        }

    def play_pause(self):
        self.play_pause_count += 1
        self.audio.paused = not self.audio.paused

    def set_volume(self, value):
        self.audio.volume = max(0, min(100, value))

    def subscribe(self, _callback):
        pass


class MprisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "requires a session D-Bus")
    def test_headset_play_pause_is_exported_over_mpris(self):
        controller = FakeController()
        window = QWidget()
        bridge = MprisBridge(controller, window)
        client = None
        try:
            self.assertTrue(bridge.registered, repr(bridge._failure))

            async def send_play_pause():
                nonlocal client
                client = await MessageBus().connect()
                introspection = await client.introspect(SERVICE_NAME, OBJECT_PATH)
                proxy = client.get_proxy_object(SERVICE_NAME, OBJECT_PATH, introspection)
                player = proxy.get_interface("org.mpris.MediaPlayer2.Player")
                await player.call_play_pause()

            asyncio.run(send_play_pause())
            self.assertEqual(controller.play_pause_count, 1)
            self.assertTrue(controller.audio.paused)
        finally:
            if client is not None:
                client.disconnect()
            bridge.close()
            window.close()


if __name__ == "__main__":
    unittest.main()