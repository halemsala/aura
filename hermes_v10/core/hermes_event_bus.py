#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Event Bus — SQLite WAL + hash-chain audit + sync pub/sub."""
from __future__ import annotations
import hashlib, json, sqlite3, threading, time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

class EventBus:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # recreate if corrupt empty/non-db
        p = Path(self.db_path)
        if p.exists() and p.stat().st_size > 0:
            try:
                c = sqlite3.connect(self.db_path, timeout=10)
                c.execute("SELECT 1 FROM sqlite_master LIMIT 1")
                c.close()
            except sqlite3.DatabaseError:
                p.unlink(missing_ok=True)
                for suffix in ("-wal", "-shm"):
                    Path(str(p) + suffix).unlink(missing_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL,
                    event_type TEXT,
                    payload TEXT,
                    prev_hash TEXT
                )""")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL,
                    event_type TEXT,
                    payload TEXT,
                    prev_hash TEXT
                )
            """)
            conn.commit()

    def subscribe(self, event_type: str, callback: Callable[[dict], Any]) -> None:
        self.subscribers[event_type].append(callback)

    def publish(self, event_type: str, payload: dict) -> int:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT payload FROM event_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = hashlib.sha256((row[0] if row else "GENESIS").encode()).hexdigest()
                payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                cur = conn.execute(
                    "INSERT INTO event_log (ts, event_type, payload, prev_hash) VALUES (?, ?, ?, ?)",
                    (time.time(), event_type, payload_str, prev_hash),
                )
                conn.commit()
                eid = int(cur.lastrowid)
        for cb in list(self.subscribers.get(event_type, [])) + list(self.subscribers.get("*", [])):
            try:
                cb(payload)
            except Exception as e:
                print(f"[event_bus] subscriber error: {e}")
        return eid

    def recent(self, limit: int = 20) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, event_type, payload, prev_hash FROM event_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r[0], "ts": r[1], "event_type": r[2],
                "payload": json.loads(r[3]), "prev_hash": r[4],
            })
        return list(reversed(out))

if __name__ == "__main__":
    import os, tempfile
    p = Path(tempfile.gettempdir()) / "hermes_event_test.db"
    bus = EventBus(str(p))
    bus.publish("test", {"ok": True})
    print(json.dumps(bus.recent(5), indent=2))
