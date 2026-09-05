# cascade_guard.py — previne falhas em cascata (budget de erros / cooldown global)
from __future__ import annotations
import time
from typing import Dict, Optional


class CascadeGuard:
    """
    Se N componentes falham em janela curta, entra em modo degradado global.
    """

    def __init__(self, max_failures: int = 3, window_seconds: float = 30.0, degrade_seconds: float = 60.0):
        self.max_failures = max_failures
        self.window = window_seconds
        self.degrade_seconds = degrade_seconds
        self._events: list = []
        self.degraded_until: float = 0.0

    def report_failure(self, component: str):
        now = time.time()
        self._events.append((now, component))
        self._events = [(t, c) for t, c in self._events if now - t <= self.window]
        comps = {c for t, c in self._events}
        if len(self._events) >= self.max_failures or len(comps) >= self.max_failures:
            self.degraded_until = now + self.degrade_seconds

    def is_degraded(self) -> bool:
        return time.time() < self.degraded_until

    def status(self) -> Dict:
        return {
            "degraded": self.is_degraded(),
            "recent_failures": len(self._events),
            "degraded_until": self.degraded_until,
        }


cascade_guard = CascadeGuard()
