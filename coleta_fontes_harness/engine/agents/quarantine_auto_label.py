from __future__ import annotations
import sqlite3
import time
from typing import Any, Dict, List, Optional

class QuarantineAutoLabel:
    EDGE_HIGH = 0.2

    def __init__(self, db_path: str = "aura_quant_x.db") -> None:
        self.db_path = db_path
        self._ensure()

    def _ensure(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS quarantine_suggested_labels ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER, match_id TEXT, "
            "suggested_result TEXT, predicted_edge REAL, anomaly_flag INTEGER DEFAULT 0, "
            "reason TEXT, ts REAL, applied INTEGER DEFAULT 0)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS match_results ("
            "match_id TEXT PRIMARY KEY, final_corners REAL, source TEXT, ts REAL)"
        )
        conn.commit(); conn.close()

    def suggest_labels(self) -> Dict[str, Any]:
        self._ensure()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        inserted = 0
        anomalies = 0
        try:
            cur.execute(
                "SELECT id, match_id, COALESCE(predicted_corners,0), COALESCE(decision,'') "
                "FROM paper_trades WHERE COALESCE(labeled,0)=0"
            )
            trades = cur.fetchall()
        except Exception:
            trades = []
        # V23 audit 4.4: batch lookup instead of N+1
        match_ids = list({str(m) for _, m, _, _ in trades if m is not None})
        results_map: Dict[str, float] = {}
        if match_ids:
            placeholders = ",".join("?" * len(match_ids))
            try:
                cur.execute(
                    f"SELECT match_id, final_corners FROM match_results WHERE match_id IN ({placeholders})",
                    match_ids,
                )
                for mid, fc in cur.fetchall():
                    results_map[str(mid)] = float(fc)
            except Exception:
                results_map = {}
        for trade_id, match_id, predicted, decision in trades:
            final_c = results_map.get(str(match_id))
            if final_c is None:
                continue
            pred = float(predicted or 0)
            suggested = "Acertou" if abs(final_c - pred) <= 1.5 else "Errou"
            # edge proxy from decision confidence store if present
            edge = 0.0
            try:
                cur.execute(
                    "SELECT calculated_edge FROM paper_trades WHERE id=? AND calculated_edge IS NOT NULL",
                    (trade_id,),
                )
                er = cur.fetchone()
                if er:
                    edge = float(er[0])
            except Exception:
                edge = 0.25 if decision == "BUY_CORNER" else 0.05
            anomaly = 1 if (edge > self.EDGE_HIGH and suggested == "Errou") else 0
            reason = "high_edge_but_miss" if anomaly else "ok"
            if anomaly:
                anomalies += 1
            cur.execute(
                "INSERT INTO quarantine_suggested_labels "
                "(trade_id, match_id, suggested_result, predicted_edge, anomaly_flag, reason, ts, applied) "
                "VALUES (?,?,?,?,?,?,?,0)",
                (trade_id, str(match_id), suggested, edge, anomaly, reason, time.time()),
            )
            inserted += 1
            # NEVER write directly to outcomes here
        conn.commit(); conn.close()
        return {"quarantined": inserted, "anomaly_flags": anomalies}

if __name__ == "__main__":
    print(QuarantineAutoLabel("aura_quant_local.db").suggest_labels())
