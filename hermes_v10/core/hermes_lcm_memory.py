#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lossless Context Memory — SQLite DAG of messages."""
from __future__ import annotations
import json, sqlite3, time
from pathlib import Path
from typing import Any, Dict, List, Optional

class LosslessContextMemory:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER,
                    ts REAL,
                    role TEXT,
                    content TEXT,
                    raw TEXT,
                    FOREIGN KEY(parent_id) REFERENCES messages(id)
                )
            """)
            conn.commit()

    def add(self, role: str, content: str, parent_id: Optional[int] = None, raw: Optional[dict] = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (parent_id, ts, role, content, raw) VALUES (?, ?, ?, ?, ?)",
                (parent_id, time.time(), role, content, json.dumps(raw or {}, ensure_ascii=False)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def context(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, parent_id, role, content FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "parent_id": r[1], "role": r[2], "content": r[3]}
            for r in reversed(rows)
        ]

if __name__ == "__main__":
    import tempfile
    m = LosslessContextMemory(str(Path(tempfile.gettempdir()) / "lcm_test.db"))
    m.add("user", "hello")
    m.add("assistant", "hi", parent_id=1)
    print(m.context())
