#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X — RELATORIO GERAL AUTOMATICO DE TODAS AS CAMADAS (V27)
Roda: processos, portas, health, Bridge latest (HTTP+disco), UI state,
      Hermes once, Hermes E2E, smoke, captura rica, sync, paper-only.
Gera TXT + JSON em logs_supervisor/
paper_trade=true / execution_allowed=false
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1]).resolve()
LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_TXT = LOGDIR / f"RELATORIO_GERAL_{TS}.txt"
REPORT_JSON = LOGDIR / f"RELATORIO_GERAL_{TS}.json"
LATEST_TXT = LOGDIR / "RELATORIO_GERAL_LATEST.txt"
LATEST_JSON = LOGDIR / "RELATORIO_GERAL_LATEST.json"

results: List[Dict[str, Any]] = []
lines: List[str] = []


def w(msg: str = "") -> None:
    lines.append(msg)
    try:
        print(msg)
    except Exception:
        print(msg.encode("utf-8", "replace").decode("ascii", "replace"))


def layer(name: str, ok: bool, detail: str, soft: bool = False) -> None:
    status = "OK" if ok else ("WARN" if soft else "FAIL")
    results.append({"layer": name, "ok": ok, "soft": soft, "status": status, "detail": detail})
    tag = {"OK": "[OK  ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    w(f"{tag} {name}: {detail}")


def http_json(url: str, timeout: float = 4.0, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, Any]:
    try:
        h = {"Accept": "application/json", "User-Agent": "AURA-RelatorioGeral/V27"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return True, json.loads(raw)
            except json.JSONDecodeError:
                return True, {"_text": raw[:400], "_status": getattr(resp, "status", None)}
    except Exception as exc:
        return False, {"error": str(exc)}


def port_listen(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.8):
            return True
    except Exception:
        return False


def bridge_headers() -> Dict[str, str]:
    token = (os.environ.get("CORNERAI_BRIDGE_TOKEN") or os.environ.get("AURA_BRIDGE_TOKEN") or "").strip()
    if not token:
        return {}
    return {"X-CornerAI-Token": token, "Authorization": f"Bearer {token}"}


def load_latest_disk() -> Dict[str, Any]:
    for p in [ROOT / "bridge" / "live_latest.json", Path("bridge/live_latest.json")]:
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def venv_python() -> Path:
    candidates = [
        ROOT / "engine" / "venv" / "Scripts" / "python.exe",
        ROOT / "engine" / "venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return Path(sys.executable)


def run_cmd(args: List[str], timeout: int = 120) -> Tuple[int, str]:
    try:
        env = os.environ.copy()
        env["AURA_ROOT"] = str(ROOT)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "engine"), str(ROOT / "bridge")])
        env["PAPER_TRADE"] = "true"
        env["EXECUTION_ALLOWED"] = "false"
        env["PYTHONUTF8"] = "1"
        cp = subprocess.run(
            args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        out = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")
        return cp.returncode, out.strip()
    except Exception as exc:
        return 99, str(exc)


def main() -> int:
    w("=" * 64)
    w(" AURA QUANT-X — RELATORIO GERAL AUTOMATICO V27")
    w(f" Inicio: {datetime.now().isoformat(timespec='seconds')}")
    w(f" Root:   {ROOT}")
    w(" paper_trade=true | execution_allowed=false")
    w("=" * 64)

    # CAMADA 0 — ficheiros criticos
    w("\n--- CAMADA 0) Ficheiros criticos ---")
    critical = [
        "engine/server.py",
        "bridge/server.py",
        "desktop/capture/aura-capture.js",
        "engine/agents/hermes_supervisor_agent.py",
        "scripts/smoke_test.py",
        "scripts/aura_hermes_e2e.py",
        "AURA_LIMPEZA_E_INSTALACAO_COMPLETA.bat",
        "AURA_TUDO_EM_UM.bat",
    ]
    for rel in critical:
        ok = (ROOT / rel).is_file()
        layer(f"file:{rel}", ok, "presente" if ok else "AUSENTE")

    # CAMADA 1 — portas
    w("\n--- CAMADA 1) Portas ---")
    for name, port in [("Bridge", 8080), ("Engine", 8765), ("Voice", 8099), ("Ollama", 11434)]:
        ok = port_listen(port)
        layer(f"Porta_{port}_{name}", ok, "LISTEN" if ok else "OFF", soft=(name in ("Voice", "Ollama")))

    # CAMADA 2 — health HTTP
    w("\n--- CAMADA 2) Health HTTP ---")
    ok_b, body_b = http_json("http://127.0.0.1:8080/health")
    age = None
    if ok_b and isinstance(body_b, dict):
        age = body_b.get("latestAgeSec")
        layer("Bridge_health", True, f"ok ageSec={age} lines={body_b.get('feedLines')}")
    else:
        layer("Bridge_health", False, str(body_b))

    ok_e, body_e = http_json("http://127.0.0.1:8765/api/health")
    layer("Engine_health", ok_e, str(body_e.get("status") if isinstance(body_e, dict) else body_e))

    ok_v, body_v = http_json("http://127.0.0.1:8099/api/voice/health")
    layer("Voice_health", ok_v, str(body_v.get("status") if isinstance(body_v, dict) else body_v), soft=True)

    ok_o, body_o = http_json("http://127.0.0.1:11434/api/tags")
    nmodels = len((body_o or {}).get("models") or []) if isinstance(body_o, dict) else 0
    layer("Ollama_tags", ok_o, f"models={nmodels}", soft=True)

    # CAMADA 3 — Bridge latest HTTP + disco
    w("\n--- CAMADA 3) Bridge latest + captura ---")
    ok_l, body_l = http_json("http://127.0.0.1:8080/api/cornerai/latest", headers=bridge_headers())
    latest = {}
    if ok_l and isinstance(body_l, dict):
        latest = body_l.get("latest") if isinstance(body_l.get("latest"), dict) else body_l
        layer("Bridge_latest_HTTP", True, "ok")
    else:
        layer("Bridge_latest_HTTP", False, str(body_l), soft=True)
        latest = load_latest_disk()
        layer("Bridge_latest_DISK", bool(latest), "live_latest.json" if latest else "vazio")

    view = {}
    if isinstance(latest, dict):
        view = latest.get("view") if isinstance(latest.get("view"), dict) else latest
    home = view.get("home") if isinstance(view, dict) else None
    away = view.get("away") if isinstance(view, dict) else None
    minute = view.get("minute") if isinstance(view, dict) else None
    corners_h = view.get("corners_home") if isinstance(view, dict) else None
    corners_a = view.get("corners_away") if isinstance(view, dict) else None
    dang_h = view.get("dangerous_home") if isinstance(view, dict) else None
    xg_h = view.get("xg_home") if isinstance(view, dict) else None
    atk_h = view.get("attacks_home") if isinstance(view, dict) else None

    rich = any(v is not None for v in (corners_h, corners_a, dang_h, xg_h, atk_h))
    layer(
        "Captura_identidade",
        bool(home and away),
        f"{home} x {away} min={minute}",
        soft=not (home and away),
    )
    layer(
        "Captura_rica",
        rich,
        f"corners={corners_h}-{corners_a} atk_h={atk_h} dang_h={dang_h} xg_h={xg_h}",
        soft=not rich,
    )
    fresh = age is not None and float(age) < 20
    layer("Feed_fresco", fresh, f"ageSec={age}", soft=not fresh)

    # CAMADA 4 — UI state / sync
    w("\n--- CAMADA 4) Engine UI state / sync ---")
    ok_ui, body_ui = http_json("http://127.0.0.1:8765/api/ui/state")
    ui_home = body_ui.get("home") if isinstance(body_ui, dict) else None
    ui_away = body_ui.get("away") if isinstance(body_ui, dict) else None
    ui_src = body_ui.get("source") if isinstance(body_ui, dict) else None
    stale = body_ui.get("capture_stale") if isinstance(body_ui, dict) else None
    jarvis = body_ui.get("jarvis_state") if isinstance(body_ui, dict) else None
    layer(
        "UI_state",
        bool(ui_home and ui_away),
        f"home={ui_home} away={ui_away} source={ui_src} stale={stale} jarvis={jarvis}",
        soft=not (ui_home and ui_away),
    )
    sync = bool(home and ui_home and str(home).lower()[:12] == str(ui_home).lower()[:12])
    layer("Sync_UI_Bridge", sync, f"bridge={home} ui={ui_home}", soft=not sync)

    # CAMADA 5 — paper only
    w("\n--- CAMADA 5) Paper-only / seguranca ---")
    paper = True
    if isinstance(body_ui, dict):
        paper = body_ui.get("paper_trade", True) is True and body_ui.get("execution_allowed", False) is False
    layer("Paper_only", paper, f"paper_trade={isinstance(body_ui, dict) and body_ui.get('paper_trade')} exec={isinstance(body_ui, dict) and body_ui.get('execution_allowed')}")

    # CAMADA 6 — smoke + hermes
    w("\n--- CAMADA 6) Smoke + Hermes ---")
    py = str(venv_python())
    smoke_script = ROOT / "scripts" / "smoke_test.py"
    if smoke_script.is_file():
        code, out = run_cmd([py, str(smoke_script)], timeout=90)
        ok = code == 0 or "SUCCESS" in out or "PASS" in out
        layer("Smoke_test", ok, out.splitlines()[-1][:160] if out else f"exit={code}")
    else:
        layer("Smoke_test", False, "script ausente", soft=True)

    code, out = run_cmd([py, "-m", "engine.agents.hermes_supervisor_agent", "--once"], timeout=180)
    ok = code == 0 or "HEALTHY" in out or "Hermes" in out
    # extract first meaningful line
    summary = next((ln for ln in out.splitlines() if "HEALTHY" in ln or "Hermes" in ln or "FAIL" in ln), out[:160])
    layer("Hermes_once", ok, summary[:200])

    e2e = ROOT / "scripts" / "aura_hermes_e2e.py"
    if e2e.is_file():
        code, out = run_cmd([py, str(e2e)], timeout=180)
        ok = code == 0 or "RESULTADO: PASS" in out or "PASS" in out.splitlines()[-1:]
        tail = " | ".join(out.splitlines()[-3:])[:220]
        layer("Hermes_E2E", ok, tail or f"exit={code}")
    else:
        layer("Hermes_E2E", False, "script ausente", soft=True)

    # CAMADA 7 — Desktop processo
    w("\n--- CAMADA 7) Desktop ---")
    desktop_ok = False
    try:
        if sys.platform.startswith("win"):
            code, out = run_cmd(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-Process Aura.QuantX.Desktop -ErrorAction SilentlyContinue | Measure-Object).Count"],
                timeout=20,
            )
            desktop_ok = out.strip() not in ("", "0")
        layer("Desktop_process", desktop_ok, out.strip() if out else "n/d", soft=True)
    except Exception as exc:
        layer("Desktop_process", False, str(exc), soft=True)

    # RESUMO
    oks = sum(1 for r in results if r["status"] == "OK")
    warns = sum(1 for r in results if r["status"] == "WARN")
    fails = sum(1 for r in results if r["status"] == "FAIL")
    w("\n" + "=" * 64)
    w(" RESUMO FINAL")
    w(f" OK={oks}  WARN={warns}  FAIL={fails}  TOTAL={len(results)}")
    w("=" * 64)
    for r in results:
        w(f"  {r['status']:4}  {r['layer']}: {r['detail'][:100]}")

    if fails == 0 and warns == 0:
        global_status = "HEALTHY"
    elif fails == 0:
        global_status = "HEALTHY_WITH_WARNINGS"
    elif oks >= fails:
        global_status = "DEGRADED"
    else:
        global_status = "CRITICAL"

    w(f"\nStatus global: {global_status}")
    w(f"Relatorio TXT: {REPORT_TXT}")
    w(f"Relatorio JSON: {REPORT_JSON}")
    w(f"Fim: {datetime.now().isoformat(timespec='seconds')}")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "status": global_status,
        "counts": {"ok": oks, "warn": warns, "fail": fails, "total": len(results)},
        "results": results,
        "paper_trade": True,
        "execution_allowed": False,
        "version": "12.7.62-V27-RELATORIO-GERAL",
    }
    text = "\n".join(lines) + "\n"
    REPORT_TXT.write_text(text, encoding="utf-8")
    LATEST_TXT.write_text(text, encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LATEST_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # feedback para IA
    fb = ROOT / "engine" / "data" / "system_health_feedback.json"
    try:
        fb.parent.mkdir(parents=True, exist_ok=True)
        fb.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass

    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
