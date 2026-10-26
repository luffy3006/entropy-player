import json
import os
import tempfile
import unittest
from unittest.mock import patch

from entropy.core.preferences import load_volume, save_volume


class VolumePreferenceTests(unittest.TestCase):
    def test_volume_is_saved_and_restored_with_bounds(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            self.assertEqual(load_volume(37), 37)
            save_volume(73)
            self.assertEqual(load_volume(), 73)
            save_volume(150)
            self.assertEqual(load_volume(), 100)

    def test_malformed_preferences_fall_back_to_default(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            path = os.path.join(directory, "entropy", "settings.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as settings:
                settings.write("not json")
            self.assertEqual(load_volume(42), 42)

    def test_saving_volume_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            path = os.path.join(directory, "entropy", "settings.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as settings:
                settings.write('{"theme": "Strawberry Blue", "last_update_check": 123}')

            save_volume(62)

            with open(path, encoding="utf-8") as settings:
                self.assertEqual(
                    json.load(settings),
                    {"theme": "Strawberry Blue", "last_update_check": 123, "volume": 62},
                )

    def test_saving_volume_recovers_from_malformed_preferences(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            path = os.path.join(directory, "entropy", "settings.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as settings:
                settings.write("not json")

            save_volume(62)

            with open(path, encoding="utf-8") as settings:
                self.assertEqual(json.load(settings), {"volume": 62})


if __name__ == "__main__":
    unittest.main()