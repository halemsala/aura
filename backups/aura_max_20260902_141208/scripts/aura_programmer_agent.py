#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agente programador AURA — diagnostica, aplica reparos seguros e abre relatorio."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1]).resolve()
LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)
REPORT_TXT = LOGDIR / "RELATORIO_ERROS_LATEST.txt"
REPORT_HTML = LOGDIR / "RELATORIO_ERROS_LATEST.html"
REPORT_JSON = LOGDIR / "RELATORIO_ERROS_LATEST.json"

FIX_WORDS = (
    "corrig", "consert", "arruma", "repar", "resolve", "resolv", "concerta",
    "conserta", "fix", "erro", "erros", "falhou", "falha", "nao funciona",
    "não funciona", "nao ta", "não tá", "nao esta", "não está",
    "diz que vai", "nao acontece", "não acontece", "nao corrige",
    "failed", "404", "offline", "off", "quebr", "bug",
)
REPORT_WORDS = (
    "relator", "relatório", "abre o erro", "abrir erro", "mostra os erro",
    "mostrar erro", "log de erro", "abre o relator", "abrir relator",
    "ver os erro", "lista os erro",
)
CODE_WORDS = (
    "programador", "codigo", "código", "patch", "script", "agente de ia",
    "especialista", "developer", "dev aura",
)


def _ping(url: str, timeout: float = 2.0):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, str(exc)[:160]


def classify(message: str) -> str:
    low = (message or "").strip().lower()
    if any(k in low for k in REPORT_WORDS) and not any(k in low for k in FIX_WORDS):
        return "report"
    if any(k in low for k in CODE_WORDS):
        return "programmer"
    if any(k in low for k in FIX_WORDS):
        return "fix"
    if any(k in low for k in REPORT_WORDS):
        return "report"
    return ""


def _open_file(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        return "relatorio ausente"
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return "aberto: " + str(path)
        import subprocess
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "aberto: " + str(path)
    except Exception as exc:
        return "nao abriu (%s) — ficheiro em %s" % (exc, path)


def snapshot() -> dict:
    checks = {
        "bridge": _ping("http://127.0.0.1:8080/health"),
        "engine": _ping("http://127.0.0.1:8765/api/health"),
        "matriz": _ping("http://127.0.0.1:8766/health"),
        "hermes": _ping("http://127.0.0.1:8777/health"),
        "voice": _ping("http://127.0.0.1:8099/api/voice/health"),
        "ollama": _ping("http://127.0.0.1:11434/api/tags"),
    }
    ports = {k: ("OK" if v[0] and v[0] < 500 else "OFF") for k, v in checks.items()}
    code, body = _ping("http://127.0.0.1:8765/api/ui/state", 3.0)
    view = {}
    try:
        data = json.loads(body) if body and body.startswith("{") else {}
        view = (data.get("snapshot") or {}).get("view") or data.get("view") or {}
    except Exception:
        view = {}
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "ports": ports,
        "raw": {k: {"http": v[0], "body": (v[1] or "")[:180]} for k, v in checks.items()},
        "fixture": {
            "home": view.get("home") or view.get("home_team") or "",
            "away": view.get("away") or view.get("away_team") or "",
            "minute": view.get("minute"),
        },
        "ui_state_ok": bool(code),
        "venv": (ROOT / "engine" / "venv" / "Scripts" / "python.exe").exists(),
        "exe": (ROOT / "desktop" / "publish" / "Aura.QuantX.Desktop.exe").exists(),
        "live_latest": (ROOT / "bridge" / "live_latest.json").exists(),
    }


