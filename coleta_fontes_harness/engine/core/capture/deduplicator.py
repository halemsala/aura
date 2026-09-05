from __future__ import annotations
from collections import OrderedDict
from threading import RLock

class StateDeduplicator:
    def __init__(self, max_entries: int = 4096) -> None:
        self._lock = RLock()
        self._seen = OrderedDict()
        self._max_entries = max_entries

    def accept(self, fixture_id: str, state_hash: str) -> bool:
        key = (str(fixture_id), state_hash)
        with self._lock:
            if key in self._seen:
                self._seen.move_to_end(key)
                return False
            self._seen[key] = True
            while len(self._seen) > self._max_entries:
                self._seen.popitem(last=False)
            return True

    def invalidate_fixture(self, fixture_id: str) -> None:
        with self._lock:
            for key in [k for k in self._seen if k[0] == str(fixture_id)]:
                self._seen.pop(key, None)

state_deduplicator = StateDeduplicator()
