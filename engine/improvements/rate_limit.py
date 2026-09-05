# Item 65 — rate limit local
from __future__ import annotations
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, per_fixture_interval: float = 2.0, global_per_sec: int = 10):
        self.per_fixture_interval = per_fixture_interval
        self.global_per_sec = global_per_sec
        self._last_fixture: Dict[str, float] = {}
        self._global: Deque[float] = deque()

    def allow(self, fixture_id: str) -> bool:
        now = time.time()
        # global
        while self._global and now - self._global[0] > 1.0:
            self._global.popleft()
        if len(self._global) >= self.global_per_sec:
            return False
        # per fixture
        last = self._last_fixture.get(fixture_id, 0)
        if now - last < self.per_fixture_interval:
            return False
        self._last_fixture[fixture_id] = now
        self._global.append(now)
        return True
