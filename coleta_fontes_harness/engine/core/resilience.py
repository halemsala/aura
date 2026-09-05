from __future__ import annotations
import asyncio
import logging
from enum import Enum
from typing import Any, Callable, List, Optional

logger = logging.getLogger("aura.resilience")


class DegradationLevel(Enum):
    NORMAL = 0
    REDUCED = 1
    MINIMAL = 2
    SAFE_MODE = 3


class ResilienceController:
    def __init__(self, governor: Any = None, poll_interval: float = 5.0):
        self.level = DegradationLevel.NORMAL
        self.governor = governor
        self.poll_interval = poll_interval
        self._callbacks: List[Callable] = []

    def on_degrade(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    async def monitor(self) -> None:
        while True:
            try:
                status = {}
                if self.governor is not None and hasattr(self.governor, "status"):
                    status = self.governor.status() or {}
                if status.get("throttled") or status.get("is_throttled"):
                    await self._degrade()
                else:
                    await self._recover()
            except Exception as e:
                logger.warning("resilience monitor: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _degrade(self) -> None:
        old = self.level
        if self.level == DegradationLevel.NORMAL:
            self.level = DegradationLevel.REDUCED
        elif self.level == DegradationLevel.REDUCED:
            self.level = DegradationLevel.MINIMAL
        elif self.level == DegradationLevel.MINIMAL:
            self.level = DegradationLevel.SAFE_MODE
        if old != self.level:
            logger.warning("QoS degrade -> %s (paper_trade only)", self.level.name)
            for cb in self._callbacks:
                try:
                    r = cb(self.level)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception:
                    pass

    async def _recover(self) -> None:
        if self.level != DegradationLevel.NORMAL:
            self.level = DegradationLevel.NORMAL
            logger.info("QoS recover -> NORMAL")
            for cb in self._callbacks:
                try:
                    r = cb(self.level)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception:
                    pass


async def sqlite_retry(operation: Callable, retries: int = 3, base_delay_ms: float = 10.0) -> Any:
    import sqlite3
    for attempt in range(retries):
        try:
            return operation()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                await asyncio.sleep(base_delay_ms * (2 ** attempt) / 1000.0)
            else:
                raise
    raise RuntimeError("SQLite locked apos retries")
