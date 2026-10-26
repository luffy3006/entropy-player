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


if __name__ == "__main__":
    unittest.main()