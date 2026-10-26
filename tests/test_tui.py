import unittest

from textual.widgets import DataTable, Input
from textual.coordinate import Coordinate

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
        self.current_id = None
        self._tracks = [
            {"id": index, "title": f"Track {index}", "artist": "Artist", "album": "Album",
             "duration": 120, "play_count": 0, "skip_count": 0, "weight_percent": 100 / 3}
            for index in range(1, 4)
        ]

    def tracks(self):
        return self._tracks

    def state(self):
        return {
            "current": next((track for track in self._tracks if track["id"] == self.current_id), None),
            "position": self.audio.time_pos,
            "duration": self.audio.duration,
            "paused": self.audio.paused,
            "volume": self.audio.volume,
            "muted": self.audio.muted,
            "shuffle_mode": self.shuffle_mode,
        }

    def close(self):
        pass

    def set_volume(self, value):
        self.audio.volume = max(0, min(100, value))


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
            await pilot.press("left")
            await pilot.press("right")
            self.assertEqual(controller.audio.seek_positions, [15.0, 20.0, 15.0, 20.0])

            await pilot.press("-")
            await pilot.press("+")
            self.assertEqual(controller.audio.volume, 50)

            await pilot.press("/")
            self.assertEqual(app.focused, app.query_one(Input))
            await pilot.press("escape")
            self.assertEqual(app.focused, table)

    async def test_current_track_highlight_and_scroll_survive_refresh(self):
        controller = FakeController()
        controller._tracks = [
            {**track, "id": index, "title": f"Track {index}"}
            for index, track in enumerate(controller._tracks * 20, start=1)
        ]
        controller.current_id = 15
        app = EntropyTUI(controller)
        async with app.run_test(size=(100, 24)) as pilot:
            table = app.query_one(DataTable)
            await pilot.press(*(["down"] * 20))
            previous_cursor = table.cursor_row
            previous_scroll = table.scroll_y
            highlighted = table.get_cell_at(Coordinate(14, 0))
            self.assertIn("bold", str(highlighted.style))

            app.refresh_view()

            self.assertEqual(table.cursor_row, previous_cursor)
            self.assertEqual(table.scroll_y, previous_scroll)


if __name__ == "__main__":
    unittest.main()