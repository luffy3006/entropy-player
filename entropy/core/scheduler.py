"""History-aware weighted selection for Entropy shuffle."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any


def track_weight(track: dict[str, Any]) -> float:
    day = int(track.get("plays_day", 0))
    week = int(track.get("plays_week", 0))
    month = int(track.get("plays_month", 0))
    skips = int(track.get("skip_count", 0))
    return 1.0 / ((1 + day * 5 + week * 2 + month * 0.5) * (1 + skips * 1.5))


def weight_percentages(tracks: Sequence[dict[str, Any]]) -> dict[int, float]:
    weights = [track_weight(track) for track in tracks]
    total = sum(weights)
    if total == 0:
        return {int(track["id"]): 0.0 for track in tracks}
    return {int(track["id"]): weight / total * 100 for track, weight in zip(tracks, weights)}


class EntropyScheduler:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def choose(self, tracks: Sequence[dict[str, Any]], current_id: int | None = None) -> dict[str, Any] | None:
        candidates = [track for track in tracks if int(track["id"]) != current_id]
        if not candidates:
            candidates = list(tracks)
        if not candidates:
            return None
        return self._rng.choices(candidates, weights=[track_weight(track) for track in candidates], k=1)[0]