import ctypes.util
import importlib.util
import math
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from entropy.core.audio import AudioEngine, normalize_end_reason

_MPV_AVAILABLE = bool(ctypes.util.find_library("mpv") and importlib.util.find_spec("mpv"))


class AudioEngineTests(unittest.TestCase):
    def test_end_file_reasons_normalize_to_closed_set(self):
        values = {
            0: "eof",
            2: "stop",
            3: "quit",
            4: "error",
            5: "redirect",
            1: "unknown",
            "EOF": "eof",
            "MPV_END_FILE_REASON_STOP": "stop",
            "4": "error",
            "aborted": "unknown",
            "unexpected": "unknown",
        }
        for raw_reason, expected in values.items():
            with self.subTest(raw_reason=raw_reason):
                self.assertEqual(normalize_end_reason(raw_reason), expected)

    def test_mpv_callback_passes_normalized_reason(self):
        reasons = []
        audio = AudioEngine.__new__(AudioEngine)
        audio._on_end = reasons.append

        class EndFileEvent:
            reason = 0

        audio._handle_end_file(EndFileEvent())

        self.assertEqual(reasons, ["eof"])

    @unittest.skipUnless(_MPV_AVAILABLE, "python-mpv or libmpv is unavailable")
    def test_null_output_smoke_plays_generated_wave_to_eof(self):
        completed = threading.Event()
        reasons = []

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "tiny.wav"
            sample_rate = 8000
            samples = bytearray()
            for index in range(1600):
                sample = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
                samples.extend(sample.to_bytes(2, byteorder="little", signed=True))
            with wave.open(str(audio_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes(samples)

            def on_end(reason: str) -> None:
                reasons.append(reason)
                if reason == "eof":
                    completed.set()

            audio = AudioEngine(
                on_end,
                audio_output="null",
                video_output="null",
            )
            try:
                audio.play(str(audio_path))
                self.assertTrue(completed.wait(10), "mpv did not report EOF for the generated WAV")
                self.assertIn("eof", reasons)
            finally:
                audio.close()


if __name__ == "__main__":
    unittest.main()
