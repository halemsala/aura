# -*- coding: utf-8 -*-
"""AURA — reparo painel paper-only: testa, sobe servicos, gera relatorio."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1]).resolve()
LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)
REPORT = LOGDIR / "RELATORIO_REPARO_PAINEL_LATEST.md"
REPORT_JSON = LOGDIR / "RELATORIO_REPARO_PAINEL_LATEST.json"

SERVICES = [
    ("bridge", 8080, "/health", "bridge/server.py", ["--host", "127.0.0.1", "--port", "8080"]),
    ("engine", 8765, "/api/health", "engine/server.py", ["--host", "127.0.0.1", "--port", "8765"]),
    ("matriz", 8766, "/health", "scripts/aura_serve_matriz.py", []),
    ("hermes", 8777, "/health", "hermes_v10/AURA_RUN_HERMES.py", []),
    ("control", 8790, "/health", "scripts/aura_tools_control_api.py", []),
    ("voice", 8099, "/api/voice/health", "bridge/jarvis_voice_server.py",
     ["--host", "127.0.0.1", "--port", "8099", "--lazy"]),
]


def log(msg: str, lines: list) -> None:
    print(msg, flush=True)
    lines.append(msg)


def port_listen(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def http_get(url: str, timeout: float = 3.0):
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            body = r.read()[:500].decode("utf-8", "replace")
        return True, body
    except Exception as e:
        return False, str(e)


def ensure_venv(lines: list):
    vpy = ROOT / "engine" / "venv" / "Scripts" / "python.exe"
    if vpy.is_file():
        log("[OK] venv: %s" % vpy, lines)
        return vpy
    log("[FIX] venv ausente — criar py -3.11", lines)
    (ROOT / "engine").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.run(
            ["py", "-3.11", "-m", "venv", str(ROOT / "engine" / "venv")],
            check=True, env=env, cwd=str(ROOT),
        )
    except Exception as e:
        log("[ERRO] venv: %s" % e, lines)
        return None
    if not vpy.is_file():
        return None
    subprocess.run(
        [str(vpy), "-m", "pip", "install", "-U", "pip", "fastapi",
         "uvicorn[standard]", "pydantic", "httpx", "psutil"],
        check=False, env=env, cwd=str(ROOT),
    )
    log("[OK] venv criado", lines)
    return vpy


def ensure_matriz_ui(lines: list) -> bool:
    idx = ROOT / "desktop" / "ui" / "matriz_v22" / "index.html"
    hub = ROOT / "desktop" / "ui" / "matriz_v22" / "tools-hub.html"
    if idx.is_file() and hub.is_file():
        log("[OK] matriz UI index=%s" % idx.stat().st_size, lines)
        return True
    log("[FIX] matriz_v22 incompleta — procurar ZIP", lines)
    zips = []
    for base in [ROOT, Path.home() / "Downloads", Path.home() / "Desktop"]:
        if not base.exists():
            continue
        try:
            for p in base.rglob("*V37.3.54*.zip"):
                zips.append(p)
        except Exception:
            pass
    zips = sorted(set(zips), key=lambda p: p.stat().st_mtime, reverse=True)
    if not zips:
        log("[ERRO] ZIP nao encontrado", lines)
        return False
    zpath = zips[0]
    log("[ZIP] %s" % zpath, lines)
    try:
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if not name.startswith("desktop/ui/matriz_v22/") or name.endswith("/"):
                    continue
                target = ROOT / name.replace("/", os.sep)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, open(target, "wb") as out:
                    out.write(src.read())
        log("[OK] matriz extraida", lines)
    except Exception as e:
        log("[ERRO] extrair: %s" % e, lines)
        return False
    return idx.is_file()


def start_service(name, script_rel, args, vpy, lines) -> bool:
    script = ROOT / script_rel.replace("/", os.sep)
    if not script.is_file():
        log("[ERRO] %s falta %s" % (name, script), lines)
        return False
    env = os.environ.copy()
    env.update({
        "AURA_ROOT": str(ROOT),
        "PAPER_TRADE": "true",
        "EXECUTION_ALLOWED": "false",
        "AURA_EXECUTION_ALLOWED": "0",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.pathsep.join([
            str(ROOT), str(ROOT / "engine"), str(ROOT / "bridge"), str(ROOT / "hermes_v10"),
        ]),
    })
    if name == "hermes":
        cwd = str(ROOT / "hermes_v10")
        cmd = [str(vpy), "-u", "AURA_RUN_HERMES.py"]
    else:
        cwd = str(ROOT)
        cmd = [str(vpy), "-u", str(script)] + list(args)
    logf = LOGDIR / ("repair_%s.log" % name)
    try:
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        lf = open(logf, "a", encoding="utf-8")
        lf.write("\n==== %s start %s ====\n%s\n" % (datetime.now().isoformat(), name, " ".join(cmd)))
        lf.flush()
        subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags, stdout=lf, stderr=subprocess.STDOUT)
        log("[START] %s -> %s" % (name, logf.name), lines)
        return True
    except Exception as e:
        log("[ERRO] start %s: %s" % (name, e), lines)
        return False


def main() -> int:
    lines = []
    actions = []
    log("# RELATORIO REPARO PAINEL AURA", lines)
    log("ts: %s" % datetime.now(timezone.utc).isoformat(), lines)
    log("root: %s" % ROOT, lines)
    log("paper_trade=true execution_allowed=false", lines)
    log("", lines)

    os.environ["PYTHONUTF8"] = "1"
    vpy = ensure_venv(lines)
    if not vpy:
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        return 2
    ensure_matriz_ui(lines)

    log("", lines)
    log("## Servicos (antes)", lines)
    for name, port, path, script, args in SERVICES:
        ok, body = http_get("http://127.0.0.1:%s%s" % (port, path)) if port_listen(port) else (False, "down")
        log("- %s:%s %s" % (name, port, "UP" if ok else "DOWN"), lines)
        if not ok:
            if start_service(name, script, args, vpy, lines):
                actions.append({"start": name, "port": port})

    log("", lines)
    log("## Wait 15s", lines)
    time.sleep(15)

    final = {}
    core_ok = True
    log("## Depois", lines)
    for name, port, path, script, args in SERVICES:
        ok, body = http_get("http://127.0.0.1:%s%s" % (port, path))
        final[name] = {"port": port, "ok": ok, "sample": body[:160]}
        log("- %s:%s %s %s" % (name, port, "OK" if ok else "OFF", body[:80]), lines)
        if name in ("bridge", "engine", "control", "matriz") and not ok:
            core_ok = False

    log("", lines)
    log("## Acoes", lines)
    for a in actions:
        log("- %s" % a, lines)
    log("", lines)
    if core_ok:
        log("## RESULTADO: CORE OK — http://127.0.0.1:8766/tools-hub.html", lines)
    else:
        log("## RESULTADO: ainda OFF — ver logs_supervisor/repair_*.log", lines)

    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "paper_trade": True,
        "execution_allowed": False,
        "actions": actions,
        "final": final,
        "core_ok": core_ok,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n[REPORT]", REPORT)
    return 0 if core_ok else 1


if __name__ == "__main__":
    sys.exit(main())
