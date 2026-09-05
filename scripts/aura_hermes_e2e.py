#!/usr/bin/env python3
"""Hermes E2E — auditoria de arquivos, imports, HTTP e comunicação.

Não inicia Telegram, userbot, ordens, webcam nem scrape.
paper_trade=true / execution_allowed=false
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
REPORT = ROOT / "engine" / "data" / "hermes_e2e_report.json"


def _get(url: str, timeout: float = 3.0) -> tuple[bool, Any]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return True, json.loads(raw)
            except json.JSONDecodeError:
                return True, {"text": raw[:300], "status": resp.status}
    except Exception as exc:
        return False, {"error": str(exc)}


def _post(url: str, payload: dict[str, Any], timeout: float = 4.0) -> tuple[bool, Any]:
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return True, json.loads(body)
            except json.JSONDecodeError:
                return True, {"text": body[:300]}
    except Exception as exc:
        return False, {"error": str(exc)}


def _port(port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def check_files() -> list[dict[str, Any]]:
    required = [
        "engine/server.py",
        "engine/knowledge_review_gate.py",
        "engine/war_council_api.py",
        "engine/agents/war_council.py",
        "engine/agents/aura_hermes_router.py",
        "engine/agents/hermes_supervisor_agent.py",
        "engine/agents_glm/red_team_adversary.py",
        "engine/agents_glm/post_match_forensics.py",
        "engine/agents_glm/elo_rating_agent.py",
        "engine/agents_glm/crew_council.py",
        "bridge/server.py",
        "requirements.txt",
        "agents/activation_manifest.json",
        "desktop/ui/matriz_v22/index.html",
        "knowledge/inbox/knowledge_candidates.jsonl",
        "knowledge/approved/knowledge.jsonl",
        "knowledge/review_decisions.jsonl",
    ]
    out = []
    for rel in required:
        path = ROOT / rel
        out.append({"name": f"file:{rel}", "ok": path.is_file(), "detail": "presente" if path.is_file() else "AUSENTE"})
    return out


def check_imports() -> list[dict[str, Any]]:
    sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "bridge")]
    specs = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("httpx", "httpx"),
        ("requests", "requests"),
        ("knowledge_review_gate", "knowledge_review_gate"),
        ("war_council", "engine.agents.war_council"),
        ("hermes_router", "engine.agents.aura_hermes_router"),
        ("red_team", "engine.agents_glm.red_team_adversary"),
        ("forensics", "engine.agents_glm.post_match_forensics"),
        ("elo", "engine.agents_glm.elo_rating_agent"),
        ("crew", "engine.agents_glm.crew_council"),
        ("hermes_supervisor", "engine.agents.hermes_supervisor_agent"),
    ]
    out = []
    for name, mod in specs:
        try:
            __import__(mod)
            out.append({"name": f"import:{name}", "ok": True, "detail": mod})
        except Exception as exc:
            out.append({"name": f"import:{name}", "ok": False, "detail": str(exc)})
    return out


def check_local_council() -> list[dict[str, Any]]:
    out = []
    try:
        from engine.agents.war_council import convene
        from engine.agents.aura_hermes_router import is_primary_pipeline

        veto = convene(
            {"minute": 88, "score": "0-0", "attack_pressure_diff": 10, "shots_off_target": 9, "corners": 2},
            {"decision": "ENTRA", "odd": 9.0, "score": 70},
        )
        ok = veto.get("verdict") == "VETOED" and veto.get("execution_allowed") is False
        out.append({"name": "council:red_team_veto", "ok": ok, "detail": str(veto.get("verdict"))})
        out.append({"name": "hermes:primary_pipeline", "ok": bool(is_primary_pipeline()), "detail": "primary"})
    except Exception as exc:
        out.append({"name": "council:red_team_veto", "ok": False, "detail": str(exc)})
    return out


def check_http() -> list[dict[str, Any]]:
    checks = []
    core = [
        ("bridge:/health", "http://127.0.0.1:8080/health", True),
        ("engine:/api/health", "http://127.0.0.1:8765/api/health", True),
        ("engine:/api/knowledge/status", "http://127.0.0.1:8765/api/knowledge/status", True),
        ("engine:/api/council/status", "http://127.0.0.1:8765/api/council/status", True),
        ("engine:/api/ui/state", "http://127.0.0.1:8765/api/ui/state", True),
        ("engine:/api/agents", "http://127.0.0.1:8765/api/agents", True),
        ("engine:/api/activation", "http://127.0.0.1:8765/api/activation", True),
        ("engine:/api/agents/glm/status", "http://127.0.0.1:8765/api/agents/glm/status", False),
        ("voice:/api/voice/health", "http://127.0.0.1:8099/api/voice/health", False),
        ("ollama:/api/tags", "http://127.0.0.1:11434/api/tags", False),
    ]
    for name, url, required in core:
        ok, payload = _get(url)
        detail = payload if isinstance(payload, dict) else {"raw": payload}
        if name.endswith("/status") and ok and isinstance(payload, dict):
            if payload.get("execution_allowed") is True:
                ok = False
                detail["error"] = "execution_allowed=true bloqueado no E2E"
        checks.append(
            {
                "name": f"http:{name}",
                "ok": ok if required else True,
                "warning": (not ok) and (not required),
                "detail": json.dumps(detail, ensure_ascii=False)[:240],
            }
        )

    ok, payload = _post(
        "http://127.0.0.1:8765/api/council/convene",
        {
            "features": {"minute": 88, "score": "0-0", "attack_pressure_diff": 12},
            "decision": {"decision": "ENTRA", "odd": 9.0, "score": 70},
        },
    )
    veto_ok = ok and isinstance(payload, dict) and payload.get("verdict") == "VETOED"
    checks.append({"name": "http:council_convene_veto", "ok": veto_ok or (not _port(8765) and False) or veto_ok, "detail": json.dumps(payload, ensure_ascii=False)[:240] if isinstance(payload, dict) else str(payload)[:240]})

    ok_elo, elo = _get("http://127.0.0.1:8765/api/council/elo?home=Casa&away=Fora&odd=2.4")
    checks.append({"name": "http:elo", "ok": ok_elo and isinstance(elo, dict) and elo.get("execution_allowed") is False, "detail": json.dumps(elo, ensure_ascii=False)[:240] if isinstance(elo, dict) else str(elo)[:240]})
    return checks


def check_ports() -> list[dict[str, Any]]:
    live = os.environ.get("AURA_E2E_LIVE", "0").strip() in {"1", "true", "True"}
    mapping = {8080: "bridge", 8765: "engine", 8099: "voice", 11434: "ollama"}
    out = []
    for port, name in mapping.items():
        listening = _port(port)
        required = live and port in {8080, 8765}
        out.append(
            {
                "name": f"port:{port}:{name}",
                "ok": listening if required else True,
                "warning": not listening,
                "detail": "LISTEN" if listening else ("fechada (ok no preflight)" if not live else "fechada"),
            }
        )
    return out


def check_sokker_feed(http_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ui_ok, ui = _get("http://127.0.0.1:8765/api/ui/state")
    home = away = source = None
    if ui_ok and isinstance(ui, dict):
        view = (ui.get("snapshot") or {}).get("view") or {}
        home = view.get("home")
        away = view.get("away")
        source = ui.get("source")
    live = bool(home and away)
    return [
        {
            "name": "comms:sokkerpro_pane",
            "ok": True,
            "warning": not live,
            "detail": f"source={source} home={home} away={away}" + ("" if live else " — abra SokkerPRO na pane direita"),
        }
    ]


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    checks.extend(check_files())
    checks.extend(check_imports())
    checks.extend(check_local_council())
    checks.extend(check_ports())
    if _port(8080) or _port(8765):
        checks.extend(check_http())
        checks.extend(check_sokker_feed(checks))
    else:
        checks.append({"name": "http:skipped", "ok": True, "warning": True, "detail": "Bridge/Engine ainda nao escutam — rode o BAT completo"})

    required_fail = [c for c in checks if not c.get("ok") and not c.get("warning")]
    warnings = [c for c in checks if c.get("warning")]
    report = {
        "ok": not required_fail,
        "paper_trade": True,
        "execution_allowed": False,
        "root": str(ROOT),
        "failed": [c["name"] for c in required_fail],
        "warnings": [c["name"] for c in warnings],
        "checks": checks,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== HERMES E2E ===")
    for item in checks:
        flag = "OK" if item.get("ok") and not item.get("warning") else ("AVISO" if item.get("warning") else "FALHA")
        print(f"[{flag}] {item['name']}: {item.get('detail','')[:160]}")
    print(f"RELATORIO: {REPORT}")
    print("RESULTADO:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
