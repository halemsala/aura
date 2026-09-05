#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Circuit breaker + kill switch (soft/hard)."""
from __future__ import annotations
import os, signal, time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Deque, List, Optional, Tuple

@dataclass
class BreakerState:
    failures: Deque[Tuple[float, str]] = field(default_factory=lambda: deque(maxlen=100))
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    opened_at: float = 0.0
    trip_count: int = 0

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, window_seconds: float = 60.0, cooldown_seconds: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window = window_seconds
        self.cooldown = cooldown_seconds
        self._state = BreakerState()
        self._lock = Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.time()
            if self._state.state == "OPEN":
                if now - self._state.opened_at > self.cooldown:
                    self._state.state = "HALF_OPEN"
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state.state == "HALF_OPEN":
                self._state.state = "CLOSED"
                self._state.failures.clear()

    def record_failure(self, reason: str = "") -> None:
        with self._lock:
            now = time.time()
            self._state.failures.append((now, reason))
            recent = [f for f in self._state.failures if now - f[0] <= self.window]
            if len(recent) >= self.failure_threshold and self._state.state != "OPEN":
                self._state.state = "OPEN"
                self._state.opened_at = now
                self._state.trip_count += 1

    def status(self) -> dict:
        return {"name": self.name, "state": self._state.state, "trips": self._state.trip_count}

class KillSwitch:
    def __init__(self, root: str, soft_file: str = "hitl_queue/KILL_SOFT", hard_file: str = "hitl_queue/KILL_HARD"):
        self.root = Path(root)
        self.soft = self.root / soft_file
        self.hard = self.root / hard_file
        self.soft.parent.mkdir(parents=True, exist_ok=True)
        try:
            signal.signal(signal.SIGTERM, self._sig_hard)
        except Exception:
            pass

    def _sig_hard(self, *_):
        self.hard.write_text("SIGTERM", encoding="utf-8")
        os._exit(130)

    def check(self) -> Optional[str]:
        if self.hard.exists():
            return "HARD_KILL"
        if self.soft.exists():
            return "SOFT_KILL_ACTIVE"
        return None

    def soft_kill(self) -> None:
        self.soft.write_text(f"soft {time.time()}", encoding="utf-8")

    def clear_soft(self) -> None:
        if self.soft.exists():
            self.soft.unlink()

if __name__ == "__main__":
    b = CircuitBreaker("test", failure_threshold=3, window_seconds=10)
    for i in range(3):
        b.record_failure(f"e{i}")
    print(b.status(), "allow", b.allow())
