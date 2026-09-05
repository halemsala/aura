# engine/infra/duckdb_analytics.py
from __future__ import annotations
import duckdb
from pathlib import Path
from typing import Any, List, Optional

class DuckDBAnalytics:
    def __init__(self, db_path: str = "aura_analytics.duckdb"):
        self.db_path = db_path
        self.con = duckdb.connect(db_path)
        self.con.execute("INSTALL json; LOAD json;")
        self.con.execute("INSTALL parquet; LOAD parquet;")

    def query_jsonl(self, path: str, sql: str) -> List[Any]:
        p = Path(path).as_posix()
        return self.con.execute(sql.replace("{path}", p)).fetchall()

    def ingest_telemetry_jsonl(self, path: str, table: str = "telemetry") -> int:
        p = Path(path).as_posix()
        self.con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_json_auto('{p}')")
        return self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def backtest_join(self, telemetry_path: str, outcomes_path: str) -> Any:
        t = Path(telemetry_path).as_posix()
        o = Path(outcomes_path).as_posix()
        return self.con.execute(f"""
            SELECT t.*, o.result, o.profit_loss
            FROM read_json_auto('{t}') t
            LEFT JOIN read_json_auto('{o}') o ON t.match_id = o.match_id
        """).fetchdf()

    def close(self):
        self.con.close()
