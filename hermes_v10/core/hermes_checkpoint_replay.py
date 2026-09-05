#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exactly-once effects + checkpoints (anti re-execução)."""
from __future__ import annotations
import hashlib, json, sqlite3, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

@dataclass
class EffectRecord:
    effect_id: str
    action: str
    args_hash: str
    intent: str
    executed_at: float
    result_hash: str

class CheckpointStore:
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
            conn.execute("""CREATE TABLE IF NOT EXISTS effects (
                effect_id TEXT PRIMARY KEY, action TEXT, args_hash TEXT, intent TEXT,
                executed_at REAL, result_hash TEXT, prev_hash TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS checkpoints (
                cp_id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, state TEXT, created_at REAL)""")
            conn.commit()

    @staticmethod
    def effect_id(action: str, args: dict, intent: str) -> str:
        args_canon = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(f"{action}|{args_canon}|{intent}".encode()).hexdigest()[:32]

    def already_executed(self, action: str, args: dict, intent: str) -> Optional[EffectRecord]:
        eid = self.effect_id(action, args, intent)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT effect_id, action, args_hash, intent, executed_at, result_hash FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
        if row:
            return EffectRecord(*row)
        return None

    def record_effect(self, action: str, args: dict, intent: str, result: Any) -> str:
        eid = self.effect_id(action, args, intent)
        args_hash = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]
        result_hash = hashlib.sha256(str(result).encode()).hexdigest()[:16]
        with self._conn() as conn:
            prev = conn.execute("SELECT effect_id FROM effects ORDER BY executed_at DESC LIMIT 1").fetchone()
            prev_hash = prev[0] if prev else "GENESIS"
            conn.execute(
                "INSERT OR IGNORE INTO effects VALUES (?,?,?,?,?,?,?)",
                (eid, action, args_hash, intent, time.time(), result_hash, prev_hash),
            )
            conn.commit()
        return eid

    def save_checkpoint(self, agent: str, state: dict) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO checkpoints (agent, state, created_at) VALUES (?,?,?)",
                (agent, json.dumps(state, ensure_ascii=False, default=str), time.time()),
            )
            conn.commit()
            return int(cur.lastrowid)

if __name__ == "__main__":
    import tempfile
    s = CheckpointStore(str(Path(tempfile.gettempdir()) / "cp_test.db"))
    assert s.already_executed("fix", {"x": 1}, "domain") is None
    s.record_effect("fix", {"x": 1}, "domain", {"ok": True})
    assert s.already_executed("fix", {"x": 1}, "domain") is not None
    print("checkpoint_ok")
