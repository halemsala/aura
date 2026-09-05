# Item 47 — cache de frame idêntico (pula inferência)
from __future__ import annotations
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple


class FrameCache:
    def __init__(self, ttl_seconds: float = 3.0):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, str, Dict[str, Any]]] = {}

    def _hash(self, fixture_id: str, stats: Dict[str, Any]) -> str:
        blob = json.dumps({"f": fixture_id, "s": stats}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, fixture_id: str, stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        h = self._hash(fixture_id, stats)
        item = self._store.get(fixture_id)
        if not item:
            return None
        ts, prev_h, payload = item
        if prev_h == h and (time.time() - ts) <= self.ttl:
            return dict(payload)
        return None

    def set(self, fixture_id: str, stats: Dict[str, Any], result: Dict[str, Any]):
        h = self._hash(fixture_id, stats)
        self._store[fixture_id] = (time.time(), h, dict(result))
