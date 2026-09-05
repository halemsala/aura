from __future__ import annotations

# engine/core/hyper_cache_v23.py — Lock-free reads, monotonic_ns TTL, lazy eviction
"""ULTRA-CACHE: zero-contention reads for hot paths. Optional alternative to TTLCache."""
import time
from typing import Any, Callable, Optional


class HyperCacheV23:
    __slots__ = ("_store", "_ttl_ns", "_maxsize")

    def __init__(self, maxsize: int = 4096, ttl_seconds: float = 30.0):
        self._store: dict[str, tuple[int, Any]] = {}
        self._ttl_ns = int(float(ttl_seconds) * 1_000_000_000)
        self._maxsize = int(maxsize)

    def get(self, key: str, default: Any = None, factory: Optional[Callable[[], Any]] = None) -> Any:
        now_ns = time.monotonic_ns()
        entry = self._store.get(key)
        if entry is not None:
            ts, val = entry
            if (now_ns - ts) <= self._ttl_ns:
                return val
            self._store.pop(key, None)
        if factory is not None:
            val = factory()
            self.set(key, val)
            return val
        return default

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._maxsize and key not in self._store:
            self._evict_oldest()
        self._store[key] = (time.monotonic_ns(), value)

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k][0])
        self._store.pop(oldest_key, None)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear_expired(self) -> int:
        now_ns = time.monotonic_ns()
        expired = [k for k, (ts, _) in self._store.items() if (now_ns - ts) > self._ttl_ns]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)

    def __contains__(self, key: str) -> bool:
        return self.get(key, sentinel := object()) is not sentinel

    def __len__(self) -> int:
        return len(self._store)


GlobalHyperCache = HyperCacheV23(maxsize=8192, ttl_seconds=15.0)
