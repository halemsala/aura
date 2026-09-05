"""Dead Man's Switch observacional; não mata nem reinicia processos."""
from __future__ import annotations

from threading import RLock
from time import time
from typing import Callable, Dict


class DeadMansSwitch:
    def __init__(self, *, timeout: float = 15.0, clock: Callable[[], float] = time) -> None:
        self.timeout = float(timeout)
        self._clock = clock
        self._last_beat = self._clock()
        self._lock = RLock()

    def beat(self) -> None:
        with self._lock:
            self._last_beat = self._clock()

    def status(self) -> Dict[str, object]:
        with self._lock:
            age = max(0.0, self._clock() - self._last_beat)
            return {"healthy": age <= self.timeout, "age_seconds": age,
                    "timeout": self.timeout, "action": "observe_only",
                    "restart_enabled": False, "kill_enabled": False}

    def start_monitoring(self) -> bool:
        return False


DEAD_SWITCH = DeadMansSwitch()
__all__ = ["DeadMansSwitch", "DEAD_SWITCH"]
