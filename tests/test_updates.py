import unittest

from entropy import __version__
from entropy.updates import UpdateResult, _version_key


class UpdateTests(unittest.TestCase):
    def test_version_comparison_ignores_prefix_and_trailing_zeroes(self):
        self.assertEqual(_version_key("v1.2"), _version_key("1.2.0"))

    def test_newer_release_is_reported(self):
        self.assertTrue(UpdateResult("v99.0.0", "https://example.test/release").update_available)

    def test_current_release_is_not_reported_as_an_update(self):
        self.assertFalse(UpdateResult(__version__, "https://example.test/release").update_available)


if __name__ == "__main__":
    unittest.main()