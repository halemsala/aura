# Itens 52, 84 — notificar só BUY aprovado + cap por hora
from __future__ import annotations
import time
from collections import deque
from typing import Deque


class NotifyPolicy:
    def __init__(self, max_per_hour: int = 6):
        self.max_per_hour = max_per_hour
        self._times: Deque[float] = deque()

    def allow(self, signal: str, approved: bool) -> bool:
        if not approved or signal == "HOLD":
            return False
        now = time.time()
        while self._times and now - self._times[0] > 3600:
            self._times.popleft()
        if len(self._times) >= self.max_per_hour:
            return False
        self._times.append(now)
        return True


_default = NotifyPolicy()


def should_notify(signal: str, approved: bool, policy: NotifyPolicy | None = None) -> bool:
    return (policy or _default).allow(signal, approved)
