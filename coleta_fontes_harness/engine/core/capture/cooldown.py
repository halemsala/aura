from __future__ import annotations
from threading import Lock
from time import monotonic

class AtomicCooldown:
    def __init__(self, cooldown_seconds: float) -> None:
        self._lock = Lock()
        self._cooldown = float(cooldown_seconds)
        self._last: dict[str, float] = {}

    def reserve(self, key: str) -> bool:
        now = monotonic()
        with self._lock:
            prev = self._last.get(key)
            if prev is not None and (now - prev) < self._cooldown:
                return False
            self._last[key] = now
            return True
