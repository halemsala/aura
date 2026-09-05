# engine/core/async_db_pool.py — Auditoria Radical 1.1
from __future__ import annotations
import asyncio
import sqlite3
import threading
import queue
from typing import Any


class AsyncSQLitePool:
    """Serializa writes SQLite em thread dedicada; API async para o event loop."""

    __slots__ = ("_conn_factory", "_tx_queue", "_worker", "_loop", "_pending")

    def __init__(self, db_path: str):
        self._conn_factory = lambda: sqlite3.connect(
            db_path, check_same_thread=False, isolation_level=None
        )
        self._tx_queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(
            target=self._serialize, daemon=True, name="sqlite-serial"
        )
        self._worker.start()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[int, asyncio.Future] = {}

    def _serialize(self) -> None:
        conn = self._conn_factory()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        while True:
            item = self._tx_queue.get()
            if item is None:
                break
            fut, sql, params = item
            try:
                conn.execute("BEGIN IMMEDIATE")
                if isinstance(sql, list):
                    for s, p in zip(sql, params):
                        conn.execute(s, p)
                else:
                    conn.execute(sql, params or ())
                conn.execute("COMMIT")
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(fut.set_result, True)
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(fut.set_exception, exc)

    async def execute(self, sql: str | list[str], params: tuple | list[tuple] = ()) -> bool:
        self._loop = asyncio.get_running_loop()
        fut = self._loop.create_future()
        self._tx_queue.put((fut, sql, params))
        return await asyncio.wait_for(fut, timeout=3.0)

    def close(self) -> None:
        self._tx_queue.put(None)
        self._worker.join(timeout=5.0)
