# -*- coding: utf-8 -*-
"""
system_health_reader — AURA IA le o feedback do monitor E2E + Hermes Supervisor.

Uso pela IA / Hermes / chat:
  from engine.agents.system_health_reader import get_system_health, format_health_for_chat
  h = get_system_health()
  print(format_health_for_chat(h))

Arquivos consumidos:
  engine/data/system_health_feedback.json
  engine/data/hermes_supervisor_report.json  (V26.5+)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_PATH = ROOT / "engine" / "data" / "system_health_feedback.json"
HERMES_REPORT_PATH = ROOT / "engine" / "data" / "hermes_supervisor_report.json"
STALE_SEC = 120  # se arquivo mais velho que isso, status = STALE


def get_system_health(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or FEEDBACK_PATH
    if not p.exists():
        # fallback: tenta relatório do Hermes Supervisor
        if HERMES_REPORT_PATH.exists():
            try:
                hr = json.loads(HERMES_REPORT_PATH.read_text(encoding="utf-8"))
                return {
                    "status": hr.get("status", "UNKNOWN"),
                    "message_for_ia": hr.get("message_for_operator")
                    or "Feedback Hermes Supervisor carregado.",
                    "errors": [
                        f.get("message")
                        for f in (hr.get("findings") or [])
                        if f.get("severity") in ("CRITICAL", "HIGH")
                    ],
                    "ok": [
                        f.get("message")
                        for f in (hr.get("findings") or [])
                        if f.get("severity") == "INFO"
                    ],
                    "timestamp": hr.get("timestamp"),
                    "age_sec": None,
                    "source": "hermes_supervisor_report",
                    "recommendations": hr.get("recommendations") or [],
                }
            except Exception:
                pass
        return {
            "status": "UNKNOWN",
            "message_for_ia": (
                "Nenhum feedback de saude encontrado. "
                "Rode RODAR_TESTE_AUTOMATICO.bat, RODAR_MONITOR_CONTINUO_IA.bat "
                "ou HERMES_SUPERVISOR_ONCE.bat."
            ),
            "errors": ["system_health_feedback.json ausente"],
            "ok": [],
            "timestamp": None,
            "age_sec": None,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "status": "UNKNOWN",
            "message_for_ia": f"Falha ao ler feedback: {e}",
            "errors": [str(e)],
            "ok": [],
            "timestamp": None,
            "age_sec": None,
        }

    age = None
    ts = data.get("timestamp")
    if ts:
        try:
            from datetime import datetime

            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            age = max(0.0, time.time() - t.timestamp())
        except Exception:
            age = None

    if age is not None and age > STALE_SEC:
        data["status"] = "STALE"
        data["message_for_ia"] = (
            f"Feedback antigo ({int(age)}s). Rode o monitor continuo ou HERMES_SUPERVISOR_LOOP.bat. "
            + str(data.get("message_for_ia", ""))
        )

    data["age_sec"] = age
    data["feedback_path"] = str(p)

    # anexa resumo Hermes se existir e for mais recente
    if HERMES_REPORT_PATH.exists():
        try:
            hr = json.loads(HERMES_REPORT_PATH.read_text(encoding="utf-8"))
            data["hermes_supervisor_status"] = hr.get("status")
            data["hermes_message"] = hr.get("message_for_operator")
        except Exception:
            pass

    return data


def format_health_for_chat(health: Optional[Dict[str, Any]] = None) -> str:
    h = health or get_system_health()
    status = h.get("status", "UNKNOWN")
    lines = [
        f"[SYSTEM HEALTH] status={status}",
        f"timestamp={h.get('timestamp')} age_sec={h.get('age_sec')}",
    ]
    if h.get("hermes_supervisor_status"):
        lines.append(f"hermes_supervisor={h.get('hermes_supervisor_status')}")
    if h.get("hermes_message"):
        lines.append(str(h["hermes_message"]))
    ok = h.get("ok") or []
    if ok:
        lines.append("OK: " + ", ".join(str(x) for x in ok))
    errs = h.get("errors") or []
    if errs:
        lines.append("ERROS: " + "; ".join(str(x) for x in errs))
    metrics = h.get("metrics") or {}
    if metrics:
        parts = []
        for k in (
            "feed_age_sec",
            "feed_fresh",
            "sync",
            "rich_stats",
            "bridge_game",
            "ui_game",
            "feed_fresh_pct",
            "sync_pct",
            "rich_pct",
            "last_bridge",
            "last_ui",
        ):
            if k in metrics and metrics[k] is not None:
                parts.append(f"{k}={metrics[k]}")
        if parts:
            lines.append("metrics: " + " | ".join(parts))
    msg = h.get("message_for_ia")
    if msg:
        lines.append(str(msg))
    recs = h.get("recommendations") or []
    if recs:
        lines.append("RECOMENDACOES: " + " | ".join(str(x) for x in recs[:5]))
    return "\n".join(lines)


def is_healthy(max_age_sec: float = STALE_SEC) -> bool:
    h = get_system_health()
    if h.get("status") not in ("HEALTHY",):
        return False
    age = h.get("age_sec")
    if age is not None and age > max_age_sec:
        return False
    return True


if __name__ == "__main__":
    print(format_health_for_chat())
