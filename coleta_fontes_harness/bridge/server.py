#!/usr/bin/env python3
"""
CornerAI Bridge mínimo — recebe feed da extensão e grava JSONL + REG.

Endpoint:
  POST http://127.0.0.1:8080/api/cornerai/feed

Saídas (pasta do script ou CORNERAI_DATA_DIR):
  live_feed.jsonl          — um JSON por linha (cada push da extensão)
  live_latest.json         — último payload completo
  regs/REG-YYYYMMDD-NNN.md — bloco REG no schema da skill
  CornerAI_Log_Analises_Entradas.md — append dos REGs

Uso:
  python3 server.py
  python3 server.py --port 8080 --dir ./data
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths / state
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent
FEED_FILE = DATA_DIR / "live_feed.jsonl"
LATEST_FILE = DATA_DIR / "live_latest.json"
LOG_FILE = DATA_DIR / "CornerAI_Log_Analises_Entradas.md"
REGS_DIR = DATA_DIR / "regs"
SKILL_JSON = DATA_DIR / "skill_feed_latest.json"
SKILL_MD = DATA_DIR / "skill_feed_for_chat.md"
SKILL_HISTORY = DATA_DIR / "skill_feed_history.jsonl"
BRIDGE_VERSION = "12.7.6-RESILIENCIA"
logger = logging.getLogger("aura.bridge")


class FeedRotator:
    """Rotaciona JSONL antes do fallback escrever, sem apagar o arquivo ativo."""
    def __init__(self, filepath: Path, max_size_mb: int = 50, backups: int = 5):
        self.filepath = Path(filepath)
        self.max_size = max(1, int(max_size_mb)) * 1024 * 1024
        self.backups = max(1, int(backups))
        self._lock = threading.Lock()

    def check_and_rotate(self) -> None:
        with self._lock:
            try:
                if not self.filepath.exists() or self.filepath.stat().st_size <= self.max_size:
                    return
                for index in range(self.backups, 0, -1):
                    older = self.filepath.with_name(self.filepath.name + f".{index}.bak")
                    if index == self.backups and older.exists():
                        older.unlink()
                    elif index < self.backups and older.exists():
                        newer = self.filepath.with_name(self.filepath.name + f".{index + 1}.bak")
                        older.replace(newer)
                self.filepath.replace(self.filepath.with_name(self.filepath.name + ".1.bak"))
                logger.info("Feed JSONL rotacionado: %s", self.filepath)
            except OSError as exc:
                logger.warning("Falha ao rotacionar feed: %s", exc)


_FEED_ROTATOR = FeedRotator(FEED_FILE, max_size_mb=50, backups=5)

# Security defaults: browser origins are explicit and never reflected broadly.
_ALLOWED_ORIGINS = {x.strip() for x in os.getenv(
    "CORNERAI_ALLOWED_ORIGINS",
    "https://aura.local,http://aura.local,"
    "https://sokkerpro.com,https://www.sokkerpro.com,"
    "https://m2.sokkerpro.com,https://m4.sokkerpro.com"
).split(",") if x.strip()}
_BRIDGE_TOKEN = os.getenv("CORNERAI_BRIDGE_TOKEN", "").strip()
# Operator OS local: default aberto; em rede compartilhada force CORNERAI_BRIDGE_REQUIRE_TOKEN=1
_REQUIRE_BRIDGE_TOKEN = os.getenv("CORNERAI_BRIDGE_REQUIRE_TOKEN", "0").strip().lower() not in {"0", "false", "no", "off"}

_lock = threading.Lock()
_seq_by_day: Dict[str, int] = {}
_last_fingerprint: Optional[str] = None
_last_log_key: Optional[str] = None
_last_log_at: float = 0.0

# v12.7.2: fallback bounded para instalações onde o FeedBus não carrega.
# O caminho normal já usa FeedBus com writer dedicado; este buffer evita que
# o fallback legado escreva live_feed.jsonl a cada POST.
_FEED_RING_BUFFER = deque(maxlen=500)
_BUFFER_LOCK = threading.Lock()
_FLUSH_INTERVAL_SEC = 2.0
_FLUSH_STOP = threading.Event()
_FLUSH_THREAD: Optional[threading.Thread] = None

# --- V25 FeedBus: handler HTTP nao toca em disco (writer dedicado) ---
import sys as _sys
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
try:
    from engine.core.feed_bus import FeedBus, JsonlSink, LatestJsonSink
    BUS = FeedBus(name="bridge_feed", maxsize=4096, batch_size=256,
                  flush_interval=0.20, drop_policy="newest")
    # rotate=None preserva nome live_feed.jsonl para consumidores legados
    BUS.add_sink(JsonlSink(FEED_FILE, rotate=None))
    BUS.add_sink(LatestJsonSink(LATEST_FILE))

    def _on_feed_batch(records):
        """Cold path (writer thread): REG markdown + skill pack."""
        global _last_fingerprint
        for rec in records:
            view = rec.get("view") or {}
            payload = rec.get("payload") or {}
            if not (view.get("fixture_id") or view.get("home")):
                continue
            fp = fingerprint(view)
            if fp == _last_fingerprint:
                continue
            _last_fingerprint = fp
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                REGS_DIR.mkdir(parents=True, exist_ok=True)
                ensure_log_header()
                reg_id = _next_reg_id()
                md = build_reg_markdown(reg_id, view, payload)
                (REGS_DIR / f"{reg_id}.md").write_text(md, encoding="utf-8")
                with LOG_FILE.open("a", encoding="utf-8") as f:
                    f.write(md + "\n")
                append_index_row(reg_id, view)
            except Exception:
                import traceback
                traceback.print_exc()
            try:
                pack = view_to_skill_pack(view, payload)
                persist_skill_pack({"json": pack, "pack": pack})
            except Exception:
                import traceback
                traceback.print_exc()

    BUS.subscribe(_on_feed_batch, sid="reg_skill")
    BUS.start()
except Exception as _bus_exc:
    BUS = None  # type: ignore
    print(f"[bridge] FeedBus indisponivel — fallback sync: {_bus_exc}", flush=True)


def _flush_feed_buffer_once() -> int:
    with _BUFFER_LOCK:
        batch = list(_FEED_RING_BUFFER)
        _FEED_RING_BUFFER.clear()
    if not batch:
        return 0
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _FEED_ROTATOR.check_and_rotate()
        with FEED_FILE.open("a", encoding="utf-8") as f:
            f.writelines(batch)
        return len(batch)
    except Exception:
        # Devolve o lote ao buffer quando possível; não derruba o endpoint.
        with _BUFFER_LOCK:
            for row in reversed(batch):
                _FEED_RING_BUFFER.appendleft(row)
        return 0


def _background_flush_feed() -> None:
    while not _FLUSH_STOP.wait(_FLUSH_INTERVAL_SEC):
        _flush_feed_buffer_once()


def _start_fallback_flush_thread() -> None:
    global _FLUSH_THREAD
    if _FLUSH_THREAD is None or not _FLUSH_THREAD.is_alive():
        _FLUSH_STOP.clear()
        _FLUSH_THREAD = threading.Thread(
            target=_background_flush_feed,
            name="aura-feed-fallback-flush",
            daemon=True,
        )
        _FLUSH_THREAD.start()


def _stop_fallback_flush_thread() -> None:
    _FLUSH_STOP.set()
    _flush_feed_buffer_once()


def _queue_fallback_record(record: Dict[str, Any]) -> None:
    _start_fallback_flush_thread()
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _BUFFER_LOCK:
        _FEED_RING_BUFFER.append(line)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _day_key() -> str:
    return datetime.now().strftime("%Y%m%d")


def _next_reg_id() -> str:
    day = _day_key()
    with _lock:
        n = _seq_by_day.get(day, 0) + 1
        # also scan existing regs to avoid collision after restart
        if day not in _seq_by_day and REGS_DIR.exists():
            existing = list(REGS_DIR.glob(f"REG-{day}-*.md"))
            max_n = 0
            for p in existing:
                m = re.search(rf"REG-{day}-(\d+)", p.name)
                if m:
                    max_n = max(max_n, int(m.group(1)))
            n = max(max_n + 1, n)
        _seq_by_day[day] = n
        return f"REG-{day}-{n:03d}"


def _safe_num(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        if isinstance(v, str) and v.strip() == "":
            return None
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return v


def _pair(obj: Any, key_home: str = "home", key_away: str = "away") -> Tuple[Any, Any]:
    if obj is None:
        return None, None
    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        return _safe_num(obj[0]), _safe_num(obj[1])
    if isinstance(obj, dict):
        return _safe_num(obj.get(key_home)), _safe_num(obj.get(key_away))
    return None, None


def _get(d: Dict, *path: str, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def extract_match_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza analyst-1, skill-feed-1/2 ou payload solto."""
    schema = payload.get("schema") or payload.get("type") or ""

    # cornerai-analyst-1 (schema real da extensão)
    # fixture + pressure.* + corners.total / corners.events
    if schema == "cornerai-analyst-1" or (
        isinstance(payload.get("fixture"), dict) and "pressure" in payload
    ) or (
        isinstance(payload.get("fixture"), dict) and "corners" in payload
    ):
        fix = payload.get("fixture") or {}
        pressure = payload.get("pressure") or {}
        corners_block = payload.get("corners") if isinstance(payload.get("corners"), dict) else {}
        stats = payload.get("stats") or {}  # fallback se vier em formato antigo
        score = fix.get("score")
        sh, sa = _pair(score)
        if isinstance(score, dict):
            sh, sa = _pair(score)

        corners_h, corners_a = _pair(corners_block.get("total"))
        if corners_h is None and corners_a is None:
            corners_h, corners_a = _pair(stats.get("corners"))

        dang_h, dang_a = _pair(pressure.get("dangerous"))
        if dang_h is None and dang_a is None:
            dang_h, dang_a = _pair(stats.get("dangerous"))

        att_h, att_a = _pair(pressure.get("attacks"))
        if att_h is None and att_a is None:
            att_h, att_a = _pair(stats.get("attacks"))

        shots_h, shots_a = _pair(pressure.get("shotsOn"))
        xg_h, xg_a = _pair(pressure.get("xg"))
        if xg_h is None and xg_a is None:
            xg_h, xg_a = _pair(stats.get("xg"))
        poss_h, poss_a = _pair(pressure.get("possession"))
        if poss_h is None and poss_a is None:
            poss_h, poss_a = _pair(stats.get("possession"))

        events = corners_block.get("events") if corners_block else None
        if events is None:
            events = payload.get("corner_events") or payload.get("ce") or []

        am = payload.get("advanced_metrics") or {}
        return {
            "schema": schema or "cornerai-analyst-1",
            "fixture_id": fix.get("id"),
            "league": fix.get("league"),
            "home": fix.get("home"),
            "away": fix.get("away"),
            "minute": fix.get("minute"),
            "extra": fix.get("extra") or 0,
            "period": fix.get("period"),
            "status": fix.get("status"),
            "score_home": sh,
            "score_away": sa,
            "corners_home": corners_h,
            "corners_away": corners_a,
            "attacks_home": att_h,
            "attacks_away": att_a,
            "dangerous_home": dang_h,
            "dangerous_away": dang_a,
            "xg_home": xg_h,
            "xg_away": xg_a,
            "possession_home": poss_h,
            "possession_away": poss_a,
            "shots_on_home": shots_h,
            "shots_on_away": shots_a,
            "corner_events": events or [],
            "cpi_home": _get(am, "CPI_v2", "home", "cpi"),
            "cpi_away": _get(am, "CPI_v2", "away", "cpi"),
            "pred": _get(am, "temporal", "prediction_corner_2m"),
            "raw_ts": payload.get("ts") or payload.get("exportedAt"),
            "quality": (payload.get("quality") or {}).get("score")
            if isinstance(payload.get("quality"), dict)
            else payload.get("quality"),
        }

    # cornerai-skill-feed-1 / micro
    if schema in ("cornerai-skill-feed-1", "cornerai-gemini-compact-1") or "match_id" in payload or "home" in payload:
        match = payload.get("match") or {}
        stats = payload.get("stats") or {}
        ce = payload.get("corner_events") or payload.get("ce") or []
        if ce and isinstance(ce[0], (list, tuple)):
            ce = [{"minute": c[0], "team": c[1] if len(c) > 1 else None} for c in ce]
        sh, sa = payload.get("score_home"), payload.get("score_away")
        if sh is None and match:
            sh, sa = _pair(match.get("score"))
        ch, ca = payload.get("corners_home"), payload.get("corners_away")
        if ch is None and stats:
            ch, ca = _pair(stats.get("corners"))
        return {
            "schema": schema or "cornerai-skill-feed-1",
            "fixture_id": payload.get("match_id") or match.get("fixtureId") or payload.get("fixtureId"),
            "league": payload.get("league"),
            "home": payload.get("home") or match.get("home"),
            "away": payload.get("away") or match.get("away"),
            "minute": payload.get("minute") if payload.get("minute") is not None else match.get("minute"),
            "extra": payload.get("extra") or match.get("extraMinute") or 0,
            "period": payload.get("period"),
            "score_home": sh,
            "score_away": sa,
            "corners_home": ch,
            "corners_away": ca,
            "attacks_home": payload.get("attacks_home") or _pair(stats.get("attacks"))[0],
            "attacks_away": payload.get("attacks_away") or _pair(stats.get("attacks"))[1],
            "dangerous_home": payload.get("dangerous_home") or _pair(stats.get("dangerous"))[0],
            "dangerous_away": payload.get("dangerous_away") or _pair(stats.get("dangerous"))[1],
            "xg_home": payload.get("xg_home") or _pair(stats.get("xg"))[0],
            "xg_away": payload.get("xg_away") or _pair(stats.get("xg"))[1],
            "possession_home": payload.get("possession_home") or _pair(stats.get("possession"))[0],
            "possession_away": payload.get("possession_away") or _pair(stats.get("possession"))[1],
            "shots_on_home": payload.get("shots_on_home") or _pair(stats.get("shotsOn"))[0],
            "shots_on_away": payload.get("shots_on_away") or _pair(stats.get("shotsOn"))[1],
            "corner_events": ce,
            "cpi_home": payload.get("cpi_home") or (payload.get("metrics") or {}).get("CPI", [None, None])[0]
            if isinstance((payload.get("metrics") or {}).get("CPI"), list)
            else payload.get("cpi_home"),
            "cpi_away": payload.get("cpi_away"),
            "pred": payload.get("mc_hint") or (payload.get("metrics") or {}).get("p2"),
            "raw_ts": payload.get("ts"),
            "live": payload.get("live"),
            "status": payload.get("status") or match.get("status"),
        }

    # nested analyst inside handoff
    for key in ("analyst", "feed", "payload", "data"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            return extract_match_view(inner)

    return {
        "schema": schema or "unknown",
        "fixture_id": payload.get("fixtureId"),
        "home": payload.get("home"),
        "away": payload.get("away"),
        "minute": payload.get("minute"),
        "score_home": payload.get("score_home"),
        "score_away": payload.get("score_away"),
        "corner_events": payload.get("corner_events") or [],
        "raw_ts": payload.get("ts"),
    }


def fingerprint(view: Dict[str, Any]) -> str:
    return "|".join(
        str(x)
        for x in (
            view.get("fixture_id"),
            view.get("minute"),
            view.get("score_home"),
            view.get("score_away"),
            view.get("corners_home"),
            view.get("corners_away"),
            view.get("dangerous_home"),
            view.get("dangerous_away"),
        )
    )


def window_label(minute: Any, period: Any = None) -> str:
    try:
        m = int(minute)
    except (TypeError, ValueError):
        return "OUT"
    if period == 1 or (period is None and m <= 48):
        if 30 <= m <= 48:
            return "W1"
        return "OUT"
    if m >= 80:
        return "W2"
    return "OUT"


def last_corner_gap(view: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    events = view.get("corner_events") or []
    if not events:
        return None, None
    last = events[-1]
    if isinstance(last, dict):
        lm = last.get("minute") or last.get("m")
        side = last.get("team") or last.get("side")
    elif isinstance(last, (list, tuple)):
        lm = last[0] if last else None
        side = last[1] if len(last) > 1 else None
    else:
        return None, None
    try:
        gap = int(view.get("minute")) - int(lm) if view.get("minute") is not None and lm is not None else None
    except (TypeError, ValueError):
        gap = None
    return gap, side


def build_reg_markdown(reg_id: str, view: Dict[str, Any], payload: Dict[str, Any]) -> str:
    gap, last_side = last_corner_gap(view)
    minute = view.get("minute")
    win = window_label(minute, view.get("period"))
    ts = _now_iso()
    home = view.get("home") or "?"
    away = view.get("away") or "?"
    lines = [
        f"### {reg_id}",
        f"**Timestamp solicitação:** {ts}",
        f"**Tipo:** ANALISE_LIVE",
        "",
        "#### 1. Identificação",
        f"- {view.get('league') or 'N/D'} | {home} × {away}",
        f"- Fixture: {view.get('fixture_id') or 'N/D'} | Janela: {win}",
        f"- Schema feed: {view.get('schema')}",
        "",
        "#### 3. Relógio e placar",
        f"- Minuto: {minute}' (+{view.get('extra') or 0}) | Placar: {view.get('score_home')}×{view.get('score_away')}",
        f"- Status: {view.get('status') or ('live' if view.get('live') else 'N/D')}",
        "",
        "#### 5. Estatísticas (Casa | Visitante)",
        f"| Ataques | {view.get('attacks_home')} | {view.get('attacks_away')} |",
        f"| AP (dangerous) | {view.get('dangerous_home')} | {view.get('dangerous_away')} |",
        f"| Posse % | {view.get('possession_home')} | {view.get('possession_away')} |",
        f"| Finalizações (gol) | {view.get('shots_on_home')} | {view.get('shots_on_away')} |",
        f"| Escanteios | {view.get('corners_home')} | {view.get('corners_away')} |",
        f"| xG | {view.get('xg_home')} | {view.get('xg_away')} |",
        f"| CPI | {view.get('cpi_home')} | {view.get('cpi_away')} |",
        f"| Gap último canto | {gap} min | lado={last_side} |",
        "",
        "#### 6. Eventos de canto (últimos)",
    ]
    for e in (view.get("corner_events") or [])[-12:]:
        if isinstance(e, dict):
            lines.append(f"- {e.get('minute') or e.get('m')}' · {e.get('team') or e.get('side')}")
        else:
            lines.append(f"- {e}")
    pred = view.get("pred")
    lines += [
        "",
        "#### 7. CornerAI — cálculo",
        "- Score: *(preencher pela skill / Auto-Gemini)*",
        "- Bônus aplicados:",
        "- Kills aplicados:",
        f"- MC / pred feed: {json.dumps(pred, ensure_ascii=False) if pred else 'N/D'}",
        "- Gatilhos 2-de-3:",
        "- Must Win:",
        "- Stop-Live 65: N/D",
        "",
        "#### 8. Decisão",
        "- **AGUARDA** *(bridge só armazena — decisão vem da skill/Gemini)*",
        "",
        "#### 9. Resultado (POS_JOGO — preencher depois)",
        "- Minuto real canto:",
        "- Acerto/Erro:",
        "- Cantos finais Casa | Visitante | Total:",
        "",
        "<details><summary>payload bruto (compacto)</summary>",
        "",
        "```json",
        json.dumps(
            {
                k: view.get(k)
                for k in (
                    "fixture_id",
                    "home",
                    "away",
                    "minute",
                    "score_home",
                    "score_away",
                    "corners_home",
                    "corners_away",
                    "dangerous_home",
                    "dangerous_away",
                    "xg_home",
                    "xg_away",
                    "cpi_home",
                    "cpi_away",
                )
            },
            ensure_ascii=False,
        ),
        "```",
        "",
        "</details>",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def ensure_log_header() -> None:
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 0:
        return
    LOG_FILE.write_text(
        "# CornerAI — Log Oficial de Análises (bridge live)\n\n"
        "Gerado por `server.py`. Cada push da extensão pode criar um REG.\n\n"
        "## Índice\n\n"
        "| ID | Timestamp | Partida | Min | Decisão |\n"
        "|----|-----------|---------|-----|--------|\n\n"
        "---\n\n## Registros\n\n",
        encoding="utf-8",
    )


def append_index_row(reg_id: str, view: Dict[str, Any]) -> None:
    # lightweight: append a comment line; full table edit is expensive
    row = (
        f"<!-- index {reg_id} | {_now_iso()} | "
        f"{view.get('home')} x {view.get('away')} | {view.get('minute')}' -->\n"
    )
    with _lock:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(row)


def _is_empty_view(view: Dict[str, Any]) -> bool:
    """Sem times = payload inútil (aba lista / estado vazio)."""
    home = view.get("home")
    away = view.get("away")
    if not home and not away:
        return True
    if home in (None, "", "None") and away in (None, "", "None"):
        return True
    return False


def persist_feed(payload: Dict[str, Any]) -> Dict[str, Any]:
    """v2: valida -> normaliza -> publica no bus. ZERO I/O de disco no handler (quando BUS ativo)."""
    view = extract_match_view(payload)
    if _is_empty_view(view):
        return {"ok": True, "skipped": "empty", "reg": None,
                "view": {"home": None, "away": None, "minute": None,
                         "corners": [None, None]}}
    fp = fingerprint(view)

    # Preferir bus nao-bloqueante; fallback sync se bus nao subiu
    if BUS is not None:
        accepted = BUS.publish(
            {"received_at": _now_iso(), "view": view, "payload": payload,
             "fingerprint": fp},
            key=str(view.get("fixture_id") or "unknown"))
        return {
            "ok": bool(accepted), "reg": None, "fingerprint": fp, "queued": bool(accepted),
            "view": {
                "home": view.get("home"), "away": view.get("away"),
                "minute": view.get("minute"),
                "score": [view.get("score_home"), view.get("score_away")],
                "corners": [view.get("corners_home"), view.get("corners_away")],
                "dangerous": [view.get("dangerous_home"), view.get("dangerous_away")],
                "xg": [view.get("xg_home"), view.get("xg_away")],
            },
            "files": {"jsonl": str(FEED_FILE), "latest": str(LATEST_FILE),
                      "log": str(LOG_FILE)},
        }

    # --- fallback legado (BUS indisponivel) ---
    global _last_fingerprint, _last_log_key, _last_log_at
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REGS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_log_header()
    record = {
        "received_at": _now_iso(),
        "fingerprint": fp,
        "view": view,
        "payload": payload,
    }
    with _lock:
        _queue_fallback_record(record)
        LATEST_FILE.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    created_reg = None
    if fp != _last_fingerprint and (view.get("fixture_id") or view.get("home")):
        reg_id = _next_reg_id()
        md = build_reg_markdown(reg_id, view, payload)
        (REGS_DIR / f"{reg_id}.md").write_text(md, encoding="utf-8")
        with _lock:
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(md + "\n")
        append_index_row(reg_id, view)
        created_reg = reg_id
        _last_fingerprint = fp
    try:
        pack = view_to_skill_pack(view, payload)
        persist_skill_pack({"json": pack, "pack": pack})
    except Exception as _e:
        print(f"[skill] auto-write fail: {_e}", flush=True)
    return {
        "ok": True,
        "reg": created_reg,
        "fingerprint": fp,
        "view": {
            "home": view.get("home"),
            "away": view.get("away"),
            "minute": view.get("minute"),
            "score": [view.get("score_home"), view.get("score_away")],
            "corners": [view.get("corners_home"), view.get("corners_away")],
            "dangerous": [view.get("dangerous_home"), view.get("dangerous_away")],
            "xg": [view.get("xg_home"), view.get("xg_away")],
        },
        "files": {
            "jsonl": str(FEED_FILE),
            "latest": str(LATEST_FILE),
            "log": str(LOG_FILE),
        },
    }




def view_to_skill_pack(view: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Monta pack manual completo a partir do feed automatico da extensao (dashboard 100%)."""
    # Se o payload já é um skill pack completo da extensão, preserva integralmente
    schema = str(payload.get("schema") or "")
    if schema.startswith("cornerai-skill-manual") or schema.startswith("cornerai-skill-v") and "match" in payload and "stats" in payload:
        pack = dict(payload)
        pack["exportedAt"] = _now_iso()
        pack["source"] = pack.get("source") or "bridge-passthrough"
        return pack

    minute = view.get("minute")
    try:
        m = int(minute) if minute is not None else None
    except (TypeError, ValueError):
        m = None
    if m is not None and 30 <= m <= 48:
        win = "W1"
    elif m is not None and m >= 80:
        win = "W2"
    else:
        win = "OUT"

    # Preferir stats completos do payload quando existirem
    stats_src = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    pressure_src = payload.get("pressure") if isinstance(payload.get("pressure"), dict) else {}

    def _stat(key: str, vh, va):
        if key in stats_src and isinstance(stats_src[key], (list, dict)):
            return stats_src[key] if isinstance(stats_src[key], list) else [stats_src[key].get("home"), stats_src[key].get("away")]
        if key in pressure_src and isinstance(pressure_src[key], (list, dict)):
            p = pressure_src[key]
            return p if isinstance(p, list) else [p.get("home"), p.get("away")]
        return [vh, va]

    full_stats = {
        "corners": _stat("corners", view.get("corners_home"), view.get("corners_away")),
        "attacks": _stat("attacks", view.get("attacks_home"), view.get("attacks_away")),
        "dangerous": _stat("dangerous", view.get("dangerous_home"), view.get("dangerous_away")),
        "shotsOn": _stat("shotsOn", view.get("shots_on_home"), view.get("shots_on_away")),
        "shots": _stat("shots", None, None),
        "shotsOff": _stat("shotsOff", None, None),
        "possession": _stat("possession", view.get("possession_home"), view.get("possession_away")),
        "xg": _stat("xg", view.get("xg_home"), view.get("xg_away")),
        "fouls": _stat("fouls", None, None),
        "offsides": _stat("offsides", None, None),
        "yellow": _stat("yellow", None, None),
        "red": _stat("red", None, None),
        "subs": _stat("subs", None, None),
        "crosses": _stat("crosses", None, None),
        "saves": _stat("saves", None, None),
        "passes": _stat("passes", None, None),
        "passesFailed": _stat("passesFailed", None, None),
    }
    # merge qualquer chave extra de stats_src
    for k, v in stats_src.items():
        if k not in full_stats:
            full_stats[k] = v if isinstance(v, list) else ([v.get("home"), v.get("away")] if isinstance(v, dict) else v)

    pack = {
        "schema": "cornerai-skill-manual-2",
        "exportedAt": _now_iso(),
        "source": "bridge-auto-feed",
        "instruction": "Analise com CornerAI v9.3.1-TRADER (Timing, Gate 2/3, Score, MC, kills). Responda no formato operacional ENTRA|AGUARDA|NÃO ENTRA. Não invente stats ausentes. Use TODOS os campos (dashboard 100%).",
        "match": {
            "fixtureId": view.get("fixture_id") or payload.get("fixtureId"),
            "league": view.get("league"),
            "home": view.get("home"),
            "away": view.get("away"),
            "minute": view.get("minute"),
            "extra": view.get("extra") or 0,
            "period": view.get("period"),
            "status": view.get("status") or "live",
            "score_home": view.get("score_home"),
            "score_away": view.get("score_away"),
            "score": [view.get("score_home"), view.get("score_away")],
            "dataMode": payload.get("dataMode") or view.get("dataMode"),
            "url": payload.get("url") or view.get("url"),
        },
        "stats": full_stats,
        "pressure": {
            "attacks": full_stats["attacks"],
            "dangerous": full_stats["dangerous"],
            "shotsOn": full_stats["shotsOn"],
            "possession": full_stats["possession"],
            "xg": full_stats["xg"],
        },
        "extendedStats": payload.get("extendedStats") or {},
        "corner_events": view.get("corner_events") or payload.get("corner_events") or payload.get("ce") or [],
        "match_events": payload.get("match_events") or payload.get("matchEvents") or [],
        "cpi": [view.get("cpi_home"), view.get("cpi_away")],
        "cpi_detail": payload.get("cpi_detail") or payload.get("cpi"),
        "pred": view.get("pred") or payload.get("pred"),
        "quality": view.get("quality") or payload.get("quality"),
        "charts": payload.get("charts"),
        "odds": payload.get("odds"),
        "h2h": payload.get("h2h"),
        "teamHistory": payload.get("teamHistory"),
        "timeline": payload.get("timeline") or payload.get("statTimeline"),
        "diagnostics": payload.get("diagnostics"),
        "sources": payload.get("sources"),
        "analyst_raw": payload.get("analyst_raw") or (payload if "fixture" in payload else None),
        "window": win,
    }
    return pack


def validate_skill_pack(pack: Dict[str, Any]) -> list:
    """Validacao estrita: cornerai-skill-v3 (preferencial) ou manual-2 (legado)."""
    errors: list = []

    def req_pair(v, path):
        if not (isinstance(v, list) and len(v) == 2):
            errors.append(f"{path}: esperado par [home,away], recebi {v!r}")
            return
        for i, x in enumerate(v):
            if x is not None and not isinstance(x, (int, float)):
                errors.append(f"{path}[{i}]: esperado number|null, recebi {type(x).__name__}")

    if not isinstance(pack, dict):
        return ["payload raiz nao e um objeto"]

    schema = pack.get("schema")
    if schema not in ("cornerai-skill-v3", "cornerai-skill-manual-2"):
        errors.append(f"schema: esperado cornerai-skill-v3|cornerai-skill-manual-2, recebi {schema!r}")

    # --- v3 ---
    if schema == "cornerai-skill-v3":
        meta = pack.get("meta") or {}
        if not isinstance(meta.get("exportedAtMs"), (int, float)):
            errors.append("meta.exportedAtMs: number obrigatorio")
        if not isinstance(meta.get("fixtureId"), str) or not meta.get("fixtureId"):
            errors.append("meta.fixtureId ausente")
        if "skillReady" in meta and not isinstance(meta.get("skillReady"), bool):
            errors.append("meta.skillReady: boolean")
        sha = meta.get("contentSha256")
        if not isinstance(sha, str) or len(sha) < 16:
            errors.append("meta.contentSha256 ausente/curto")
        match = pack.get("match") or {}
        if not isinstance(match.get("home"), str) or not str(match.get("home") or "").strip():
            errors.append("match.home ausente")
        if not isinstance(match.get("away"), str) or not str(match.get("away") or "").strip():
            errors.append("match.away ausente")
        minute = match.get("minute")
        if minute is not None and (not isinstance(minute, (int, float)) or not (0 <= minute <= 130)):
            errors.append(f"match.minute fora 0-130: {minute!r}")
        if "score" in match:
            req_pair(match.get("score"), "match.score")
        pairs = ((pack.get("teams") or {}).get("pairs")) or {}
        for key in ("corners", "attacks", "dangerous", "shotsOn", "xg", "possession"):
            if key in pairs:
                req_pair(pairs[key], f"teams.pairs.{key}")
        timeline = pack.get("timeline") or {}
        if not isinstance(timeline.get("corners"), list):
            errors.append("timeline.corners: array obrigatorio")
        if not isinstance(timeline.get("events"), list):
            errors.append("timeline.events: array obrigatorio")
        if meta.get("skillReady") is False:
            errors.append("skillReady=false: captura nao estavel")
        stale = meta.get("skillStaleMs")
        if isinstance(stale, (int, float)) and stale > 120000:
            errors.append(f"skillStaleMs={stale}: dados >2min")
        # aliases legados opcionais no mesmo pack
        return errors

    # --- legado manual-2 ---
    if "stateVersion" in pack and (not isinstance(pack.get("stateVersion"), (int, float)) or pack.get("stateVersion") < 0):
        errors.append("stateVersion: esperado number >= 0")
    if "skillReady" in pack and not isinstance(pack.get("skillReady"), bool):
        errors.append("skillReady: esperado boolean")
    match = pack.get("match") or {}
    if not isinstance(match.get("home"), str) or not match.get("home", "").strip():
        errors.append(f"match.home: esperado string nao-vazia, recebi {match.get('home')!r}")
    if not isinstance(match.get("away"), str) or not match.get("away", "").strip():
        errors.append(f"match.away: esperado string nao-vazia, recebi {match.get('away')!r}")
    minute = match.get("minute")
    if minute is not None and (not isinstance(minute, (int, float)) or not (0 <= minute <= 130)):
        errors.append(f"match.minute: fora do range 0-130, recebi {minute!r}")
    if "score" in match:
        req_pair(match.get("score"), "match.score")
    stats = pack.get("stats") or {}
    for key in ("corners", "attacks", "dangerous", "shotsOn", "possession", "xg"):
        if key in stats:
            req_pair(stats[key], f"stats.{key}")
        else:
            errors.append(f"stats.{key}: chave ausente")
    if not isinstance(pack.get("corner_events", []), list):
        errors.append("corner_events: esperado array")
    if not isinstance(pack.get("match_events", []), list):
        errors.append("match_events: esperado array")
    if pack.get("skillReady") is False:
        errors.append("skillReady=false: captura ainda nao possui fixture/times/status estavel")
    stale = pack.get("skillStaleMs")
    if isinstance(stale, (int, float)) and stale > 120000:
        errors.append(f"skillStaleMs={stale}: dados com mais de 2 minutos sem atualizacao")
    return errors


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Escrita atômica no mesmo diretório: temp + os.replace.
    Qualquer leitor vê apenas a versão anterior completa ou a nova completa —
    nunca um JSON truncado no meio da gravação.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        # os.replace é atômico no mesmo filesystem (POSIX e Windows modernos)
        os.replace(str(tmp), str(path))
    except Exception:
        # Limpa temp em caso de falha para não deixar lixo
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def persist_skill_pack(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reescreve sempre os mesmos arquivos para a skill consumir manualmente."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Aceita pack direto ou envelope {json/pack/pasteText}
    pack = payload.get("json") or payload.get("pack") or payload
    if not isinstance(pack, dict):
        pack = {"raw": pack}

    # [FIX v6.9.9.67] aborta a escrita em disco se o payload estiver corrompido —
    # o skill_feed_latest.json anterior (valido) permanece intacto no lugar.
    validation_errors = validate_skill_pack(pack)
    if validation_errors:
        print("[skill] EXPORTACAO ABORTADA - payload invalido:", flush=True)
        for e in validation_errors:
            print(f"  - {e}", flush=True)
        return {
            "ok": False,
            "error": "validation_failed",
            "errors": validation_errors,
        }
    paste = payload.get("pasteText")
    if not paste:
        paste = (
            "### CORNERAI INGEST — skill manual\n"
            "Analise com pipeline v9.3.1-TRADER. Não invente dados.\n"
            "```json\n"
            + json.dumps(pack, ensure_ascii=False, indent=2)
            + "\n```\n"
            "Responda no formato: DECISÃO | TIMING | LADO | GATE | PRESSÃO | MC | KILLS | JUSTIFICATIVA | REG\n"
        )
    record = {
        "received_at": _now_iso(),
        "pack": pack,
        "pasteText": paste,
    }
    # [FIX v6.9.9.93-resilient] escrita atômica + lock:
    # - writers serializados pelo _lock
    # - cada arquivo é promovido via os.replace (nunca truncado à vista de leitores)
    json_text = json.dumps(pack, ensure_ascii=False, indent=2)
    # Coleta em lote: grava cópia por fixture em bridge/batch/
    batch_name = payload.get("filename") or pack.get("_batchFile")
    batch_path = None
    if batch_name:
        safe = re.sub(r"[^\w.\-]+", "_", str(batch_name)).strip("._") or "skill_batch.json"
        if not safe.endswith(".json"):
            safe += ".json"
        batch_dir = DATA_DIR / "batch"
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_path = batch_dir / safe

    # Arquivo ÚNICO do dia: daily/YYYY-MM-DD.json (lista de jogos, upsert por fixtureId)
    daily = bool(payload.get("daily")) or bool(pack.get("_daily")) or bool(payload.get("singleDailyFile"))
    daily_day = str(payload.get("dailyDay") or "").strip()
    if not daily_day:
        daily_day = datetime.now().astimezone().strftime("%Y-%m-%d")
    daily_file = None
    daily_md = None
    daily_action = None
    if daily:
        daily_dir = DATA_DIR / "daily"
        daily_file = daily_dir / f"{daily_day}.json"
        daily_md = daily_dir / f"{daily_day}.md"

    with _lock:
        _atomic_write_text(SKILL_JSON, json_text)
        _atomic_write_text(SKILL_MD, paste)
        if batch_path is not None:
            _atomic_write_text(batch_path, json_text)
        if daily and daily_file is not None:
            daily_file.parent.mkdir(parents=True, exist_ok=True)
            fid = str(
                payload.get("dailyFixtureId")
                or (pack.get("match") or {}).get("fixtureId")
                or "unknown"
            )
            fp = payload.get("dailyFingerprint")
            # carrega arquivo único do dia
            doc = {"schema": "cornerai-daily-1", "day": daily_day, "updatedAt": _now_iso(), "matches": []}
            if daily_file.exists():
                try:
                    loaded = json.loads(daily_file.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict) and isinstance(loaded.get("matches"), list):
                        doc = loaded
                    elif isinstance(loaded, list):
                        doc["matches"] = loaded
                except Exception:
                    doc = {"schema": "cornerai-daily-1", "day": daily_day, "updatedAt": _now_iso(), "matches": []}
            matches = list(doc.get("matches") or [])
            entry = {
                "fixtureId": fid,
                "savedAt": record["received_at"],
                "fingerprint": fp,
                "match": pack.get("match"),
                "decision_frame": pack.get("decision_frame"),
                "stats": pack.get("stats"),
                "pressure": pack.get("pressure"),
                "corners": pack.get("corners"),
                "context": pack.get("context"),
                "window": pack.get("window"),
                "skillReady": pack.get("skillReady"),
                "pasteText": paste,
                "pack": pack,
            }
            idx_m = next((i for i, m in enumerate(matches) if str(m.get("fixtureId")) == str(fid)), None)
            if idx_m is None:
                matches.append(entry)
                daily_action = "added"
            else:
                prev = matches[idx_m]
                prev_fp = prev.get("fingerprint")
                if prev_fp and fp and prev_fp == fp:
                    daily_action = "unchanged"
                    # mantém o anterior
                else:
                    matches[idx_m] = entry
                    daily_action = "updated"
            doc["matches"] = matches
            doc["updatedAt"] = _now_iso()
            doc["count"] = len(matches)
            _atomic_write_text(daily_file, json.dumps(doc, ensure_ascii=False, indent=2))
            # índice MD reescrito (sempre coerente com o JSON único)
            lines = [
                f"# CornerAI — jogos do dia {daily_day}",
                "",
                f"Arquivo único: `{daily_file.name}` · {len(matches)} jogo(s) · atualizado {doc['updatedAt']}",
                "",
            ]
            for m in matches:
                mm = m.get("match") or {}
                lines.append(
                    f"- **{mm.get('home') or '?'}** {mm.get('score_home') if mm.get('score_home') is not None else '?'}×"
                    f"{mm.get('score_away') if mm.get('score_away') is not None else '?'} **{mm.get('away') or '?'}** · "
                    f"{mm.get('minute')}' · {mm.get('status')} · fixture `{m.get('fixtureId')}` · {m.get('savedAt')}"
                )
            lines.append("")
            _atomic_write_text(daily_md, "\n".join(lines) + "\n")
        with SKILL_HISTORY.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "received_at": record["received_at"],
                        "match": pack.get("match"),
                        "window": pack.get("window"),
                        "batch": str(batch_path) if batch_path else None,
                        "daily": str(daily_file) if daily_file else None,
                        "dailyAction": daily_action,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    match = pack.get("match") or {}
    print(
        f"[skill] reescrito skill_feed_latest.json · "
        f"{match.get('home')} x {match.get('away')} · {match.get('minute')}' · win={pack.get('window')}"
        + (f" · batch={batch_path.name}" if batch_path else "")
        + (f" · daily={daily_day}/{daily_action}" if daily else ""),
        flush=True,
    )
    files = {
        "json": str(SKILL_JSON),
        "md": str(SKILL_MD),
        "history": str(SKILL_HISTORY),
    }
    if batch_path is not None:
        files["batch"] = str(batch_path)
    if daily and daily_file is not None:
        files["daily"] = str(daily_file)
        files["daily_md"] = str(daily_md)
    return {
        "ok": True,
        "files": files,
        "match": match,
        "dailyAction": daily_action,
    }




# V23 BLOCO 4: Rate limiter no feed (anti-flood)
class RateLimiter:
    def __init__(self, max_requests: int = 15, window_seconds: float = 2.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = []  # type: list

    def is_allowed(self, client_ip: str = "unknown") -> bool:
        now = time.time()
        self.requests = [t for t in self.requests if now - t < self.window]
        if len(self.requests) >= self.max_requests:
            return False
        self.requests.append(now)
        return True


feed_limiter = RateLimiter(max_requests=15, window_seconds=2.0)


class Handler(BaseHTTPRequestHandler):
    server_version = "CornerAIBridge/1.0"

    def _origin_allowed(self, origin: str) -> bool:
        if not origin:
            return True
        if origin in _ALLOWED_ORIGINS:
            return True
        return False

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if self._origin_allowed(origin):
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        elif origin:
            self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-CornerAI-Token, X-CornerAI-Schema, X-CornerAI-Version, X-Requested-With",
        )
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Access-Control-Expose-Headers", "X-CornerAI-Bridge")

    def _auth_ok(self) -> bool:
        if not _BRIDGE_TOKEN:
            return not _REQUIRE_BRIDGE_TOKEN
        token = self.headers.get("X-CornerAI-Token", "").strip()
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = token or auth[7:].strip()
        return hmac.compare_digest(token, _BRIDGE_TOKEN)

    def _json(self, code: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-CornerAI-Bridge", "ok" if code < 400 else "error")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in ("/", "/health", "/api/cornerai/health", "/metrics", "/api/metrics", "/api/status", "/status") and not self._auth_ok():
            self._json(401, {"ok": False, "error": "bridge_auth_required"})
            return
        if path in ("/", "/health", "/api/cornerai/health"):
            feed_lines = 0
            latest_age_s = None
            try:
                if FEED_FILE.exists():
                    with FEED_FILE.open("r", encoding="utf-8", errors="ignore") as fh:
                        feed_lines = sum(1 for _ in fh)
            except Exception:
                feed_lines = -1
            try:
                if LATEST_FILE.exists():
                    import time as _time
                    latest_age_s = round(_time.time() - LATEST_FILE.stat().st_mtime, 1)
            except Exception:
                latest_age_s = None
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-CornerAI-Bridge", "ok")
            self._cors()
            body = {
                "ok": True,
                "service": "cornerai-bridge",
                "version": BRIDGE_VERSION,
                "feed": str(FEED_FILE),
                "feedLines": feed_lines,
                "latest": str(LATEST_FILE),
                "latestAgeSec": latest_age_s,
                "log": str(LOG_FILE),
                "regs": str(REGS_DIR),
                "skillJson": str(SKILL_JSON),
                "skillMd": str(SKILL_MD),
                "time": _now_iso(),
                "endpoints": {
                    "feed": "/api/cornerai/feed",
                    "skillFeed": "/api/cornerai/skill-feed",
                    "health": "/health",
                    "skill": "/skill",
                },
            }
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path in ("/skill", "/api/cornerai/skill", "/colar"):
            # Pagina unica: Ctrl+A Ctrl+C ou botao copiar
            # [FIX v6.9.9.93-resilient] lê sob o mesmo _lock dos escritores
            md = ""
            with _lock:
                if SKILL_MD.exists():
                    try:
                        md = SKILL_MD.read_text(encoding="utf-8")
                    except Exception:
                        md = "(erro ao ler skill_feed_for_chat.md)"
                elif SKILL_JSON.exists():
                    try:
                        import json as _json
                        pack = _json.loads(SKILL_JSON.read_text(encoding="utf-8"))
                        md = (
                            "### CORNERAI INGEST — skill manual\n"
                            "Analise com pipeline v9.3.1-TRADER. Nao invente dados.\n"
                            "```json\n"
                            + _json.dumps(pack, ensure_ascii=False, indent=2)
                            + "\n```\n"
                            "Responda no formato: DECISAO | TIMING | LADO | GATE | PRESSAO | MC | KILLS | JUSTIFICATIVA | REG\n"
                        )
                    except Exception as e:
                        md = f"(erro: {e})"
                else:
                    md = (
                        "Ainda sem dados.\n"
                        "1) Deixe a extensao em partida LIVE\n"
                        "2) Bridge ligado\n"
                        "3) Aguarde um feed ou clique Atualizar JSON no popup\n"
                        "4) Atualize esta pagina (F5)\n"
                    )
            # escape for HTML
            safe = (
                md.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CornerAI → Skill</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f1419;color:#e7ecf3;margin:0;padding:16px}}
h1{{font-size:18px;margin:0 0 8px}}
.sub{{opacity:.7;font-size:13px;margin-bottom:12px}}
button{{background:#3b82f6;color:#fff;border:0;padding:12px 18px;border-radius:8px;font-size:15px;cursor:pointer;margin-right:8px}}
button.sec{{background:#334155}}
button:active{{transform:scale(.98)}}
#ok{{color:#4ade80;margin-left:8px;font-size:13px}}
pre{{background:#1a2332;padding:14px;border-radius:8px;overflow:auto;max-height:70vh;white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.4}}
a{{color:#93c5fd}}
</style></head><body>
<h1>CornerAI → colar na skill</h1>
<div class="sub">Mesma URL sempre · dados reescritos pelo bridge · F5 para atualizar</div>
<button type="button" id="copy">Copiar tudo</button>
<button type="button" class="sec" id="reload">Atualizar pagina</button>
<span id="ok"></span>
<pre id="box">{safe}</pre>
<p class="sub">Chat da skill → Ctrl+V. Ou clique em Copiar tudo.</p>
<script>
const box=document.getElementById('box');
document.getElementById('copy').onclick=async()=>{{
  const t=box.innerText;
  try{{
    await navigator.clipboard.writeText(t);
    document.getElementById('ok').textContent='Copiado! Cole no chat da skill (Ctrl+V)';
  }}catch(e){{
    const r=document.createRange(); r.selectNodeContents(box);
    const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    document.getElementById('ok').textContent='Selecionei o texto — Ctrl+C e cole no chat';
  }}
}};
document.getElementById('reload').onclick=()=>location.reload();
</script>
</body></html>"""
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(data)
            return

        if path in ("/api/cornerai/skill-feed", "/skill-feed", "/api/cornerai/skill-latest"):
            # [FIX v6.9.9.93-resilient] leitura sob _lock + arquivo promovido atomicamente
            with _lock:
                exists = SKILL_JSON.exists()
                if exists:
                    try:
                        body = json.loads(SKILL_JSON.read_text(encoding="utf-8"))
                    except Exception as e:
                        self._json(500, {"ok": False, "error": str(e)})
                        return
            if exists:
                self._json(200, {"ok": True, "skill": body, "file": str(SKILL_JSON), "md": str(SKILL_MD)})
            else:
                self._json(404, {"ok": False, "error": "skill_feed_latest.json ainda nao gerado — clique Atualizar JSON na extensao"})
            return
        if path in ("/metrics", "/api/metrics"):
            # Metricas leves JSON (Prometheus-texto completo e roadmap)
            ring_len = 0
            try:
                with _BUFFER_LOCK:
                    ring_len = len(_FEED_RING_BUFFER)
            except Exception:
                pass
            body = {
                "service": "cornerai-bridge",
                "version": BRIDGE_VERSION,
                "feed_lines_hint": -1,
                "ring_buffer": ring_len,
                "require_token": _REQUIRE_BRIDGE_TOKEN,
                "token_configured": bool(_BRIDGE_TOKEN),
                "feed_bus": BUS is not None if "BUS" in dir() else False,
            }
            try:
                if FEED_FILE.exists():
                    body["feed_size_bytes"] = FEED_FILE.stat().st_size
                if LATEST_FILE.exists():
                    body["latest_size_bytes"] = LATEST_FILE.stat().st_size
                    body["latest_age_sec"] = round(time.time() - LATEST_FILE.stat().st_mtime, 1)
            except Exception:
                pass
            self._json(200, body)
            return
        if path in ("/api/status", "/status"):
            self._json(200, {
                "ok": True,
                "service": "cornerai-bridge",
                "version": BRIDGE_VERSION,
                "require_token": _REQUIRE_BRIDGE_TOKEN,
                "endpoints": {
                    "feed": "/api/cornerai/feed",
                    "latest": "/api/cornerai/latest",
                    "health": "/health",
                    "metrics": "/metrics",
                },
            })
            return
        if path in ("/api/cornerai/latest", "/latest"):
            with _lock:
                exists = LATEST_FILE.exists()
                if exists:
                    try:
                        body = json.loads(LATEST_FILE.read_text(encoding="utf-8"))
                    except Exception as e:
                        self._json(500, {"ok": False, "error": str(e)})
                        return
            if exists:
                self._json(200, {"ok": True, "latest": body})
            else:
                self._json(404, {"ok": False, "error": "sem payload ainda"})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def _do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        # V23 BLOCO 4: rate limit no feed
        if path in ("/api/cornerai/feed", "/feed"):
            try:
                client_ip = self.client_address[0] if self.client_address else "unknown"
            except Exception:
                client_ip = "unknown"
            if not feed_limiter.is_allowed(client_ip):
                self._json(429, {"ok": False, "error": "rate_limit_exceeded"})
                return
        if _REQUIRE_BRIDGE_TOKEN and not _BRIDGE_TOKEN:
            self._json(503, {"ok": False, "error": "bridge_token_not_configured"})
            return
        if not self._auth_ok():
            self._json(401, {"ok": False, "error": "bridge_auth_required"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 8 * 1024 * 1024:
            self._json(413, {"ok": False, "error": "payload too large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        schema_h = self.headers.get("X-CornerAI-Schema") or ""
        version_h = self.headers.get("X-CornerAI-Version") or ""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON deve ser objeto")
        except Exception as e:
            print(f"[error] JSON inválido path={path} schema={schema_h} err={e}", flush=True)
            self._json(400, {"ok": False, "error": f"JSON inválido: {e}"})
            return

        # Skill JSON manual — sempre sobrescreve skill_feed_latest.json
        if path in ("/api/cornerai/skill-feed", "/skill-feed"):
            try:
                result = persist_skill_pack(payload)
                print(f"[skill-feed] ok schema={schema_h or payload.get('schema')} ver={version_h}", flush=True)
                self._json(200, result)
            except Exception as e:
                print(f"[error] skill-feed {e}", flush=True)
                self._json(500, {"ok": False, "error": str(e)})
            return

        if path not in ("/api/cornerai/feed", "/feed"):
            print(f"[error] POST 404 path={path}", flush=True)
            self._json(404, {"ok": False, "error": "not found", "path": path})
            return

        try:
            # --- NOVIDADE V23: Identifica a fonte da captura ---
            capture_source = payload.get("source", "EXTENSAO_CHROME_LEGADO")

            result = persist_feed(payload)
            if result.get("skipped") == "empty":
                # silencioso — evita flood None x None no terminal
                self._json(200, result)
                return

            v = result.get("view") or {}
            tag = result.get("reg") or "no-reg"

            # Log agora mostra se é WEBVIEW2 nativo ou Chrome legado
            print(
                f"[feed] {tag} · {v.get('home')} x {v.get('away')} · "
                f"{v.get('minute')}' · placar={v.get('score')} · "
                f"corners={v.get('corners')} · AP={v.get('dangerous')} · xG={v.get('xg')}"
                f" · schema={schema_h or payload.get('schema') or '-'} · ver={version_h or '-'}"
                f" · SRC=[{capture_source}]",
                flush=True,
            )
            self._json(200, {**result, "bridge": "ok", "version": BRIDGE_VERSION})
        except Exception as e:
            print(f"[error] feed persist {e}", flush=True)
            self._json(500, {"ok": False, "error": str(e)})

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._do_GET()
        except Exception as exc:
            print(f"[error] GET {self.path}: {exc}", flush=True)
            try:
                self._json(500, {"ok": False, "error": "internal_error", "detail": str(exc)})
            except Exception:
                self.close_connection = True

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._do_POST()
        except Exception as exc:
            print(f"[error] POST {self.path}: {exc}", flush=True)
            try:
                self._json(500, {"ok": False, "error": "internal_error", "detail": str(exc)})
            except Exception:
                self.close_connection = True

    def log_message(self, fmt: str, *args: Any) -> None:
        # Log POST + errors; keep GET /health quiet unless failure
        try:
            line = fmt % args if args else fmt
        except Exception:
            line = str(fmt)
        is_post = "POST" in line
        is_err = any(x in line for x in (" 4", " 5", "code 4", "code 5"))
        is_health = "/health" in line or line.strip().endswith("GET / ")
        if is_post or is_err or not is_health:
            super().log_message(fmt, *args)


def main() -> None:
    global DATA_DIR, FEED_FILE, LATEST_FILE, LOG_FILE, REGS_DIR, SKILL_JSON, SKILL_MD, SKILL_HISTORY
    ap = argparse.ArgumentParser(description="CornerAI live feed bridge")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default=None, help="pasta de dados (default: pasta do script)")
    args = ap.parse_args()

    DATA_DIR = Path(args.dir).resolve() if args.dir else Path(__file__).resolve().parent
    FEED_FILE = DATA_DIR / "live_feed.jsonl"
    LATEST_FILE = DATA_DIR / "live_latest.json"
    LOG_FILE = DATA_DIR / "CornerAI_Log_Analises_Entradas.md"
    REGS_DIR = DATA_DIR / "regs"
    SKILL_JSON = DATA_DIR / "skill_feed_latest.json"
    SKILL_MD = DATA_DIR / "skill_feed_for_chat.md"
    SKILL_HISTORY = DATA_DIR / "skill_feed_history.jsonl"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REGS_DIR.mkdir(parents=True, exist_ok=True)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"\n========================================\n"
        f" CornerAI Bridge v{BRIDGE_VERSION}\n"
        f"========================================\n"
        f" Feed    : http://{args.host}:{args.port}/api/cornerai/feed\n"
        f" Health  : http://{args.host}:{args.port}/health\n"
        f" Skill   : http://{args.host}:{args.port}/skill\n"
        f"\n"
        f" JSONL   : {FEED_FILE}\n"
        f" Latest  : {LATEST_FILE}\n"
        f" Log     : {LOG_FILE}\n"
        f" REGs    : {REGS_DIR}\n"
        f" SkillJSON: {SKILL_JSON}\n"
        f" SkillMD  : {SKILL_MD}\n"
        f"\n"
        f" Extensao deve apontar webhook para:\n"
        f"   http://{args.host}:{args.port}/api/cornerai/feed\n"
        f" Se o outbox mostrar BRIDGE_OFFLINE, este processo nao esta rodando.\n"
        f"========================================\n",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    main()


# Compatibilidade de testes quando `bridge/` aparece antes de `engine/` no
# sys.path. O Bridge continua com seu próprio app; o contrato é resolvido
# somente sob demanda para o módulo canônico do Engine.
def _apply_risk_contract(analysis, payload=None):
    try:
        from engine.server import _apply_risk_contract as canonical_apply_risk_contract
    except ImportError:
        from server import _apply_risk_contract as canonical_apply_risk_contract
    return canonical_apply_risk_contract(analysis, payload)


# --- Observability bridge :9101 ---
try:
    from engine.core.observability import REG, MetricsServer, default_alerts
    _BRIDGE_METRICS = MetricsServer(REG, host="127.0.0.1", port=9101)
    try:
        _BRIDGE_METRICS.register_component("feed_bus", BUS.stats)  # type: ignore[name-defined]
    except Exception:
        pass
    for _r in default_alerts(REG):
        _BRIDGE_METRICS.add_alert(_r)
    _BRIDGE_METRICS.start()
except Exception as _obs_err:
    import logging as _log
    _log.getLogger("bridge").warning("metrics bridge skip: %s", _obs_err)
