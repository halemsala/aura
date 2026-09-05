from __future__ import annotations
from enum import Enum
from typing import Callable, Iterable

class RecoveryState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"

class RecoveryController:
    def __init__(self, max_attempts: int = 2) -> None:
        self.state = RecoveryState.HEALTHY
        self.max_attempts = max_attempts

    def recover(self, strategies: Iterable[Callable[[], bool]]) -> bool:
        self.state = RecoveryState.RECOVERING
        for attempt, strategy in enumerate(strategies, start=1):
            if attempt > self.max_attempts:
                break
            try:
                if strategy():
                    self.state = RecoveryState.HEALTHY
                    return True
            except Exception:
                continue
        self.state = RecoveryState.QUARANTINED
        return False
