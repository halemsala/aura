# engine/core/bounded_ttl_cache.py — Extreme P1 1.6
from __future__ import annotations
from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any, Optional


class BoundedTTLCache:
    def __init__(self, max_items: int = 1024):
        self.max_items = int(max_items)
        self.data: OrderedDict = OrderedDict()
        self.lock = Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: Any, default: Any = None) -> Any:
        now = monotonic()
        with self.lock:
            item = self.data.get(key)
            if item is None:
                self.misses += 1
                return default
            value, expires = item
            if expires is not None and now >= expires:
                self.data.pop(key, None)
                self.misses += 1
                return default
            self.data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: Any, value: Any, ttl_s: Optional[float] = None) -> None:
        expires = monotonic() + float(ttl_s) if ttl_s else None
        with self.lock:
            self.data[key] = (value, expires)
            self.data.move_to_end(key)
            while len(self.data) > self.max_items:
                self.data.popitem(last=False)
                self.evictions += 1

    def stats(self) -> dict:
        with self.lock:
            total = self.hits + self.misses
            return {
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "size": len(self.data),
                "hit_rate": (self.hits / total) if total else 0.0,
            }