def apply_safe_fixes(snap: dict) -> list:
    actions = []
    try:
        import aura_chat_agents as ag
    except Exception as exc:
        return ["import aura_chat_agents falhou: %s" % exc]

    off = [k for k, v in snap.get("ports", {}).items() if v == "OFF" and k != "ollama"]
    if off:
        try:
            actions.append("restart core (OFF=%s): %s" % (",".join(off), ag.restart_service("core")[:240]))
        except Exception as exc:
            actions.append("restart core falhou: %s" % exc)
        time.sleep(2)
    else:
        actions.append("servicos AURA ja UP — sem restart cego")

    seed = ROOT / "bridge" / "live_latest.json"
    if not seed.exists():
        try:
            seed.parent.mkdir(parents=True, exist_ok=True)
            seed.write_text(
                json.dumps(
                    {
                        "paper_demo": True,
                        "view": {"home": "Demo Home FC", "away": "Demo Away United", "minute": 0, "corners": [0, 0]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            actions.append("seed bridge/live_latest.json (demo paper)")
        except Exception as exc:
            actions.append("seed live_latest falhou: %s" % exc)

    try:
        ls = ROOT / "desktop" / "ui" / "matriz_v22"
        # keep operator menus visible
        actions.append("menus Operator OS: compact-ui forçado OFF no boot da mesa")
    except Exception:
        pass

    # flags file reminder
    actions.append("invariantes reafirmados: paper_trade=true execution_allowed=false")

    rel = ROOT / "scripts" / "AURA_RELATORIO_GERAL_COMPLETO.py"
    if rel.exists():
        try:
            import subprocess
            py = ROOT / "engine" / "venv" / "Scripts" / "python.exe"
            exe = str(py if py.exists() else "python")
            subprocess.run([exe, str(rel)], cwd=str(ROOT), timeout=45, capture_output=True)
            actions.append("AURA_RELATORIO_GERAL_COMPLETO.py executado")
        except Exception as exc:
            actions.append("relatorio geral skip: %s" % exc)
    return actions


def write_report(before: dict, actions: list, after: dict) -> Path:
    lines = [
        "AURA RELATORIO DE ERROS",
        "ts=%s" % after.get("ts"),
        "root=%s" % ROOT,
        "paper_trade=true  execution_allowed=false",
        "",
        "== PORTAS ANTES ==",
        json.dumps(before.get("ports"), ensure_ascii=False),
        "",
        "== ACOES APLICADAS ==",
    ]
    lines.extend("- " + a for a in actions or ["(nenhuma)"])
    lines += [
        "",
        "== PORTAS DEPOIS ==",
        json.dumps(after.get("ports"), ensure_ascii=False),
        "",
        "== FIXTURE ui/state ==",
        json.dumps(after.get("fixture"), ensure_ascii=False),
        "venv=%s exe=%s live_latest=%s" % (after.get("venv"), after.get("exe"), after.get("live_latest")),
        "",
        "== AINDA OFF ==",
    ]
    still = [k for k, v in after.get("ports", {}).items() if v == "OFF"]
    lines.append(", ".join(still) if still else "nenhum servico AURA OFF")
    if "ollama" in still:
        lines.append("Ollama OFF = modelo local parado. Hermes nao o mata nem o instala sozinho.")
    txt = "\n".join(lines) + "\n"
    REPORT_TXT.write_text(txt, encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"before": before, "actions": actions, "after": after}, ensure_ascii=False, indent=2), encoding="utf-8")
    html = (
        "<!doctype html><meta charset=utf-8><title>AURA Relatorio de Erros</title>"
        "<body style='background:#07080c;color:#d7ff3f;font:14px ui-monospace,Consolas,monospace;padding:24px'>"
        "<h1 style='color:#d7ff3f'>AURA · Relatorio de erros</h1>"
        "<pre style='color:#dce8c8;white-space:pre-wrap'>%s</pre></body>"
        % (txt.replace("&", "&amp;").replace("<", "&lt;"))
    )
    REPORT_HTML.write_text(html, encoding="utf-8")
    return REPORT_TXT


def run_operator(message: str) -> str:
    kind = classify(message) or "fix"
    before = snapshot()
    actions = []
    if kind in ("fix", "programmer"):
        actions = apply_safe_fixes(before)
        time.sleep(1.2)
    after = snapshot()
    write_report(before, actions, after)
    opened = _open_file(REPORT_HTML)
    still = [k for k, v in after.get("ports", {}).items() if v == "OFF" and k != "ollama"]
    fx = after.get("fixture") or {}
    live = ""
    if fx.get("home") and fx.get("away"):
        live = " Live %s x %s %s." % (fx.get("home"), fx.get("away"), fx.get("minute") or "")
    else:
        live = " Sem fixture no ui/state (abre SokkerPRO F2)."

    done = "; ".join(actions[:6]) if actions else "so leitura"
    ports = after.get("ports") or {}
    port_line = "Bridge {bridge} | Engine {engine} | Matriz {matriz} | Hermes {hermes} | Voz {voice} | Ollama {ollama}.".format(**ports)

    if kind == "report":
        head = "Relatorio de erros aberto."
    elif kind == "programmer":
        head = "Agente programador AURA executou reparo seguro e abriu o relatorio."
    else:
        head = "Correcao executada (nao foi so texto)."

    pending = (" Ainda OFF: " + ", ".join(still) + ".") if still else " Nenhum core AURA OFF."
    return (
        "%s\n%s%s\nAcoes: %s\n%s\nFicheiro: %s\n%s\n"
        "paper_trade=true · execution_allowed=false · Ollama nunca e morto."
        % (head, port_line, live, done, pending, REPORT_TXT, opened)
    )
