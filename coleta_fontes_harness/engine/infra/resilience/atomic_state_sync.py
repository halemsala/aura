from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Optional

class AtomicStateSync:
    """Async-compatible context manager: SQLite commit only if LanceDB add succeeds."""
    def __init__(self, db_path: str = "aura_quant_x.db", lance_uri: str = "./lancedb_aura", table: str = "kb_feedback") -> None:
        self.db_path = db_path
        self.lance_uri = lance_uri
        self.table = table
        self._conn: Optional[sqlite3.Connection] = None
        self._db = None

    async def __aenter__(self) -> "AtomicStateSync":
        self._conn = sqlite3.connect(self.db_path, timeout=10.0)
        self._conn.execute("BEGIN")
        try:
            import lancedb
            self._db = lancedb.connect(self.lance_uri)
        except Exception:
            self._db = None
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._conn is None:
            return
        try:
            if exc_type is not None:
                self._conn.rollback()
            self._conn.close()
        except Exception:
            pass
        self._conn = None

    async def execute_trade_insert(self, query: str, params: tuple, vector_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if self._conn is None:
            raise RuntimeError("not in context")
        try:
            self._conn.execute(query, params)
            if vector_data and self._db is not None:
                names = self._db.table_names()
                if self.table not in names:
                    self._db.create_table(self.table, data=vector_data, mode="overwrite")
                else:
                    self._db.open_table(self.table).add(vector_data)
            elif vector_data and self._db is None:
                self._conn.rollback()
                return {"ok": False, "error": "lancedb_unavailable", "rolled_back": True}
            self._conn.commit()
            return {"ok": True}
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            return {"ok": False, "error": str(e), "rolled_back": True}
