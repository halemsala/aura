#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Causal lineage spans (stdlib SQLite WAL) — OTel-shaped without OTel deps."""
from __future__ import annotations
import json, sqlite3, time, uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

@dataclass
class Span:
    span_id: str
    parent_id: Optional[str]
    trace_id: str
    name: str
    kind: str
    start_ts: float
    end_ts: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[dict] = field(default_factory=list)

class LineageTracer:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._stack: List[Span] = []
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY, trace_id TEXT, parent_id TEXT,
                name TEXT, kind TEXT, start_ts REAL, end_ts REAL,
                attributes TEXT, events TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON spans(trace_id)")
            conn.commit()

    @contextmanager
    def span(self, name: str, kind: str = "tool", **attrs) -> Generator[Span, None, None]:
        trace_id = self._stack[0].trace_id if self._stack else uuid.uuid4().hex
        parent_id = self._stack[-1].span_id if self._stack else None
        sp = Span(uuid.uuid4().hex[:16], parent_id, trace_id, name, kind, time.time(), attributes=dict(attrs))
        self._stack.append(sp)
        try:
            yield sp
        except Exception as e:
            sp.events.append({"ts": time.time(), "event": "error", "error": str(e)})
            raise
        finally:
            sp.end_ts = time.time()
            self._stack.pop()
            self._persist(sp)

    def _persist(self, sp: Span) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?)",
                (sp.span_id, sp.trace_id, sp.parent_id, sp.name, sp.kind,
                 sp.start_ts, sp.end_ts, json.dumps(sp.attributes), json.dumps(sp.events)),
            )
            conn.commit()

    def trace(self, trace_id: str) -> List[Span]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT span_id,parent_id,trace_id,name,kind,start_ts,end_ts,attributes,events FROM spans WHERE trace_id=? ORDER BY start_ts",
                (trace_id,),
            ).fetchall()
        return [
            Span(r[0], r[1], r[2], r[3], r[4], r[5], r[6], json.loads(r[7] or "{}"), json.loads(r[8] or "[]"))
            for r in rows
        ]

    def explain_decision(self, trace_id: str, decision_span_id: str) -> dict:
        spans = self.trace(trace_id)
        by_id = {s.span_id: s for s in spans}
        chain = []
        cur = by_id.get(decision_span_id)
        while cur:
            chain.append({"span": cur.name, "kind": cur.kind, "attrs": cur.attributes})
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        return {"trace_id": trace_id, "decision": decision_span_id, "causal_chain": list(reversed(chain))}

if __name__ == "__main__":
    import tempfile
    t = LineageTracer(str(Path(tempfile.gettempdir()) / "lin.db"))
    with t.span("dispatch", kind="agent", action="status") as root:
        with t.span("system_status", kind="tool") as child:
            child.attributes["ok"] = True
        decision_id = root.span_id
        tid = root.trace_id
    print(json.dumps(t.explain_decision(tid, decision_id), indent=2))
