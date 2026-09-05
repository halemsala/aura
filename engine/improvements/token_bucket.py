# Token bucket adaptativo (Q-series rate / backpressure)
from __future__ import annotations
import time
from typing import Optional

class AdaptiveTokenBucket:
    def __init__(self, rate: float = 10.0, capacity: float = 20.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()
        self.consec_deny = 0

    def _refill(self):
        now = time.monotonic()
        delta = now - self.updated
        self.tokens = min(self.capacity, self.tokens + delta * self.rate)
        self.updated = now

    def allow(self, cost: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            self.consec_deny = 0
            return True
        self.consec_deny += 1
        if self.consec_deny >= 5:
            self.rate = max(1.0, self.rate * 0.85)
        return False

    def on_success(self):
        self.rate = min(self.capacity, self.rate * 1.02)
