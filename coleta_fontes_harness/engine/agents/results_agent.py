from __future__ import annotations
import sqlite3, time
from typing import Any, Dict, List, Optional

class ResultsAgent:
    def __init__(self, db_path: str = "aura_quant_x.db") -> None:
        self.db_path = db_path
        self._ensure()

    def _ensure(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS paper_trades ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT, predicted_corners REAL, "
            "decision TEXT, created_at REAL, labeled INTEGER DEFAULT 0)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS outcomes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER, match_id TEXT, "
            "result TEXT, profit_loss REAL, feedback_processed INTEGER DEFAULT 0, "
            "odds_velocity REAL, system_snapshot TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS match_results ("
            "match_id TEXT PRIMARY KEY, final_corners REAL, source TEXT, ts REAL)"
        )
        # ensure labeled column on existing tables
        try:
            cur.execute("ALTER TABLE paper_trades ADD COLUMN labeled INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE paper_trades ADD COLUMN predicted_corners REAL")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE paper_trades ADD COLUMN match_id TEXT")
        except Exception:
            pass
        conn.commit(); conn.close()

    def ingest_final_result(self, match_id: str, final_corners: float, source: str = "api") -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO match_results (match_id, final_corners, source, ts) VALUES (?,?,?,?)",
            (match_id, float(final_corners), source, time.time()),
        )
        conn.commit(); conn.close()

    def auto_label_day(self) -> Dict[str, Any]:
        self._ensure()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(paper_trades)")
        cols = {r[1] for r in cur.fetchall()}
        if not cols:
            conn.close()
            return {"labeled": 0, "scanned": 0}
        try:
            if "labeled" in cols:
                cur.execute("SELECT id, match_id, predicted_corners FROM paper_trades WHERE COALESCE(labeled,0)=0")
            else:
                cur.execute("SELECT id, match_id, predicted_corners FROM paper_trades")
            trades = cur.fetchall()
        except Exception:
            trades = []
        labeled = 0
        # V23 audit: 1 query for all match_ids instead of N+1
        match_ids = list({str(m) for _, m, _ in trades if m is not None})
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
        for trade_id, match_id, predicted in trades:
            final_c = results_map.get(str(match_id))
            if final_c is None:
                continue
            pred = float(predicted or 0)
            result = "Acertou" if abs(final_c - pred) <= 1.5 else "Errou"
            try:
                cur.execute(
                    "INSERT INTO outcomes (trade_id, match_id, result, profit_loss, feedback_processed) VALUES (?,?,?,?,1)",
                    (trade_id, str(match_id), result, 1.0 if result == "Acertou" else -1.0),
                )
            except Exception:
                pass
            try:
                cur.execute("UPDATE paper_trades SET labeled = 1 WHERE id = ?", (trade_id,))
            except Exception:
                pass
            labeled += 1
        conn.commit(); conn.close()
        return {"labeled": labeled, "scanned": len(trades)}

    def run_nightly(self, simulated_results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if simulated_results:
            for r in simulated_results:
                self.ingest_final_result(str(r["match_id"]), float(r["final_corners"]), r.get("source", "sim"))
        return self.auto_label_day()

if __name__ == "__main__":
    ag = ResultsAgent("aura_quant_local.db")
    print(ag.auto_label_day())
