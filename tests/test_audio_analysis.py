import math
import unittest

from entropy.gui.audio_analysis import envelope_from_samples


class AudioEnvelopeTests(unittest.TestCase):
    def test_envelope_is_normalized_and_includes_bass_band(self):
        sample_rate = 1000
        bass_samples = [0.8 * math.sin(2 * math.pi * 50 * index / sample_rate) for index in range(4000)]
        treble_samples = [0.8 * math.sin(2 * math.pi * 350 * index / sample_rate) for index in range(4000)]
        bass_envelope = envelope_from_samples(bass_samples, sample_rate=sample_rate)
        treble_envelope = envelope_from_samples(treble_samples, sample_rate=sample_rate)
        self.assertEqual(len(bass_envelope), 100)
        self.assertAlmostEqual(max(amplitude for amplitude, _bass in bass_envelope), 1.0)
        self.assertGreater(
            sum(bass for _amplitude, bass in bass_envelope) / len(bass_envelope),
            sum(bass for _amplitude, bass in treble_envelope) / len(treble_envelope),
        )

    def test_silence_has_zero_height(self):
        self.assertEqual(envelope_from_samples([0.0] * 100), [(0.0, 0.0)] * 3)


if __name__ == "__main__":
    unittest.main()