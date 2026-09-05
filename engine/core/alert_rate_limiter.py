"""Rate limiter determinístico de alertas por chave."""
from __future__ import annotations

from collections import deque
from threading import RLock
from time import monotonic
from typing import Callable, Deque, Dict


class AlertRateLimiter:
    def __init__(self, *, max_events: int = 3, window_seconds: float = 60.0,
                 clock: Callable[[], float] = monotonic) -> None:
        if max_events < 1 or window_seconds <= 0:
            raise ValueError("limites inválidos")
        self.max_events = int(max_events)
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._events: Dict[str, Deque[float]] = {}
        self._lock = RLock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            queue = self._events.setdefault(str(key), deque())
            while queue and queue[0] <= now - self.window_seconds:
                queue.popleft()
            if len(queue) >= self.max_events:
                return False
            queue.append(now)
            return True

    def status(self, key: str) -> dict:
        now = self._clock()
        with self._lock:
            queue = self._events.get(str(key), deque())
            while queue and queue[0] <= now - self.window_seconds:
                queue.popleft()
            return {"key": str(key), "events": len(queue), "max_events": self.max_events,
                    "window_seconds": self.window_seconds}


__all__ = ["AlertRateLimiter"]
