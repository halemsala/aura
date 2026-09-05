#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Budget / FinOps guardrails per run, agent hour, daily cost."""
from __future__ import annotations
import sqlite3, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

@dataclass
class BudgetConfig:
    max_tokens_per_run: int = 50_000
    max_tokens_per_agent_per_hour: int = 200_000
    max_tool_calls_per_run: int = 30
    max_cost_usd_per_day: float = 10.0
    token_cost_per_1k: Dict[str, float] = field(default_factory=lambda: {
        "ollama": 0.0, "llama3.2:3b": 0.0, "gpt-4o-mini": 0.00015, "gpt-4o": 0.005
    })

class BudgetGuard:
    def __init__(self, db_path: str, config: BudgetConfig | None = None):
        self.db_path = str(db_path)
        self.config = config or BudgetConfig()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._run: Dict[str, dict] = {}
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, run_id TEXT, agent TEXT, model TEXT,
                tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, tool TEXT)""")
            conn.commit()

    def check(self, run_id: str, agent: str, model: str, est_tokens: int) -> Tuple[bool, str]:
        run = self._run.setdefault(run_id, {"tokens": 0, "tool_calls": 0})
        if run["tokens"] + est_tokens > self.config.max_tokens_per_run:
            return False, "run_token_cap"
        if run["tool_calls"] >= self.config.max_tool_calls_per_run:
            return False, "run_tool_cap"
        hour_ago = time.time() - 3600
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in+tokens_out),0) FROM usage WHERE agent=? AND ts>?",
                (agent, hour_ago),
            ).fetchone()
            agent_hourly = row[0] if row else 0
            if agent_hourly + est_tokens > self.config.max_tokens_per_agent_per_hour:
                return False, "agent_hourly_cap"
            day_ago = time.time() - 86400
            row = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage WHERE ts>?", (day_ago,)).fetchone()
            daily = row[0] if row else 0.0
        rate = self.config.token_cost_per_1k.get(model, 0.0)
        est_cost = (est_tokens / 1000.0) * rate
        if daily + est_cost > self.config.max_cost_usd_per_day:
            return False, "daily_cost_cap"
        return True, "ok"

    def record(self, run_id: str, agent: str, model: str, tokens_in: int, tokens_out: int, tool: str = "") -> None:
        rate = self.config.token_cost_per_1k.get(model, 0.0)
        cost = ((tokens_in + tokens_out) / 1000.0) * rate
        run = self._run.setdefault(run_id, {"tokens": 0, "tool_calls": 0})
        run["tokens"] += tokens_in + tokens_out
        run["tool_calls"] += 1
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO usage (ts, run_id, agent, model, tokens_in, tokens_out, cost_usd, tool) VALUES (?,?,?,?,?,?,?,?)",
                (time.time(), run_id, agent, model, tokens_in, tokens_out, cost, tool),
            )
            conn.commit()

if __name__ == "__main__":
    import tempfile
    g = BudgetGuard(str(Path(tempfile.gettempdir()) / "budget.db"))
    ok, msg = g.check("r1", "diag", "ollama", 100)
    print(ok, msg)
    g.record("r1", "diag", "ollama", 50, 50)
