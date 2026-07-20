"""Rate limiting and human-paced delays.

Two jobs: (1) sprinkle randomised human-like pauses between UI actions, and
(2) enforce hard ceilings on how many applications go out per run and per
rolling hour so the tool stays polite and keeps your account healthy.
"""

from __future__ import annotations

import random
import time
from collections import deque


class RateLimiter:
    def __init__(
        self,
        between_applications: tuple[float, float],
        between_actions: tuple[float, float],
        max_per_run: int,
        max_per_hour: int,
        recent_timestamps: list[float] | None = None,
    ) -> None:
        self._between_applications = between_applications
        self._between_actions = between_actions
        self._max_per_run = max_per_run
        self._max_per_hour = max_per_hour
        self._run_count = 0
        # Monotonic-ish wall-clock timestamps of recent submissions.
        self._recent: deque[float] = deque(recent_timestamps or [])

    def action_pause(self) -> None:
        time.sleep(random.uniform(*self._between_actions))

    def application_pause(self) -> None:
        time.sleep(random.uniform(*self._between_applications))

    def run_limit_reached(self) -> bool:
        return self._run_count >= self._max_per_run

    def hourly_limit_reached(self) -> bool:
        self._evict_old()
        return len(self._recent) >= self._max_per_hour

    def seconds_until_hourly_slot(self) -> float:
        self._evict_old()
        if len(self._recent) < self._max_per_hour:
            return 0.0
        oldest = self._recent[0]
        return max(0.0, 3600.0 - (time.time() - oldest))

    def record_application(self) -> None:
        self._run_count += 1
        self._recent.append(time.time())

    @property
    def run_count(self) -> int:
        return self._run_count

    def _evict_old(self) -> None:
        cutoff = time.time() - 3600.0
        while self._recent and self._recent[0] < cutoff:
            self._recent.popleft()
