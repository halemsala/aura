from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from time import monotonic_ns
from typing import Optional

@dataclass(frozen=True)
class FixtureState:
    fixture_id: str
    version: int
    state_hash: str
    snapshot: dict
    analysis: Optional[dict]
    created_ns: int

class FixtureStateStore:
    def __init__(self, max_items: int = 128) -> None:
        self._lock = RLock()
        self._items = OrderedDict()
        self._max_items = max_items

    def put(self, fixture_id: str, version: int, state_hash: str, snapshot: dict, analysis: Optional[dict] = None) -> FixtureState:
        item = FixtureState(str(fixture_id), int(version), state_hash, snapshot, analysis, monotonic_ns())
        with self._lock:
            self._items.pop(str(fixture_id), None)
            self._items[str(fixture_id)] = item
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)
        return item

    def get(self, fixture_id: str) -> Optional[FixtureState]:
        with self._lock:
            item = self._items.get(str(fixture_id))
            if item is not None:
                self._items.move_to_end(str(fixture_id))
            return item

    def remove(self, fixture_id: str) -> None:
        with self._lock:
            self._items.pop(str(fixture_id), None)

fixture_state_store = FixtureStateStore()
