# engine/core/experience_db.py
"""AURA QUANT-X V25 — Experience DB (aprendizado continuo, batch + WAL).

Aditivo: nao altera Poisson/Hawkes. Apenas grava/consulta snapshots historicos.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.experience_db")

try:
    from core.ttl_cache import TTLCache
except ImportError:
    from engine.core.ttl_cache import TTLCache


class ExperienceDB:
    def __init__(self, db_path: str = "engine/experience_memory.db"):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.cache = TTLCache(default_ttl_seconds=30)
        self._write_lock = threading.Lock()
        self._pending_writes: List[Tuple] = []
        self._flush_errors = 0
        self._total_flushed = 0
        self._owns_conn = False
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Conexao isolada por chamada (seguro com FastAPI + threads)."""
        try:
            from engine.data_store import get_thread_safe_conn
            conn = get_thread_safe_conn()
            self._owns_conn = False
            return conn
        except Exception:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            self._owns_conn = True
            return conn

    def _close_if_owned(self, conn: sqlite3.Connection) -> None:
        if self._owns_conn:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA busy_timeout = 5000")
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS experience_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fixture_id TEXT,
                        minute INTEGER,
                        imc REAL,
                        pressure_diff REAL,
                        attack_rate REAL,
                        cross_rate REAL,
                        is_corner INTEGER,
                        is_pre_corner INTEGER DEFAULT 0,
                        timestamp_unix INTEGER
                    )"""
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_exp_imc_minute_corner "
                    "ON experience_snapshots(imc, minute, is_corner)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_exp_fixture_ts "
                    "ON experience_snapshots(fixture_id, timestamp_unix)"
                )
                conn.commit()
            finally:
                self._close_if_owned(conn)
        except Exception as e:
            logger.error("Erro ao iniciar Experience DB: %s", e)

    def schedule_write(
        self,
        fixture_id: str,
        state: dict,
        is_corner: bool = False,
        is_pre_corner: bool = False,
    ) -> None:
        """Fila em RAM — nao bloqueia o event loop com I/O de disco."""
        minute = float(state.get("minute", 0) or 0)
        row = (
            str(fixture_id or "unknown"),
            int(minute),
            round(float(state.get("imc", 0) or 0), 2),
            round(
                float(state.get("pressure_home", 0) or 0)
                - float(state.get("pressure_away", 0) or 0),
                2,
            ),
            round(
                float(state.get("ap_5min", 0) or 0) / max(minute, 1.0),
                2,
            ),
            round(
                float(state.get("crosses_home", 0) or 0)
                + float(state.get("crosses_away", 0) or 0),
                2,
            ),
            1 if is_corner else 0,
            1 if is_pre_corner else 0,
            int(time.time()),
        )
        with self._write_lock:
            self._pending_writes.append(row)

    def flush_writes(self) -> int:
        """Gravacao em lote (timer background). Retorna quantos registros gravados."""
        with self._write_lock:
            if not self._pending_writes:
                return 0
            batch = list(self._pending_writes)
            self._pending_writes.clear()

        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                # 9 colunas = 9 placeholders (bug original tinha 10 ?)
                cursor.executemany(
                    """INSERT INTO experience_snapshots
                    (fixture_id, minute, imc, pressure_diff, attack_rate,
                     cross_rate, is_corner, is_pre_corner, timestamp_unix)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    batch,
                )
                conn.commit()
                self._total_flushed += len(batch)
                return len(batch)
            finally:
                self._close_if_owned(conn)
        except Exception as e:
            self._flush_errors += 1
            logger.error("Erro ao salvar experiencia em lote: %s", e)
            return 0

    def query_experience(self, filters: dict) -> dict:
        """
        Filtros: imc_min, imc_max, minute_min, minute_max (ou momento_max),
        is_pre_corner.
        """
        cache_key = str(sorted((filters or {}).items()))
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        try:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                query = (
                    "SELECT COUNT(*) as total_cases, "
                    "COALESCE(SUM(is_corner), 0) as corner_cases, "
                    "AVG(imc) as avg_imc "
                    "FROM experience_snapshots WHERE 1=1"
                )
                params: List[Any] = []

                if "imc_min" in filters:
                    query += " AND imc >= ?"
                    params.append(filters["imc_min"])
                if "imc_max" in filters:
                    query += " AND imc <= ?"
                    params.append(filters["imc_max"])
                if "minute_min" in filters:
                    query += " AND minute >= ?"
                    params.append(filters["minute_min"])
                # aceita minute_max ou momento_max (typo legado do prompt)
                minute_max = filters.get("minute_max", filters.get("momento_max"))
                if minute_max is not None:
                    query += " AND minute <= ?"
                    params.append(minute_max)
                if "is_pre_corner" in filters:
                    query += " AND is_pre_corner = ?"
                    params.append(filters["is_pre_corner"])

                cursor.execute(query, params)
                row = cursor.fetchone()
            finally:
                self._close_if_owned(conn)

            if row and row[0] and row[0] > 0:
                total = int(row[0])
                corners = int(row[1] or 0)
                prob = (corners / total) * 100.0
                avg_imc = float(row[2] or 0.0)
                result = {
                    "total_cases": total,
                    "success_rate": round(prob, 1),
                    "avg_imc": round(avg_imc, 2),
                    "confidence": (
                        "HIGH" if total > 15 else "MEDIUM" if total > 5 else "LOW"
                    ),
                    "paper_trade": True,
                }
                self.cache.set(cache_key, result, ttl=30)
                return result
        except Exception as e:
            logger.error("Erro na query de experiencia: %s", e)

        return {
            "total_cases": 0,
            "success_rate": 0.0,
            "confidence": "NONE",
            "paper_trade": True,
        }

    def stats(self) -> dict:
        with self._write_lock:
            pending = len(self._pending_writes)
        return {
            "pending": pending,
            "total_flushed": self._total_flushed,
            "flush_errors": self._flush_errors,
            "db_path": self.db_path,
        }
