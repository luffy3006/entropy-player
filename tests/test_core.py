import tempfile
import unittest
from pathlib import Path

from entropy.core.database import LibraryDatabase
from entropy.core.controller import PlayerController
from entropy.core.scheduler import EntropyScheduler, track_weight, weight_percentages


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = LibraryDatabase(self.root / "entropy.db")
        self.track_path = self.root / "track.wav"
        self.track_path.write_bytes(b"RIFF")
        self.track_id = self.database.add_track(self.track_path)

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_new_track_weight_is_one(self):
        self.assertEqual(track_weight(self.database.get_tracks()[0]), 1.0)

    def test_play_and_early_skip_apply_expected_decay(self):
        self.database.record_play(self.track_id)
        self.database.record_skip(self.track_id, 12)
        row = self.database.get_tracks()[0]
        self.assertEqual(row["plays_day"], 1)
        self.assertEqual(row["skip_count"], 1)
        self.assertAlmostEqual(track_weight(row), 1 / ((1 + 5 + 2 + 0.5) * (1 + 1.5)))
        self.database.record_skip(self.track_id, 30)
        self.assertEqual(self.database.get_tracks()[0]["skip_count"], 1)

    def test_exclusion_is_soft_and_survives_rescan(self):
        self.database.set_excluded(self.track_id)
        self.database.add_track(self.track_path)
        self.assertEqual(self.database.get_tracks(), [])
        self.assertTrue(self.database.get_tracks(include_excluded=True)[0]["is_excluded"])

    def test_percentages_and_selection(self):
        second = self.root / "second.ogg"
        second.write_bytes(b"OggS")
        second_id = self.database.add_track(second)
        tracks = self.database.get_tracks()
        percentages = weight_percentages(tracks)
        self.assertAlmostEqual(sum(percentages.values()), 100.0)
        chosen = EntropyScheduler().choose(tracks, current_id=self.track_id)
        self.assertEqual(chosen["id"], second_id)

    def test_playlist_membership(self):
        playlist_id = self.database.create_playlist("Late night")
        self.database.add_to_playlist(playlist_id, self.track_id)
        self.assertEqual(self.database.get_playlist_tracks(playlist_id)[0]["id"], self.track_id)
        self.assertEqual(self.database.get_playlists()[0]["track_count"], 1)

    def test_directory_cleanup_uses_a_literal_path_prefix(self):
        library = self.root / "music_100%"
        sibling = self.root / "music_100X"
        library.mkdir()
        sibling.mkdir()
        nested_track = library / "nested.wav"
        sibling_track = sibling / "keep.wav"
        nested_track.write_bytes(b"RIFF")
        sibling_track.write_bytes(b"RIFF")
        self.database.add_track(nested_track)
        sibling_id = self.database.add_track(sibling_track)
        self.database.remove_tracks_under(library)
        remaining_ids = {row["id"] for row in self.database.get_tracks()}
        self.assertEqual(remaining_ids, {self.track_id, sibling_id})

    def test_direct_track_change_logs_an_early_skip(self):
        second = self.root / "second.mp3"
        second.write_bytes(b"ID3")
        second_id = self.database.add_track(second)

        class FakeAudio:
            time_pos = 8.0

            def play(self, _filepath):
                pass

        class FakeWatcher:
            def start(self):
                pass

        controller = PlayerController(database=self.database, audio=FakeAudio(), watcher=FakeWatcher())
        controller.play_track(self.track_id)
        controller.play_track(second_id)
        first = next(row for row in self.database.get_tracks(include_excluded=True) if row["id"] == self.track_id)
        self.assertEqual(first["skip_count"], 1)


if __name__ == "__main__":
    unittest.main()