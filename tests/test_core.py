import tempfile
import time
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
        self.assertAlmostEqual(row["decayed_skip_count"], 1.0, places=4)
        smoothed_rate = (row["decayed_skip_count"] + 1) / (row["play_count"] + 5)
        raw_weight = 1 / ((1 + 5 + 2 + 0.5) * (1 + 4 * (smoothed_rate - 0.2)))
        self.assertAlmostEqual(track_weight(row), raw_weight ** 0.8)
        self.database.record_skip(self.track_id, 30)
        self.assertEqual(self.database.get_tracks()[0]["skip_count"], 1)

    def test_old_skips_decay_instead_of_remaining_a_lifetime_penalty(self):
        self.database.record_skip(self.track_id, 5)
        with self.database._lock, self.database._connection:
            self.database._connection.execute(
                "UPDATE skips SET timestamp = ? WHERE track_id = ?",
                (time.time() - 7 * 86400, self.track_id),
            )
        row = self.database.get_tracks()[0]
        self.assertAlmostEqual(row["decayed_skip_count"], 0.5, places=3)

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

    def test_recent_track_cooldown_and_small_library_relaxation(self):
        tracks = [{"id": track_id} for track_id in range(1, 7)]
        scheduler = EntropyScheduler(cooldown=4)
        eligible = scheduler.eligible_tracks(tracks, current_id=6, recent_ids=[1, 2, 3, 4])
        self.assertEqual([track["id"] for track in eligible], [5])
        small_library = tracks[:3]
        eligible_small = scheduler.eligible_tracks(small_library, current_id=3, recent_ids=[1, 2])
        self.assertEqual([track["id"] for track in eligible_small], [1])

    def test_global_shuffle_reset_clears_history_but_keeps_tracks(self):
        self.database.record_play(self.track_id)
        self.database.record_skip(self.track_id, 5)
        self.database.reset_shuffle_history()
        row = self.database.get_tracks()[0]
        self.assertEqual(row["play_count"], 0)
        self.assertEqual(row["skip_count"], 0)
        self.assertEqual(row["decayed_skip_count"], 0)
        self.assertIsNotNone(self.database.get_track(self.track_id))

    def test_playlist_membership(self):
        playlist_id = self.database.create_playlist("Late night")
        self.database.add_to_playlist(playlist_id, self.track_id)
        self.assertEqual(self.database.get_playlist_tracks(playlist_id)[0]["id"], self.track_id)
        self.assertEqual(self.database.get_playlists()[0]["track_count"], 1)

    def test_playlist_owns_watched_folders_and_deletion_removes_registration(self):
        folder = self.root / "playlist-folder"
        folder.mkdir()
        audio_path = folder / "folder-track.mp3"
        audio_path.write_bytes(b"ID3")
        track_id = self.database.add_track(audio_path)
        playlist_id = self.database.create_playlist("Road mix")
        self.database.add_watched_folder(folder, playlist_id)
        self.assertEqual(self.database.get_playlist_folders(playlist_id), [str(folder.resolve())])
        self.assertEqual(self.database.get_playlist_tracks(playlist_id), [])
        controller = PlayerController.__new__(PlayerController)
        controller.database = self.database
        controller.scheduler = EntropyScheduler()
        playlist_tracks = PlayerController.playlist_tracks(controller, playlist_id)
        self.assertEqual([track["id"] for track in playlist_tracks], [track_id])
        self.database.delete_playlist(playlist_id)
        self.assertEqual(self.database.get_watched_folders(), [])
        self.assertIsNotNone(self.database.get_track(track_id))

    def test_shuffle_candidates_are_scoped_to_selected_playlist(self):
        second = self.root / "outside.mp3"
        second.write_bytes(b"ID3")
        outside_id = self.database.add_track(second)
        playlist_id = self.database.create_playlist("Selected")
        self.database.add_to_playlist(playlist_id, self.track_id)

        class FakeAudio:
            time_pos = 0

        class FakeWatcher:
            def start(self):
                pass

        controller = PlayerController(database=self.database, audio=FakeAudio(), watcher=FakeWatcher())
        controller.set_shuffle_playlist(playlist_id)
        candidate_ids = [track["id"] for track in controller._shuffle_candidates()]
        self.assertEqual(candidate_ids, [self.track_id])
        self.assertNotIn(outside_id, candidate_ids)
        empty_playlist = self.database.create_playlist("Empty")
        controller.set_shuffle_playlist(empty_playlist)
        self.assertEqual(controller._shuffle_candidates(), [])

    def test_legacy_watched_folders_are_migrated_into_imported_playlist(self):
        legacy_db = self.root / "legacy.db"
        folder = self.root / "legacy-folder"
        folder.mkdir()
        import sqlite3

        connection = sqlite3.connect(legacy_db)
        connection.execute("CREATE TABLE watched_folders(path TEXT PRIMARY KEY, date_added REAL NOT NULL)")
        connection.execute("INSERT INTO watched_folders(path, date_added) VALUES (?, 0)", (str(folder.resolve()),))
        connection.commit()
        connection.close()
        migrated = LibraryDatabase(legacy_db)
        try:
            playlist = next(row for row in migrated.get_playlists() if row["name"] == "Imported folders")
            self.assertEqual(migrated.get_playlist_folders(playlist["id"]), [str(folder.resolve())])
        finally:
            migrated.close()

    def test_end_of_track_hands_off_to_prequeued_track(self):
        second = self.root / "second.mp3"
        second.write_bytes(b"ID3")
        second_id = self.database.add_track(second)

        class FakeAudio:
            time_pos = 60.0

            def __init__(self):
                self.played = []
                self.queued = []

            def play(self, filepath):
                self.played.append(filepath)

            def queue_next(self, filepath):
                self.queued.append(filepath)

        class FakeWatcher:
            def start(self):
                pass

        audio = FakeAudio()
        controller = PlayerController(database=self.database, audio=audio, watcher=FakeWatcher())
        controller.play_track(self.track_id)
        self.assertEqual(audio.queued, [str(second.resolve())])
        controller._on_end_file("eof")
        self.assertEqual(controller.current_id, second_id)
        self.assertEqual(audio.played, [str(self.track_path.resolve())])
        counts = {row["id"]: row["play_count"] for row in self.database.get_tracks()}
        self.assertEqual(counts[self.track_id], 1)
        self.assertEqual(audio.queued[-1], str(self.track_path.resolve()))

    def test_video_containers_are_indexed_as_audio_items(self):
        for suffix in (".mp4", ".mkv"):
            media_path = self.root / f"audio-container{suffix}"
            media_path.write_bytes(b"container")
            self.assertIsNotNone(self.database.add_track(media_path))
        indexed_paths = {row["filepath"] for row in self.database.get_tracks()}
        self.assertIn(str((self.root / "audio-container.mp4").resolve()), indexed_paths)
        self.assertIn(str((self.root / "audio-container.mkv").resolve()), indexed_paths)

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