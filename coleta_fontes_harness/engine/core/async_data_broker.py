# engine/core/async_data_broker.py — Offload SQLite reads off the event loop
from __future__ import annotations
import asyncio
import sqlite3
from typing import Any

try:
    from engine.core.hyper_cache_v23 import GlobalHyperCache
except Exception:
    from core.hyper_cache_v23 import GlobalHyperCache  # type: ignore


class AsyncDataBroker:
    """Read-only broker: RAM cache first, then asyncio.to_thread for SQLite."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._cache = GlobalHyperCache

    def _sync_raw_query(self, query: str, params: tuple = ()) -> list[dict]:
        # Read-only URI reduces writer lock pressure
        uri = f"file:{self._db_path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        except Exception:
            conn = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    async def fetch_state(self, fixture_id: str) -> dict:
        cache_key = f"state:{fixture_id}"
        hit = self._cache.get(cache_key)
        if hit is not None:
            return hit
        query = "SELECT * FROM fixture_states WHERE id = ? LIMIT 1"
        try:
            result = await asyncio.to_thread(self._sync_raw_query, query, (fixture_id,))
        except Exception:
            return {}
        if result:
            state = result[0]
            self._cache.set(cache_key, state)
            return state
        return {}

    async def invalidate_state(self, fixture_id: str) -> None:
        self._cache.invalidate(f"state:{fixture_id}")
