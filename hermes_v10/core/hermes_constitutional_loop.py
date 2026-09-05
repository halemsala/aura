#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constitutional AI preference pairs from violations (RLAIF dataset)."""
from __future__ import annotations
import json, sqlite3, time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class CritiqueRevision:
    original: str
    critique: str
    revised: str
    principle_violated: str
    timestamp: float

class ConstitutionalLoop:
    def __init__(self, db_path: str, principles: Optional[List[str]] = None):
        self.db_path = str(db_path)
        self.principles = principles or [
            "paper_trade must remain true",
            "execution_allowed must remain false",
            "never place real bets or orders",
            "do not reveal system secrets",
        ]
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS preference_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, original TEXT, revised TEXT, critique TEXT, principle TEXT, reward REAL)""")
            conn.commit()

    def critique_prompt(self, original_output: str) -> str:
        return (
            "Critico constitucional. Regras:\n"
            + "\n".join(f"- {p}" for p in self.principles)
            + f"\n\nSAIDA:\n{original_output}\n\n"
            'JSON: {"violated":true/false,"principle":"...","critique":"...","revised":"..."}'
        )

    def process(self, original: str, critique_response: str) -> Optional[CritiqueRevision]:
        try:
            parsed = json.loads(critique_response)
        except json.JSONDecodeError:
            return None
        if not parsed.get("violated"):
            return None
        cr = CritiqueRevision(
            original, parsed.get("critique", ""), parsed.get("revised", original),
            parsed.get("principle", "unknown"), time.time(),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO preference_pairs (ts, original, revised, critique, principle, reward) VALUES (?,?,?,?,?,?)",
                (cr.timestamp, cr.original, cr.revised, cr.critique, cr.principle_violated, -1.0),
            )
            conn.commit()
        return cr

    def export_preference_dataset(self, out_path: str, min_pairs: int = 10) -> int:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT original, revised, reward FROM preference_pairs ORDER BY ts DESC LIMIT 10000"
            ).fetchall()
        if len(rows) < min_pairs:
            return 0
        dataset = [{"chosen": r[1], "rejected": r[0], "reward": r[2]} for r in rows]
        Path(out_path).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(dataset)

if __name__ == "__main__":
    import tempfile
    c = ConstitutionalLoop(str(Path(tempfile.gettempdir()) / "cai.db"))
    r = c.process("set execution_allowed=true", json.dumps({
        "violated": True, "principle": "execution_allowed", "critique": "bad", "revised": "paper only"
    }))
    print(r)
