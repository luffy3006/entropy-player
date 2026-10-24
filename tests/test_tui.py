import unittest

from textual.widgets import DataTable

from entropy.tui.app import EntropyTUI


class FakeAudio:
    def __init__(self):
        self.time_pos = 20.0
        self.duration = 120.0
        self.volume = 50
        self.muted = False
        self.paused = False
        self.seek_positions = []

    def seek(self, position):
        self.time_pos = max(0.0, position)
        self.seek_positions.append(self.time_pos)


class FakeController:
    def __init__(self):
        self.audio = FakeAudio()
        self.shuffle_mode = "entropy"
        self._tracks = [
            {"id": index, "title": f"Track {index}", "artist": "Artist", "album": "Album",
             "duration": 120, "play_count": 0, "skip_count": 0, "weight_percent": 100 / 3}
            for index in range(1, 4)
        ]

    def tracks(self):
        return self._tracks

    def state(self):
        return {
            "current": None,
            "position": self.audio.time_pos,
            "duration": self.audio.duration,
            "paused": self.audio.paused,
            "volume": self.audio.volume,
            "muted": self.audio.muted,
            "shuffle_mode": self.shuffle_mode,
        }

    def close(self):
        pass


class TuiShortcutTests(unittest.IsolatedAsyncioTestCase):
    async def test_arrows_keep_selection_after_refresh_and_shortcuts_control_audio(self):
        controller = FakeController()
        app = EntropyTUI(controller)
        async with app.run_test() as pilot:
            await pilot.press("down")
            table = app.query_one(DataTable)
            self.assertEqual(table.cursor_row, 1)

            app.refresh_view()
            self.assertEqual(table.cursor_row, 1)

            await pilot.press("h")
            await pilot.press("l")
            self.assertEqual(controller.audio.seek_positions, [15.0, 20.0])

            await pilot.press("-")
            await pilot.press("+")
            self.assertEqual(controller.audio.volume, 50)


if __name__ == "__main__":
    unittest.main()