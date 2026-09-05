#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Analytics: journals JSONL -> SQL (DuckDB ou SQLite).

Local: engine/core/analytics.py
Dependencias: stdlib (sqlite3). DuckDB OPCIONAL (pip install duckdb):
se presente, usa backend colunar; senao SQLite transparente — mesmo SQL.

Fontes de dados (tudo somente-leitura):
  - bridge: live_feed*.jsonl (envelope com 'view' ja normalizado)
  - engine/data: decisions*.jsonl (journal do ConformalRiskGate)
  - engine/data: conformal_state.jsonl (journal do ConformalGate)

Tabelas: frames, fixtures_last, corner_events, decisions, predictions,
resolutions, updates, loaded_files (registro de idempotencia).

Carga idempotente: arquivo (path, size, mtime) inalterado -> pulado.
Cada chamada de load e incremental; job semanal fica barato.

Queries-chave:
  q_corner_rate_by_minute  -> curva empirica (alimenta MinuteRateCurve)
  q_gap_distribution       -> valida tau do Hawkes/simulador
  q_window_yield           -> baseline W1/W2: P(>=1 canto | horizonte)
  q_decision_scorecard     -> decisao vs resultado (outcome resolvido pelo feed)
  q_calibration            -> bucket de p vs frequencia empirica + Brier
  q_coverage               -> cobertura conformal resolvida ao vivo
  q_feed_health            -> gaps de feed por fixture (auditoria de frescor)
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    from .replay import iter_records, record_timestamp
except ImportError:  # execucao direta: python engine/core/analytics.py
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from replay import iter_records, record_timestamp

log = logging.getLogger("aura.analytics")

__version__ = "1.1.1"
# v1.1.1: self-test — valores esperados da curva recalculados (bucket 75: 2.0 -> 1.5;
# erro do teste, nao do codigo).
# v1.1: replace-by-file — recarga de journal crescido nao duplica mais
# frames/decisions/updates (a v1 duplicava os tres; decisions infla
# q_decision_scorecard, que alimenta o criterio 1 do green-light).
# Migracao self-healing p/ schema v2 + stats() (convencao §6).
_SCHEMA_VERSION = "2"
_DATA_TABLES = ("frames", "fixtures_last", "corner_events", "decisions",
                "predictions", "resolutions", "updates", "loaded_files")
_META_DDL = ("CREATE TABLE IF NOT EXISTS schema_meta("
             "meta_key TEXT PRIMARY KEY, meta_value TEXT)")
__all__ = ["Analytics", "to_markdown"]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
        return None if (math.isnan(x) or math.isinf(x)) else x
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> Optional[int]:
    x = _f(v)
    return None if x is None else int(x)


def _fixture_of(v: dict) -> Optional[str]:
    fid = v.get("fixture_id") or v.get("fixtureId") or v.get("match_id")
    if fid:
        return str(fid)
    h, a = v.get("home"), v.get("away")
    if h and a:
        return f"{h}x{a}"
    return None


def _parse_pred_id(pred_id: Any) -> tuple:
    """'F1|m82|W2' -> ('F1', 82)."""
    if not pred_id or not isinstance(pred_id, str):
        return None, None
    parts = pred_id.split("|")
    if len(parts) >= 2 and parts[1].startswith("m"):
        try:
            return parts[0], int(parts[1][1:])
        except ValueError:
            pass
    return None, None


_DDL = [
    """CREATE TABLE IF NOT EXISTS loaded_files(
         path TEXT PRIMARY KEY, size INTEGER, mtime REAL,
         records INTEGER, loaded_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS frames(
         seq INTEGER PRIMARY KEY, fixture TEXT, minute REAL, ts REAL,
         corners_home INTEGER, corners_away INTEGER, corners_total INTEGER,
         dangerous_home INTEGER, dangerous_away INTEGER,
         attacks_home INTEGER, attacks_away INTEGER, possession_home REAL,
         score_home INTEGER, score_away INTEGER, received_at TEXT, file TEXT)""",
    """CREATE TABLE IF NOT EXISTS fixtures_last(
         fixture TEXT PRIMARY KEY, minute REAL, ts REAL,
         received_at TEXT, events_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS corner_events(
         fixture TEXT, minute REAL, ordinal INTEGER)""",
    """CREATE TABLE IF NOT EXISTS predictions(
         pred_id TEXT PRIMARY KEY, ts TEXT, p REAL, ctx TEXT, lo REAL, hi REAL)""",
    """CREATE TABLE IF NOT EXISTS resolutions(
         pred_id TEXT PRIMARY KEY, ts TEXT, y INTEGER, covered INTEGER)""",
    """CREATE TABLE IF NOT EXISTS updates(
         seq INTEGER, ts TEXT, ctx TEXT, p REAL, y INTEGER, file TEXT)""",
    """CREATE TABLE IF NOT EXISTS decisions(
         uid INTEGER PRIMARY KEY, ts TEXT, decision TEXT, p REAL, lo REAL,
         hi REAL, threshold REAL, context TEXT, pred_id TEXT, fixture TEXT,
         minute INTEGER, paper_trade INTEGER, outcome INTEGER, file TEXT)""",
]

