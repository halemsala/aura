#!/usr/bin/env python3
"""Relatorio consolidado: camadas altas/baixas, Matriz, captura, Hermes, operador."""
from __future__ import annotations
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "engine" / "data"
DATA.mkdir(parents=True, exist_ok=True)
OUT = DATA / "post_start_report.json"

ENDPOINTS = {
    "bridge_health": "http://127.0.0.1:8080/health",
    "engine_health": "http://127.0.0.1:8765/api/health",
    "engine_ui_state": "http://127.0.0.1:8765/api/ui/state",
    "engine_status": "http://127.0.0.1:8765/api/status",
    "engine_agents": "http://127.0.0.1:8765/api/agents",
    "voice_health": "http://127.0.0.1:8099/api/voice/health",
    "ollama_tags": "http://127.0.0.1:11434/api/tags",
}

def probe(url: str, timeout: float = 4.0):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AuraMatrizReport/12.7.7"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode(errors="replace")
            try:
                return True, json.loads(body)
            except Exception:
                return True, {"raw": body[:400]}
    except Exception as e:
        return False, {"error": str(e)[:200]}

def load_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}

def classify_matriz(ui):
    if not isinstance(ui, dict):
        return "UI_UNAVAILABLE", "api/ui/state nao respondeu"
    view = (ui.get("snapshot") or {}).get("view") or {}
    home = view.get("home") or ui.get("home")
    away = view.get("away") or ui.get("away")
    source = ui.get("source") or view.get("source")
    minute = view.get("minute") or ui.get("minute")
    if home or away:
        return "MATRIX_LIVE", f"{home} x {away} min={minute} source={source}"
    return "NO_CAPTURE_OR_SIM", f"sem fixture live — source={source}"

def main() -> int:
    results = {}
    for name, url in ENDPOINTS.items():
        ok, data = probe(url)
        results[name] = {"ok": ok, "data": data}

    ui = results.get("engine_ui_state", {}).get("data")
    matriz_code, matriz_reason = classify_matriz(ui if isinstance(ui, dict) else {})

    hermes = load_json(DATA / "hermes_supervisor_report.json")
    feedback = load_json(DATA / "system_health_feedback.json")

    layers = {
        "baixa_rede_portas": {
            "bridge_8080": results["bridge_health"]["ok"],
            "engine_8765": results["engine_health"]["ok"],
            "voice_8099": results["voice_health"]["ok"],
            "ollama_11434": results["ollama_tags"]["ok"],
        },
        "media_apis": {
            "ui_state": results["engine_ui_state"]["ok"],
            "status": results["engine_status"]["ok"],
            "agents": results["engine_agents"]["ok"],
        },
        "alta_matriz_captura": {
            "matriz_code": matriz_code,
            "matriz_reason": matriz_reason,
            "hermes_report_present": hermes is not None,
            "feedback_present": feedback is not None,
        },
    }

    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "priority": "MATRIZ",
        "layers": layers,
        "endpoints": {k: {"ok": v["ok"]} for k, v in results.items()},
        "ui_state_summary": {
            "ok": results["engine_ui_state"]["ok"],
            "matriz": matriz_code,
            "reason": matriz_reason,
        },
        "hermes_supervisor_report": hermes,
        "system_health_feedback": feedback,
        "invariants": {
            "paper_trade": True,
            "execution_allowed": False,
            "AURA_UNLOCK_LIVE": 0,
        },
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "written": str(OUT),
        "matriz": matriz_code,
        "bridge": results["bridge_health"]["ok"],
        "engine": results["engine_health"]["ok"],
        "hermes": hermes is not None,
    }, ensure_ascii=False, indent=2))
    if results["bridge_health"]["ok"] and results["engine_health"]["ok"]:
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
