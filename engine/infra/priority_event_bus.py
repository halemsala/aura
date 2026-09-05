# engine/infra/priority_event_bus.py
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, Optional

PRIORITY_CRITICAL = 0
PRIORITY_NORMAL = 5
PRIORITY_BACKGROUND = 10

@dataclass(order=True)
class PriorityEvent:
    priority: int
    ts: float = field(compare=False, default_factory=time.time)
    name: str = field(compare=False, default="")
    data: Dict[str, Any] = field(compare=False, default_factory=dict)

class PriorityEventBus:
    def __init__(self) -> None:
        self._q: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._handlers: Dict[str, Callable[[PriorityEvent], Awaitable[None]]] = {}
        self._running = False

    def subscribe(self, name: str, handler: Callable[[PriorityEvent], Awaitable[None]]) -> None:
        self._handlers[name] = handler

    async def publish(self, priority: int, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        await self._q.put(PriorityEvent(priority=priority, name=name, data=data or {}))

    def publish_nowait(self, priority: int, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._q.put_nowait(PriorityEvent(priority=priority, name=name, data=data or {}))

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            event = await self._q.get()
            handler = self._handlers.get(event.name)
            if handler is not None:
                try:
                    await handler(event)
                except Exception:
                    pass
            else:
                await asyncio.sleep(0)
            self._q.task_done()

    def stop(self) -> None:
        self._running = False

    def qsize(self) -> int:
        return self._q.qsize()

BUS = PriorityEventBus()
