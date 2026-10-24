"""History-aware weighted selection for Entropy shuffle."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Sequence
from typing import Any

TEMPERATURE = 1.25
RECENT_TRACK_COOLDOWN = 4
SKIP_PRIOR_PLAYS = 5
SKIP_PRIOR_RATE = 0.20
SKIP_PENALTY = 4.0


def track_weight(track: dict[str, Any], temperature: float = TEMPERATURE) -> float:
    day = int(track.get("plays_day", 0))
    week = int(track.get("plays_week", 0))
    month = int(track.get("plays_month", 0))
    effective_skips = max(0.0, float(track.get("decayed_skip_count", track.get("skip_count", 0))))
    completed_plays = max(0, int(track.get("play_count", 0)))
    smoothed_skip_rate = (effective_skips + SKIP_PRIOR_RATE * SKIP_PRIOR_PLAYS) / (
        completed_plays + SKIP_PRIOR_PLAYS
    )
    play_pressure = day * 5 + week * 2 + month * 0.5
    skip_pressure = max(0.0, smoothed_skip_rate - SKIP_PRIOR_RATE)
    raw_weight = 1.0 / ((1.0 + play_pressure) * (1.0 + SKIP_PENALTY * skip_pressure))
    return raw_weight ** (1.0 / max(0.1, temperature))


def weight_percentages(tracks: Sequence[dict[str, Any]]) -> dict[int, float]:
    weights = [track_weight(track) for track in tracks]
    total = sum(weights)
    if total == 0:
        return {int(track["id"]): 0.0 for track in tracks}
    return {int(track["id"]): weight / total * 100 for track, weight in zip(tracks, weights)}


class EntropyScheduler:
    def __init__(self, rng: random.Random | None = None, cooldown: int = RECENT_TRACK_COOLDOWN) -> None:
        self._rng = rng or random.Random()
        self.cooldown = max(0, cooldown)

    def eligible_tracks(
        self,
        tracks: Sequence[dict[str, Any]],
        current_id: int | None = None,
        recent_ids: Sequence[int] = (),
    ) -> list[dict[str, Any]]:
        available = [track for track in tracks if int(track["id"]) != current_id]
        if not available:
            return list(tracks)
        recent = list(dict.fromkeys(int(track_id) for track_id in recent_ids if track_id != current_id))
        for cooldown in range(min(self.cooldown, len(recent)), -1, -1):
            excluded = set(recent[-cooldown:]) if cooldown else set()
            candidates = [track for track in available if int(track["id"]) not in excluded]
            if candidates:
                return candidates
        return available

    def choose(
        self,
        tracks: Sequence[dict[str, Any]],
        current_id: int | None = None,
        recent_ids: Sequence[int] = (),
    ) -> dict[str, Any] | None:
        candidates = self.eligible_tracks(tracks, current_id, recent_ids)
        if not candidates:
            return None
        return self._rng.choices(candidates, weights=[track_weight(track) for track in candidates], k=1)[0]