import unittest

from entropy.core.audio import AudioEngine


class AudioEngineTests(unittest.TestCase):
    def test_numeric_mpv_eof_reason_is_normalized(self):
        reasons = []
        audio = AudioEngine.__new__(AudioEngine)
        audio._on_end = reasons.append

        class EndFileEvent:
            reason = 0

        audio._handle_end_file(EndFileEvent())

        self.assertEqual(reasons, ["eof"])


if __name__ == "__main__":
    unittest.main()