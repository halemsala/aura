# engine/infra/dynamic_yield.py
from __future__ import annotations
import os
import threading
import time
from typing import Optional

class LiveMatchYieldController:
    """When match is live (0-90), background learners yield CPU."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live = False
        self._minute: float = -1.0
        self._halftime = False

    def update_clock(self, minute: float, period: str = "") -> None:
        with self._lock:
            self._minute = float(minute)
            self._halftime = period.lower() in ("ht", "half", "halftime")
            self._live = (0.0 <= self._minute <= 90.0) and not self._halftime

    @property
    def is_live(self) -> bool:
        with self._lock:
            return self._live

    def background_sleep_seconds(self) -> float:
        with self._lock:
            if self._live:
                return 8.0
            if self._halftime:
                return 1.0
            return 0.5

    def apply_nice(self) -> None:
        try:
            if self.is_live:
                os.nice(19)
        except Exception:
            pass

    def yield_if_live(self) -> None:
        time.sleep(self.background_sleep_seconds())

YIELD = LiveMatchYieldController()
