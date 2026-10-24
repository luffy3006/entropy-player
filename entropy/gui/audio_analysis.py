"""Low-rate audio envelope extraction for the desktop waveform display."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QThread, pyqtSignal


def envelope_from_samples(samples: Iterable[float], sample_rate: int = 1000, frame_ms: int = 40) -> list[tuple[float, float]]:
    values = list(samples)
    if not values:
        return []
    frame_size = max(1, sample_rate * frame_ms // 1000)
    alpha = 1.0 - math.exp(-2.0 * math.pi * 140.0 / sample_rate)
    filtered = 0.0
    result: list[tuple[float, float]] = []
    for start in range(0, len(values), frame_size):
        frame = values[start:start + frame_size]
        square_sum = 0.0
        bass_square_sum = 0.0
        for sample in frame:
            filtered += alpha * (sample - filtered)
            square_sum += sample * sample
            bass_square_sum += filtered * filtered
        count = len(frame)
        result.append((math.sqrt(square_sum / count), math.sqrt(bass_square_sum / count)))
    scale = max((amplitude for amplitude, _bass in result), default=0.0)
    if scale <= 1e-8:
        return [(0.0, 0.0) for _ in result]
    return [(min(1.0, amplitude / scale), min(1.0, bass / scale)) for amplitude, bass in result]


class WaveformAnalysisThread(QThread):
    analyzed = pyqtSignal(int, object)

    def __init__(self, track_id: int, filepath: str, parent=None) -> None:
        super().__init__(parent)
        self.track_id = track_id
        self.filepath = filepath
        self._process: subprocess.Popen[bytes] | None = None

    def run(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None or not Path(self.filepath).is_file():
            self.analyzed.emit(self.track_id, [])
            return
        try:
            self._process = subprocess.Popen(
                [ffmpeg, "-nostdin", "-v", "error", "-i", self.filepath, "-map", "0:a:0?", "-vn",
                 "-ac", "1", "-ar", "1000", "-f", "f32le", "pipe:1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            output, _ = self._process.communicate(timeout=120)
            if self._process.returncode != 0:
                self.analyzed.emit(self.track_id, [])
                return
            samples = array.array("f")
            usable_length = len(output) - len(output) % samples.itemsize
            samples.frombytes(output[:usable_length])
            self.analyzed.emit(self.track_id, envelope_from_samples(samples))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            if self._process is not None and self._process.poll() is None:
                self._process.kill()
                self._process.communicate()
            self.analyzed.emit(self.track_id, [])
        finally:
            self._process = None

    def cancel(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