_INS_FRAME = ("INSERT INTO frames (seq, fixture, minute, ts, corners_home, "
              "corners_away, corners_total, dangerous_home, dangerous_away, "
              "attacks_home, attacks_away, possession_home, score_home, "
              "score_away, received_at, file) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
_INS_DECISION = ("INSERT INTO decisions (uid, ts, decision, p, lo, hi, threshold, "
                 "context, pred_id, fixture, minute, paper_trade, outcome, file) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


# ---------------------------------------------------------------------------
class Analytics:
    """Fachada de carga + consultas. Somente-leitura sobre os journals."""

    def __init__(self, db_path="analytics.duckdb", *, prefer_duckdb: bool = True):
        self.db_path = Path(db_path)
        self.backend = "sqlite"
        self.conn = None
        self._load_stats = {"load_feed_calls": 0, "load_decisions_calls": 0,
                            "load_conformal_calls": 0, "frames_net": 0,
                            "decisions_net": 0, "updates_net": 0}
        if prefer_duckdb:
            try:
                import duckdb  # type: ignore
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.conn = duckdb.connect(str(self.db_path))
                self.backend = "duckdb"
            except ImportError:
                log.info("[analytics] duckdb ausente — SQLite (stdlib)")
            except Exception:
                log.exception("[analytics] duckdb falhou ao abrir — SQLite")
                self.conn = None
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.db_path))
            self.backend = "sqlite"
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
        self.conn.execute(_META_DDL)
        self._migrate()
        for ddl in _DDL:
            self.conn.execute(ddl)
        self.conn.commit()

    # -- v1.1: schema / migracao / replace-by-file ---------------------------
    def _table_exists(self, name: str) -> bool:
        try:
            self.conn.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()
            return True
        except Exception:
            return False

    def _delete_by_file(self, table: str, path_str: str) -> int:
        """Apaga as linhas de `table` vindas de path_str; devolve quantas."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM %s WHERE file = ?" % table,
            [path_str]).fetchone()
        n = int(row[0]) if row else 0
        if n:
            self.conn.execute("DELETE FROM %s WHERE file = ?" % table,
                              [path_str])
        return n

    def _migrate(self) -> None:
        """v1 -> v2 (self-healing): colunas `file` em decisions/updates.
        A v1 duplicava frames/decisions/updates sempre que um journal CRESCEU
        entre cargas. DBs legados sao reconstruidos do zero (§4).
        """
        row = self.conn.execute(
            "SELECT meta_value FROM schema_meta WHERE meta_key = 'schema_version'"
        ).fetchone()
        if row and row[0] == _SCHEMA_VERSION:
            return
        if row:
            try:
                if int(row[0]) > int(_SCHEMA_VERSION):
                    log.error("[analytics] DB de schema mais novo (%s) que este "
                              "codigo (%s) — nao migrando; atualize o analytics.py",
                              row[0], _SCHEMA_VERSION)
                    return
            except (TypeError, ValueError):
                log.warning("[analytics] schema_version ilegivel (%r) — "
                            "tratando como legado", row[0])
        if any(self._table_exists(tb) for tb in _DATA_TABLES):
            log.warning("[analytics] schema legado detectado — tabelas de dados "
                        "reconstruidas do zero; a proxima carga reimporta os "
                        "journals (uma unica vez)")
            for tb in _DATA_TABLES:
                self.conn.execute('DROP TABLE IF EXISTS "%s"' % tb)
        self.conn.execute("DELETE FROM schema_meta WHERE meta_key = 'schema_version'")
        self.conn.execute(
            "INSERT INTO schema_meta (meta_key, meta_value) "
            "VALUES ('schema_version', ?)", [_SCHEMA_VERSION])
        self.conn.commit()

    def stats(self) -> dict:
        """Estado do modulo p/ observability (§6). Batch: contadores de carga."""
        out = {"backend": self.backend, "db_path": str(self.db_path),
               "schema_version": _SCHEMA_VERSION}
        out.update(self._load_stats)
        try:
            for key, table in (("frames_in_db", "frames"),
                               ("decisions_in_db", "decisions"),
                               ("updates_in_db", "updates")):
                row = self.conn.execute(
                    "SELECT COUNT(*) FROM %s" % table).fetchone()
                out[key] = int(row[0]) if row else 0
        except Exception:
            log.exception("[analytics] stats(): falha ao contar tabelas")
        return {"analytics": out}


    def query(self, sql: str, params: Optional[Sequence] = None) -> List[dict]:
        cur = self.conn.execute(sql, list(params)) if params else self.conn.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _max(self, table: str, col: str) -> int:
        row = self.conn.execute(
            f"SELECT COALESCE(MAX({col}), 0) FROM {table}").fetchone()
        return int(row[0])

    def _file_state(self, p: Path) -> tuple:
        st = p.stat()
        return int(st.st_size), float(st.st_mtime)

    def _already_loaded(self, p: Path) -> bool:
        cur = self.conn.execute(
            "SELECT size, mtime FROM loaded_files WHERE path = ?",
            [str(p)]).fetchone()
        if not cur:
            return False
        size, mtime = self._file_state(p)
        return int(cur[0]) == size and abs(float(cur[1]) - mtime) < 1e-6

    def _register_file(self, p: Path, records: int) -> None:
        size, mtime = self._file_state(p)
        self.conn.execute("DELETE FROM loaded_files WHERE path = ?", [str(p)])
        self.conn.execute(
            "INSERT INTO loaded_files (path, size, mtime, records, loaded_at) "
            "VALUES (?,?,?,?,?)", [str(p), size, mtime, records, _iso_now()])

    # -- cargas ------------------------------------------------------------------
    def load_feed(self, paths) -> dict:
        """Carrega JSONL do bridge (registros com 'view'). Idempotente.
        v1.1: arquivo que CRESCEU entre cargas e recarregado por inteiro
        (journal append-only), mas as linhas antigas desse arquivo sao
        SUBSTITUIDAS (DELETE por file) — sem duplicar. `frames` no retorno
        e o liquido novo.
        """
        stats = {"files": 0, "files_skipped": 0, "frames": 0}
        self._load_stats["load_feed_calls"] += 1
        for p in paths:
            p = Path(p)
            if not p.exists():
                continue
            if self._already_loaded(p):
                stats["files_skipped"] += 1
                continue
            path_str = str(p)
            base = self._max("frames", "seq")
            rows, last, n = [], {}, 0
            for _meta, rec in iter_records([p]):
                v = rec.get("view") if isinstance(rec.get("view"), dict) else None
                if not v:
                    continue
                fixture = _fixture_of(v)
                if not fixture:
                    continue
                n += 1
                m = _f(v.get("minute"))
                ts = record_timestamp(rec) or 0.0
                ch, ca = _i(v.get("corners_home")), _i(v.get("corners_away"))
                ct = None if (ch is None and ca is None) else (ch or 0) + (ca or 0)
                rows.append((base + n, fixture, m, ts, ch, ca, ct,
                             _i(v.get("dangerous_home")), _i(v.get("dangerous_away")),
                             _i(v.get("attacks_home")), _i(v.get("attacks_away")),
                             _f(v.get("possession_home")), _i(v.get("score_home")),
                             _i(v.get("score_away")), rec.get("received_at"), path_str))
                prev = last.get(fixture)
                if prev is None or (m is not None and
                                    (prev[0] is None or m >= prev[0])):
                    last[fixture] = (m, ts, rec.get("received_at"),
                                     json.dumps(v.get("corner_events") or v.get("ce") or [],
                                                ensure_ascii=False, default=str))
            deleted = self._delete_by_file("frames", path_str)
            if rows:
                self.conn.executemany(_INS_FRAME, rows)
            stats["frames"] += len(rows) - deleted
            self._load_stats["frames_net"] += len(rows) - deleted
            if last:
                self.conn.executemany(
                    "DELETE FROM fixtures_last WHERE fixture = ?",
                    [(fx,) for fx in last])
                self.conn.executemany(
                    "INSERT INTO fixtures_last (fixture, minute, ts, received_at, "
                    "events_json) VALUES (?,?,?,?,?)",
                    [(fx, tt[0], tt[1], tt[2], tt[3]) for fx, tt in last.items()])
            self._register_file(p, n)
            self.conn.commit()
            stats["files"] += 1
        if stats["frames"] != 0:
            self.refresh_corner_events()
        return stats

    def refresh_corner_events(self) -> int:
        """Reconstroi corner_events a partir do ultimo frame de cada fixture.

        Premissa: corner_events do feed e cumulativo — o ultimo frame carrega a
        lista completa. Partida ainda ao vivo -> recarregue apos o fim.
        """
        self.conn.execute("DELETE FROM corner_events")
        rows = self.conn.execute(
            "SELECT fixture, events_json FROM fixtures_last").fetchall()
        ins = []
        for fixture, ej in rows:
            try:
                events = json.loads(ej) if ej else []
            except (ValueError, TypeError):
                events = []
            if not isinstance(events, list):
                events = []
            for ordinal, e in enumerate(events):
                m = None
                if isinstance(e, dict):
                    m = _f(e.get("minute", e.get("m")))
                elif isinstance(e, (list, tuple)) and e:
                    m = _f(e[0])
                if m is not None:
                    ins.append((fixture, m, ordinal))
        if ins:
            self.conn.executemany(
                "INSERT INTO corner_events (fixture, minute, ordinal) "
                "VALUES (?,?,?)", ins)
        self.conn.commit()
        return len(ins)

    def load_decisions(self, paths) -> dict:
        """Carrega decisions*.jsonl (journal do ConformalRiskGate).
        v1.1: replace-by-file — recarga de arquivo crescido substitui as
        linhas antigas (a v1 duplicava uids, inflando o scorecard e o
        criterio 1 do green-light). `decisions` no retorno e o liquido novo.
        """
        stats = {"files": 0, "decisions": 0}
        self._load_stats["load_decisions_calls"] += 1
        for p in paths:
            p = Path(p)
            if not p.name.startswith("decision") or not p.exists():
                continue
            if self._already_loaded(p):
                continue
            path_str = str(p)
            base = self._max("decisions", "uid")
            rows, n = [], 0
            for _meta, rec in iter_records([p]):
                d = rec.get("decision")
                if not d:
                    continue
                pred_id = rec.get("pred_id")
                fx, mi = _parse_pred_id(pred_id)
                n += 1
                rows.append((base + n, rec.get("ts"), str(d), _f(rec.get("p")),
                             _f(rec.get("lo")), _f(rec.get("hi")),
                             _f(rec.get("threshold")), rec.get("context"),
                             pred_id, fx, mi,
                             1 if rec.get("paper_trade") else 0, None, path_str))
            deleted = self._delete_by_file("decisions", path_str)
            if rows:
                self.conn.executemany(_INS_DECISION, rows)
            stats["decisions"] += len(rows) - deleted
            self._load_stats["decisions_net"] += len(rows) - deleted
            self._register_file(p, n)
            self.conn.commit()
            stats["files"] += 1
        return stats

    def load_conformal(self, paths) -> dict:
        """Carrega conformal_state.jsonl (eventos pred/res/u).
        v1.1: eventos 'u' carregam a coluna `file` e a recarga de arquivo
        crescido SUBSTITUI as linhas antigas (a v1 duplicava 'u' a cada
        recarga semanal, enviesando q_calibration para dados antigos).
        """
        stats = {"files": 0, "predictions": 0, "resolutions": 0, "updates": 0}
        self._load_stats["load_conformal_calls"] += 1
        for p in paths:
            p = Path(p)
            if not p.name.startswith("conformal") or not p.exists():
                continue
            if self._already_loaded(p):
                continue
            path_str = str(p)
            preds, ress, ups = [], [], []
            for _meta, rec in iter_records([p]):
                ev = rec.get("ev")
                if ev == "pred" and rec.get("id") is not None:
                    preds.append((str(rec.get("id")), rec.get("t"),
                                  _f(rec.get("p")), rec.get("ctx"),
                                  _f(rec.get("lo")), _f(rec.get("hi"))))
                elif ev == "res" and rec.get("id") is not None \
                        and rec.get("y") in (0, 1):
                    ress.append((str(rec.get("id")), rec.get("t"),
                                 int(rec.get("y")),
                                 1 if rec.get("covered") else 0))
                elif ev == "u" and _f(rec.get("p")) is not None \
                        and rec.get("y") in (0, 1):
                    ups.append((_i(rec.get("seq")) or 0, rec.get("t"),
                                rec.get("ctx"), _f(rec.get("p")),
                                int(rec.get("y")), path_str))
            if preds:
                self.conn.executemany(
                    "DELETE FROM predictions WHERE pred_id = ?",
                    [(r[0],) for r in preds])
                self.conn.executemany(
                    "INSERT INTO predictions (pred_id, ts, p, ctx, lo, hi) "
                    "VALUES (?,?,?,?,?,?)", preds)
            if ress:
                self.conn.executemany(
                    "DELETE FROM resolutions WHERE pred_id = ?",
                    [(r[0],) for r in ress])
                self.conn.executemany(
                    "INSERT INTO resolutions (pred_id, ts, y, covered) "
                    "VALUES (?,?,?,?)", ress)
            deleted_u = self._delete_by_file("updates", path_str)
            if ups:
                self.conn.executemany(
                    "INSERT INTO updates (seq, ts, ctx, p, y, file) "
                    "VALUES (?,?,?,?,?,?)", ups)
            stats["updates"] += len(ups) - deleted_u
            self._load_stats["updates_net"] += len(ups) - deleted_u
            self._register_file(p, len(preds) + len(ress) + len(ups))
            self.conn.commit()
            stats["files"] += 1
            stats["predictions"] += len(preds)
            stats["resolutions"] += len(ress)
        return stats

    def fill_decision_outcomes(self, horizon: int = 10) -> int:
        """Resolve y das decisoes a partir dos corner_events do feed.

        Fixture sem dados no feed permanece outcome NULL (nao inventa).
        """
        rows = self.conn.execute(
            "SELECT uid, fixture, minute FROM decisions "
            "WHERE outcome IS NULL AND fixture IS NOT NULL "
            "AND minute IS NOT NULL").fetchall()
        if not rows:
            return 0
        events: Dict[str, List[float]] = {}
        for fx, m in self.conn.execute(
                "SELECT fixture, minute FROM corner_events").fetchall():
            if fx is not None and m is not None:
                events.setdefault(fx, []).append(float(m))
        known = {fx for (fx,) in self.conn.execute(
            "SELECT fixture FROM fixtures_last").fetchall()}
        upd = []
        for uid, fx, m in rows:
            if fx not in known or fx not in events:
                continue  # sem dados dessa fixture -> continua NULL
            y = 1 if any(m < em <= m + horizon for em in events[fx]) else 0
            upd.append((y, uid))
        if upd:
            self.conn.executemany(
                "UPDATE decisions SET outcome = ? WHERE uid = ?", upd)
            self.conn.commit()
        return len(upd)

    # -- queries ------------------------------------------------------------------
    def q_corner_rate_by_minute(self, bucket: int = 10) -> List[dict]:
        return self.query(
            """WITH nf AS (SELECT COUNT(DISTINCT fixture) AS n FROM corner_events)
               SELECT CAST(CAST(minute AS DOUBLE) / ? AS INTEGER) * ? AS minute_bucket,
                      COUNT(*) AS corners,
                      COUNT(*) * 1.0 / NULLIF((SELECT n FROM nf), 0) AS corners_per_match
               FROM corner_events GROUP BY minute_bucket ORDER BY minute_bucket""",
            [bucket, bucket])

    def q_gap_distribution(self, max_gap: int = 30) -> List[dict]:
        return self.query(
            """WITH g AS (
                 SELECT minute - LAG(minute) OVER (
                          PARTITION BY fixture ORDER BY ordinal, minute) AS gap
                 FROM corner_events)
               SELECT CAST(gap AS INTEGER) AS gap_min, COUNT(*) AS n
               FROM g WHERE gap IS NOT NULL AND gap >= 0 AND gap <= ?
               GROUP BY gap_min ORDER BY gap_min""",
            [max_gap])

    def q_window_yield(self, minute_from: int, minute_to: int,
                       horizon: int = 10) -> List[dict]:
        """Baseline: P(>=1 canto em `horizon` min | minuto de entrada).

        Entradas = minutos inteiros da janela, por fixture, exigindo frames
        observados ao longo da janela (resultado observavel). Aproximacao
        documentada: fixture sem frame na janela nao entra na conta.
        """
        return self.query(
            """WITH RECURSIVE em(m) AS (
                 SELECT ? UNION ALL SELECT m + 1 FROM em WHERE m + 1 <= ?),
               entries AS (
                 SELECT f.fixture, em.m
                 FROM (SELECT DISTINCT fixture FROM frames) f CROSS JOIN em
                 WHERE EXISTS (SELECT 1 FROM frames f2
                               WHERE f2.fixture = f.fixture
                                 AND f2.minute >= em.m
                                 AND f2.minute <= em.m + ?))
               SELECT e.m AS entry_minute, COUNT(*) AS n,
                      AVG(CASE WHEN EXISTS (
                            SELECT 1 FROM corner_events ce
                            WHERE ce.fixture = e.fixture
                              AND ce.minute > e.m
                              AND ce.minute <= e.m + ?)
                           THEN 1.0 ELSE 0.0 END) AS p_corner
               FROM entries e GROUP BY entry_minute ORDER BY entry_minute""",
            [minute_from, minute_to, horizon, horizon])

    def q_decision_scorecard(self) -> List[dict]:
        return self.query(
            """SELECT decision, COUNT(*) AS n,
                      SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END) AS wins,
                      SUM(CASE WHEN outcome = 0 THEN 1 ELSE 0 END) AS losses,
                      SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) AS unknown,
                      AVG(CASE WHEN outcome IS NOT NULL
                               THEN CAST(outcome AS DOUBLE) END) AS hit_rate
               FROM decisions GROUP BY decision ORDER BY decision""")

    def q_calibration(self, n_buckets: int = 10) -> List[dict]:
        rows = self.query(
            """SELECT CAST(p * ? AS INTEGER) AS bucket, COUNT(*) AS n,
                      AVG(CAST(y AS DOUBLE)) AS empirical, AVG(p) AS avg_p,
                      AVG((p - y) * (p - y)) AS brier
               FROM updates GROUP BY bucket ORDER BY bucket""",
            [n_buckets])
        for r in rows:  # p=1.0 exato cai no bucket n -> clamp
            if r["bucket"] >= n_buckets:
                r["bucket"] = n_buckets - 1
        return rows

    def q_coverage(self) -> List[dict]:
        return self.query(
            """SELECT COUNT(*) AS n,
                      AVG(CAST(covered AS DOUBLE)) AS coverage_rate
               FROM resolutions""")

    def q_feed_health(self, top: int = 10) -> List[dict]:
        return self.query(
            """WITH g AS (SELECT fixture,
                          ts - LAG(ts) OVER (
                              PARTITION BY fixture ORDER BY seq) AS gap
                          FROM frames)
               SELECT fixture, COUNT(*) AS frames, MAX(gap) AS max_gap_sec,
                      AVG(gap) AS avg_gap_sec
               FROM g WHERE gap IS NOT NULL
               GROUP BY fixture ORDER BY max_gap_sec DESC LIMIT ?""",
            [top])

    # -- relatorio ------------------------------------------------------------------
    def full_report(self, *, w1=(30, 48), w2=(80, 95), horizon: int = 10) -> str:
        c = self.query(
            """SELECT (SELECT COUNT(*) FROM frames) AS frames,
                      (SELECT COUNT(DISTINCT fixture) FROM frames) AS fixtures,
                      (SELECT COUNT(*) FROM corner_events) AS corner_events,
                      (SELECT COUNT(*) FROM decisions) AS decisoes""")[0]
        parts = [
            "# AURA — Relatorio de Analytics",
            "",
            f"*Backend: {self.backend} · Gerado: {_iso_now()}*",
            "",
            f"**Frames:** {c['frames']} · **Fixtures:** {c['fixtures']} · "
            f"**Cantos:** {c['corner_events']} · **Decisoes:** {c['decisoes']}",
            "",
            to_markdown(self.q_corner_rate_by_minute(15),
                        title="Taxa de cantos por 15 min (por partida)"),
            "",
            to_markdown(self.q_gap_distribution(30),
                        title="Distribuicao de gaps entre cantos (min)"),
            "",
            to_markdown(self.q_window_yield(w1[0], w1[1], horizon),
                        title=f"W1 ({w1[0]}-{w1[1]}'): P(>=1 canto em {horizon} min)"),
            "",
            to_markdown(self.q_window_yield(w2[0], w2[1], horizon),
                        title=f"W2 ({w2[0]}-{w2[1]}'): P(>=1 canto em {horizon} min)"),
            "",
            to_markdown(self.q_decision_scorecard(),
                        title="Scorecard de decisoes (outcome resolvido pelo feed)"),
            "",
            to_markdown(self.q_calibration(10),
                        title="Calibracao (bucket de p vs frequencia empirica)"),
            "",
            to_markdown(self.q_coverage(), title="Cobertura conformal (ao vivo)"),
            "",
            to_markdown(self.q_feed_health(10), title="Saude do feed (gaps por fixture)"),
        ]
        return "\n".join(parts)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self) -> "Analytics":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ---------------------------------------------------------------------------
def to_markdown(rows: List[dict], *, title: str = "",
                float_fmt: str = "{:.4f}") -> str:
    if not rows:
        return (f"### {title}\n\n_(sem dados)_\n" if title else "_(sem dados)_")
    cols = list(rows[0].keys())
    lines = [f"### {title}", ""] if title else []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for r in rows:
        cells = []
        for cname in cols:
            v = r.get(cname)
            if v is None:
                cells.append("—")
            elif isinstance(v, float):
                cells.append(float_fmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test: python engine/core/analytics.py
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    try:
        import duckdb  # noqa: F401
        backends = [("sqlite", False), ("duckdb", True)]
    except ImportError:
        backends = [("sqlite", False)]
        print("[SKIP] duckdb nao instalado — testando apenas SQLite")

    def build_fixtures(td: Path):
        base = datetime(2026, 8, 23, 20, 0, 0, tzinfo=timezone.utc)
        f1_events, f2_events = [33, 41, 55, 68, 82, 88], [37, 62, 84]

        def rec(fid, m, events):
            iso = (base + __import__("datetime").timedelta(minutes=m)).isoformat()
            ev = [{"minute": e, "team": "h"} for e in events if e <= m]
            return {"received_at": iso, "fingerprint": f"{fid}|m{m}",
                    "view": {"fixture_id": fid, "minute": m, "corners_home": len(ev),
                             "corners_away": 0, "corner_events": ev},
                    "payload": {"fixture": {"id": fid, "minute": m}}}

        feed1 = td / "live_feed-20260823.jsonl"
        feed1.write_text("\n".join(
            json.dumps(rec("F1", m, f1_events)) for m in range(30, 91, 2)) + "\n",
            encoding="utf-8")
        feed2 = td / "live_feed-20260824.jsonl"
        feed2.write_text("\n".join(
            json.dumps(rec("F2", m, f2_events)) for m in range(30, 91, 5)) + "\n",
            encoding="utf-8")

        def dec(d, pred, p):
            fx, mi = _parse_pred_id(pred)
            return {"decision": d, "p": p, "threshold": 0.65, "lo": p - 0.1,
                    "hi": p + 0.1, "context": pred.split("|")[-1], "pred_id": pred,
                    "paper_trade": True, "ts": _iso_now(), "fixture": fx,
                    "minute": mi, "reasons": [], "n_samples": 100}

        (td / "decisions.jsonl").write_text("\n".join(json.dumps(x) for x in [
            dec("ENTER", "F1|m82|W2", 0.75),
            dec("ENTER", "F2|m35|W1", 0.70),
            dec("HOLD", "F1|m40|W1", 0.55),
        ]) + "\n", encoding="utf-8")

        conf = []
        conf.append({"ev": "pred", "id": "F1|m82|W2", "p": 0.75, "ctx": "W2",
                     "lo": 0.65, "hi": 0.85, "seq": 1, "t": _iso_now()})
        conf.append({"ev": "res", "id": "F1|m82|W2", "y": 1, "covered": True,
                     "seq": 2, "t": _iso_now()})
        conf.append({"ev": "res", "id": "F2|m35|W1", "y": 1, "covered": False,
                     "seq": 3, "t": _iso_now()})
        for i in range(10):
            conf.append({"ev": "u", "p": 0.8, "y": 1, "ctx": "global",
                         "seq": 10 + i, "t": _iso_now()})
        for i in range(5):
            conf.append({"ev": "u", "p": 0.2, "y": 0, "ctx": "global",
                         "seq": 30 + i, "t": _iso_now()})
        (td / "conformal_state.jsonl").write_text(
            "\n".join(json.dumps(x) for x in conf) + "\n", encoding="utf-8")
        return [feed1, feed2]

    for backend_name, prefer in backends:
        print(f"\n--- backend: {backend_name} ---")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            feed_paths = build_fixtures(td)
            an = Analytics(td / f"an_{backend_name}.db", prefer_duckdb=prefer)
            check(f"[{backend_name}] backend selecionado",
                  an.backend == backend_name)

            st = an.load_feed(feed_paths)
            check(f"[{backend_name}] load_feed: 44 frames (31 F1 + 13 F2)",
                  st["frames"] == 44, f"{st}")
            nev = an.refresh_corner_events()
            check(f"[{backend_name}] corner_events: 9 cantos", nev == 9)

            st2 = an.load_feed(feed_paths)
            check(f"[{backend_name}] recarga idempotente",
                  st2["frames"] == 0 and st2["files_skipped"] == 2)

            # v1.1.1: valores esperados da curva RECALCULADOS contra os dados
            # sinteticos (F1: [33,41,55,68,82,88]; F2: [37,62,84]; 2 fixtures):
            # bucket 30: 33,41,37 -> 3/2 = 1.5
            # bucket 45: 55 -> 1/2 = 0.5
            # bucket 60: 68,62 -> 2/2 = 1.0
            # bucket 75: 82,88,84 -> 3/2 = 1.5 (v1.0 esperava 2.0 — erro de
            # aritmetica do SELF-TEST original; o codigo de producao estava certo)
            cr = {r["minute_bucket"]: r for r in an.q_corner_rate_by_minute(15)}
            for bucket, expected in ((30, 1.5), (45, 0.5), (60, 1.0), (75, 1.5)):
                got = cr[bucket]["corners_per_match"]
                check(f"[{backend_name}] curva: bucket {bucket}' = {expected}/partida",
                      abs(got - expected) < 1e-9, f"got={got}")

            gaps = {r["gap_min"]: r["n"] for r in an.q_gap_distribution(30)}
            check(f"[{backend_name}] gaps: gap=14 min aparece 2x", gaps.get(14) == 2)

            wy = an.q_window_yield(80, 85, 10)
            tot = sum(r["n"] for r in wy)
            pmed = sum(r["p_corner"] * r["n"] for r in wy) / tot
            check(f"[{backend_name}] window_yield W2 80-85': ~0.833",
                  tot == 12 and abs(pmed - 10.0 / 12.0) < 1e-6,
                  f"p={pmed:.4f} n={tot}")

            an.load_decisions(list(td.glob("*.jsonl")))
            an.load_conformal(list(td.glob("*.jsonl")))
            filled = an.fill_decision_outcomes(10)
            check(f"[{backend_name}] fill_outcomes: 3 decisoes resolvidas",
                  filled == 3)
            sc = {r["decision"]: r for r in an.q_decision_scorecard()}
            check(f"[{backend_name}] scorecard: ENTER 2/2",
                  sc["ENTER"]["n"] == 2 and sc["ENTER"]["wins"] == 2
                  and abs(sc["ENTER"]["hit_rate"] - 1.0) < 1e-9)

            cal = {r["bucket"]: r for r in an.q_calibration(10)}
            check(f"[{backend_name}] calibracao: bucket 8 empirico=1.0",
                  cal[8]["n"] == 10 and abs(cal[8]["empirical"] - 1.0) < 1e-9)
            check(f"[{backend_name}] calibracao: bucket 2 empirico=0.0",
                  cal[2]["n"] == 5 and abs(cal[2]["empirical"] - 0.0) < 1e-9)

            cov = an.q_coverage()[0]
            check(f"[{backend_name}] cobertura: 2 resolvidas, 50%",
                  cov["n"] == 2 and abs(cov["coverage_rate"] - 0.5) < 1e-9)

            fh = {r["fixture"]: r for r in an.q_feed_health(10)}
            check(f"[{backend_name}] feed_health: gap max F2=300s",
                  abs(fh["F2"]["max_gap_sec"] - 300.0) < 1.0)

            rep = an.full_report()
            check(f"[{backend_name}] full_report markdown",
                  "Scorecard" in rep and "| decision |" in rep)

            # v1.1: journal cresce entre cargas -> recarga LIQUIDA, sem duplicar
            feed_a, feed_b = feed_paths[0], feed_paths[1]
            extra_frame = {"received_at": "2026-08-23T21:32:00+00:00",
                           "fingerprint": "F1|m92",
                           "view": {"fixture_id": "F1", "minute": 92,
                                    "corners_home": 6, "corners_away": 0,
                                    "corner_events": [
                                        {"minute": e, "team": "h"}
                                        for e in (33, 41, 55, 68, 82, 88)]},
                           "payload": {"fixture": {"id": "F1", "minute": 92}}}
            with open(feed_a, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(extra_frame) + "\n")
            st3 = an.load_feed([feed_a, feed_b])
            check(f"[{backend_name}] feed crescido: liquido = 1 frame novo",
                  st3["frames"] == 1, f"{st3}")
            tot_f = an.query("SELECT COUNT(*) AS n FROM frames")[0]["n"]
            check(f"[{backend_name}] frames em banco = 45 (sem duplicata)",
                  tot_f == 45, f"n={tot_f}")

            st6 = an.stats()["analytics"]
            check(f"[{backend_name}] stats() expoe schema e contadores (§6)",
                  st6["schema_version"] == _SCHEMA_VERSION
                  and "frames_net" in st6 and "decisions_in_db" in st6)

            # v1.1: decisions crescido -> replace, nao duplica
            extra_dec = {"decision": "ENTER", "p": 0.72, "threshold": 0.65,
                         "lo": 0.62, "hi": 0.82, "context": "W2",
                         "pred_id": "F1|m88|W2", "paper_trade": True,
                         "ts": _iso_now(), "fixture": "F1", "minute": 88,
                         "reasons": [], "n_samples": 100}
            with open(td / "decisions.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(extra_dec) + "\n")
            st4 = an.load_decisions(list(td.glob("*.jsonl")))
            check(f"[{backend_name}] decisions crescido: liquido = 1",
                  st4["decisions"] == 1, f"{st4}")
            tot_d = an.query("SELECT COUNT(*) AS n FROM decisions")[0]["n"]
            check(f"[{backend_name}] decisions em banco = 4 (sem duplicata)",
                  tot_d == 4, f"n={tot_d}")

            # v1.1: updates crescido -> replace, calibracao nao enviesa
            extra_u = {"ev": "u", "p": 0.8, "y": 1, "ctx": "global",
                       "seq": 40, "t": _iso_now()}
            with open(td / "conformal_state.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(extra_u) + "\n")
            st5 = an.load_conformal(list(td.glob("*.jsonl")))
            check(f"[{backend_name}] conformal crescido: updates liquido = 1",
                  st5["updates"] == 1, f"{st5}")
            tot_u = an.query("SELECT COUNT(*) AS n FROM updates")[0]["n"]
            check(f"[{backend_name}] updates em banco = 16 (sem duplicata)",
                  tot_u == 16, f"n={tot_u}")
            cal2 = {r["bucket"]: r for r in an.q_calibration(10)}
            check(f"[{backend_name}] calibracao pos-recarga: bucket 8 n=11",
                  cal2[8]["n"] == 11)

            # v1.1: migracao self-healing — DB sem version row e reconstruido
            an.conn.execute("DELETE FROM schema_meta")
            an.conn.commit()
            an.close()
            an = Analytics(td / f"an_{backend_name}.db", prefer_duckdb=prefer)
            tot_m = an.query("SELECT COUNT(*) AS n FROM frames")[0]["n"]
            check(f"[{backend_name}] migracao zera tabelas legadas", tot_m == 0)
            an.load_feed(list(td.glob("live_feed*.jsonl")))
            tot_m2 = an.query("SELECT COUNT(*) AS n FROM frames")[0]["n"]
            check(f"[{backend_name}] pos-migracao reimporta journals",
                  tot_m2 == 45)
            an.close()

    print(f"\nanalytics selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
