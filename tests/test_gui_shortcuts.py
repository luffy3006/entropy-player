import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from entropy.gui.app import EntropyWindow
from entropy.gui.widgets import LibraryNavigation


class FakeDatabase:
    def get_watched_folders(self):
        return []

    def get_playlists(self):
        return []


class FakeAudio:
    def __init__(self):
        self.volume = 50
        self.time_pos = 10.0
        self.duration = 100.0
        self.paused = True
        self.muted = False

    def seek(self, value):
        self.time_pos = value


class FakeController:
    def __init__(self):
        self.database = FakeDatabase()
        self.audio = FakeAudio()
        self.play_pause_count = 0
        self.shuffle_mode = "entropy"
        self.mpris_enabled = False

    def tracks(self, include_excluded=False):
        return [
            {
                "id": track_id,
                "title": str(track_id),
                "artist": "Artist",
                "album": "Album",
                "duration": 100,
                "play_count": 0,
                "skip_count": 0,
                "weight_percent": 50,
                "is_excluded": False,
                "filepath": "/tmp/track.mp3",
            }
            for track_id in (1, 2)
        ]

    def state(self):
        return {
            "current": None,
            "position": self.audio.time_pos,
            "duration": self.audio.duration,
            "paused": self.audio.paused,
            "volume": self.audio.volume,
            "muted": self.audio.muted,
            "shuffle_mode": "entropy",
        }

    def play_pause(self):
        self.play_pause_count += 1

    def next_track(self):
        pass

    def previous_track(self):
        pass

    def set_shuffle_mode(self, _mode):
        pass

    def set_shuffle_playlist(self, _playlist_id):
        pass

    def reset_shuffle_history(self):
        pass

    def close(self):
        pass


class GuiShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = FakeController()
        self.window = EntropyWindow(self.controller)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_space_toggles_play_pause_and_arrows_seek(self):
        self.window.table.setFocus()
        QTest.keyClick(self.window.table, Qt.Key.Key_Space)
        QTest.keyClick(self.window.table, Qt.Key.Key_Left)
        self.assertEqual(self.controller.play_pause_count, 1)
        self.assertEqual(self.controller.audio.time_pos, 5.0)
        QTest.keyClick(self.window.table, Qt.Key.Key_Right)
        self.assertEqual(self.controller.audio.time_pos, 10.0)

    def test_up_down_navigate_rows_and_control_arrows_change_volume(self):
        self.window.table.setFocus()
        self.window.table.setCurrentCell(0, 0)
        QTest.keyClick(self.window.table, Qt.Key.Key_Down)
        self.assertEqual(self.window.table.currentRow(), 1)
        QTest.keyClick(self.window.table, Qt.Key.Key_Up)
        self.assertEqual(self.window.table.currentRow(), 0)
        QTest.keyClick(self.window.table, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.controller.audio.volume, 55)

    def test_arrow_keys_preserve_search_text_editing(self):
        self.window.search.setFocus()
        QTest.keyClicks(self.window.search, "ab")
        QTest.keyClick(self.window.search, Qt.Key.Key_Left)
        QTest.keyClick(self.window.search, Qt.Key.Key_X)
        QTest.keyClick(self.window.search, Qt.Key.Key_Space)
        self.assertEqual(self.window.search.text(), "ax b")
        self.assertEqual(self.controller.audio.time_pos, 10.0)

    def test_clicking_volume_track_sets_level(self):
        slider = self.window.playback.volume
        QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(int(slider.width() * 0.7), slider.height() // 2))
        self.assertGreater(slider.value(), 65)
        self.assertLess(slider.value(), 90)

    def test_dragging_volume_slider_updates_level(self):
        slider = self.window.playback.volume
        start = QPointF(slider.width() * 0.2, slider.height() / 2)
        end = QPointF(slider.width() * 0.8, slider.height() / 2)
        press = QMouseEvent(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        move = QMouseEvent(QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton,
                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(slider, press)
        QApplication.sendEvent(slider, move)
        QApplication.sendEvent(slider, release)
        self.assertGreater(slider.value(), 70)

    def test_clicking_seek_track_seeks_to_clicked_position(self):
        slider = self.window.playback.scrub
        QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(int(slider.width() * 0.7), slider.height() // 2))
        self.assertGreater(self.controller.audio.time_pos, 65)
        self.assertLess(self.controller.audio.time_pos, 90)

    def test_title_column_has_the_most_width(self):
        self.window.resize(1050, 680)
        self.app.processEvents()
        widths = [self.window.table.columnWidth(column) for column in range(self.window.table.columnCount())]
        self.assertGreater(widths[0], max(widths[1:]))

    def test_watched_folders_are_entries_in_single_playlists_section(self):
        navigation = LibraryNavigation()
        navigation.set_playlists([{"id": 7, "name": "Favourites", "track_count": 2, "folders": ["/music/library"]}])
        self.assertEqual(navigation.tree.topLevelItemCount(), 3)
        playlists = navigation.tree.topLevelItem(2)
        self.assertEqual(playlists.text(0), "Playlists")
        self.assertEqual(playlists.childCount(), 1)
        playlist = playlists.child(0)
        self.assertEqual(playlist.childCount(), 1)
        self.assertEqual(playlist.child(0).data(0, Qt.ItemDataRole.UserRole), ("folder", "/music/library", 7))
        self.assertTrue(navigation.add_folder_button.isHidden())
        navigation.select_playlist(7)
        self.assertFalse(navigation.add_folder_button.isHidden())


if __name__ == "__main__":
    unittest.main()