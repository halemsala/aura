# engine/core/ttl_cache_v2.py — Auditoria Radical 1.3
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Generic, TypeVar, Optional

K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _Node(Generic[V]):
    value: V
    expiry: float


class LockFreeTTLCache(Generic[K, V]):
    """Dict nativo + lazy eviction. Sem lock global (GIL CPython)."""

    __slots__ = ("_store", "_ttl", "_maxsize", "_evict_threshold")

    def __init__(self, ttl: float, maxsize: int = 4096):
        self._store: dict[K, _Node[V]] = {}
        self._ttl = float(ttl)
        self._maxsize = int(maxsize)
        self._evict_threshold = int(maxsize * 0.85)

    def get(self, key: K) -> Optional[V]:
        node = self._store.get(key)
        if node is None:
            return None
        if time.monotonic() > node.expiry:
            self._store.pop(key, None)
            return None
        return node.value

    def set(self, key: K, value: V) -> None:
        now = time.monotonic()
        self._store[key] = _Node(value, now + self._ttl)
        if len(self._store) > self._maxsize:
            self._lazy_evict(now)

    def _lazy_evict(self, now: float) -> None:
        expired = [k for k, n in self._store.items() if n.expiry < now]
        for k in expired:
            self._store.pop(k, None)
        if len(self._store) > self._evict_threshold:
            sorted_items = sorted(self._store.items(), key=lambda x: x[1].expiry)
            excess = len(self._store) - self._evict_threshold
            for k, _ in sorted_items[:excess]:
                self._store.pop(k, None)
