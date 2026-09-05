#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Orchestrator V30 — Zero-Touch
Sobe Bridge, Engine, Voice, Matriz HTTP (anti-404), Domain Lock, Hermes Deep Diagnóstico
e Painel. Self-healing em portas, paths e falhas de serviço.
Nunca liga execution_allowed. paper_trade=true sempre.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import List, Optional, Tuple

VERSION = "V30-ZERO-TOUCH-1.0.0"
PAPER = "true"
EXEC = "false"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        logdir = ROOT / "logs_supervisor"
        logdir.mkdir(parents=True, exist_ok=True)
        with (logdir / "ORCHESTRATOR_V30.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port(port: int, seconds: int = 30, name: str = "") -> bool:
    for i in range(seconds):
        if port_open(port):
            log(f"OK  porta {port} ({name}) LISTEN")
            return True
        time.sleep(1)
    log(f"FAIL porta {port} ({name}) nao subiu em {seconds}s")
    return False


def kill_port_windows(port: int) -> None:
    try:
        ps = (
            f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
            f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=15,
        )
    except Exception as e:
        log(f"kill_port {port}: {e}")


def find_python(root: Path) -> str:
    candidates = [
        root / "engine" / "venv" / "Scripts" / "python.exe",
        root / "engine" / "venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable


def start_py(script: Path, args: List[str], title: str, env: dict) -> Optional[subprocess.Popen]:
    if not script.exists():
        log(f"SKIP {title}: {script} ausente")
        return None
    cmd = [PY, str(script)] + args
    log(f"START {title}: {' '.join(cmd[-4:])}")
    try:
        # CREATE_NEW_CONSOLE on Windows so process survives
        creation = 0
        if os.name == "nt":
            creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
        return subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation,
        )
    except Exception as e:
        log(f"ERRO ao subir {title}: {e}")
        return None


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def start_matriz_http(ui_dir: Path, port: int = 8766) -> Optional[ThreadingHTTPServer]:
    if not (ui_dir / "index.html").exists():
        log(f"ERRO Matriz: index.html nao encontrado em {ui_dir}")
        return None

    class Handler(QuietHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ui_dir), **k)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        log(f"Matriz porta {port} ocupada: {e} — tentando liberar")
        kill_port_windows(port)
        time.sleep(1)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as e2:
            log(f"Matriz FAIL: {e2}")
            return None

    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    log(f"OK  Matriz HTTP em http://127.0.0.1:{port}/index.html  dir={ui_dir}")
    return server


def find_matriz_dir(root: Path) -> Optional[Path]:
    candidates = [
        root / "desktop" / "ui" / "matriz_v22",
        root / "desktop" / "publish" / "ui" / "matriz_v22",
        root / "desktop" / "ui" / "matriz",
        root / "desktop" / "ui",
    ]
    for c in candidates:
        if (c / "index.html").exists():
            return c
    # last resort: any index.html under desktop
    for p in (root / "desktop").rglob("index.html"):
        return p.parent
    return None


def apply_domain_lock(root: Path) -> None:
    prompts = root / "engine" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    target = prompts / "system_hermes_football_only.txt"
    text = """# SYSTEM — AURA / HERMES (V30)
Dominio UNICO: futebol ao vivo, escanteios (corners), SokkerPRO, paper-trade.
PROIBIDO: acoes, bolsa, tickers, Vale, Itau, Gerdau, Embraer, dividendos.
Se fora de dominio responda: "Fora de dominio. Sistema trata apenas futebol/escanteios."
Invariantes: paper_trade=true · execution_allowed=false · GLM_ADVISORY_ONLY=true
"""
    target.write_text(text, encoding="utf-8")
    log("OK  Domain Lock aplicado")


def run_deep_diagnostic(root: Path) -> int:
    script = root / "scripts" / "hermes_deep_diagnostic.py"
    if not script.exists():
        log("SKIP deep_diagnostic ausente")
        return 0
    env = os.environ.copy()
    env["PAPER_TRADE"] = PAPER
    env["EXECUTION_ALLOWED"] = EXEC
    env["PYTHONUTF8"] = "1"
    try:
        r = subprocess.run(
            [PY, str(script), "--root", str(root), "--deep", "--report"],
            cwd=str(root),
            env=env,
            timeout=120,
            capture_output=True,
            text=True,
        )
        out = (r.stdout or "")[-2000:]
        if out:
            print(out)
        log(f"Deep diagnostic exit={r.returncode}")
        return r.returncode
    except Exception as e:
        log(f"Deep diagnostic erro: {e}")
        return 1


def open_hermes_panel(root: Path) -> None:
    panel = root / "scripts" / "hermes_control_panel.py"
    if panel.exists():
        start_py(panel, ["--root", str(root)], "Hermes-Painel", os.environ.copy())
        return
    # fallback: open deep report in browser
    report = root / "logs_supervisor" / "HERMES_DEEP_LATEST.txt"
    if report.exists():
        webbrowser.open(report.as_uri())
        log("Hermes report aberto no browser")
    else:
        log("Hermes painel/report nao disponivel — diagnostico ja rodou")


def open_desktop_exe(root: Path) -> None:
    exe = root / "desktop" / "publish" / "Aura.QuantX.Desktop.exe"
    if exe.exists():
        try:
            subprocess.Popen([str(exe)], cwd=str(root))
            log(f"Desktop EXE iniciado: {exe}")
        except Exception as e:
            log(f"Desktop EXE falhou: {e}")
    else:
        log("Desktop EXE ausente (OK — Matriz HTTP ja cobre a interface)")


def patch_desktop_json(root: Path) -> None:
    p = root / "desktop" / "config" / "desktop.json"
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        app = data.setdefault("app", {})
        app["fallbackHomepages"] = [
            "http://127.0.0.1:8766/index.html",
            "http://127.0.0.1:8766/",
            "https://aura.local/",
            "https://aura.local/index.html",
        ]
        app["homepage"] = "http://127.0.0.1:8766/index.html"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log("OK  desktop.json homepage → 127.0.0.1:8766 (anti-404)")
    except Exception as e:
        log(f"patch desktop.json: {e}")


def main() -> int:
    global ROOT, PY
    root_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    ROOT = root_arg.resolve()
    if not (ROOT / "engine" / "server.py").exists():
        alt = Path(r"C:\aura")
        if (alt / "engine" / "server.py").exists():
            ROOT = alt

    os.chdir(ROOT)
    os.environ["PAPER_TRADE"] = PAPER
    os.environ["EXECUTION_ALLOWED"] = EXEC
    os.environ["GLM_ADVISORY_ONLY"] = "true"
    os.environ["CORNERAI_BRIDGE_REQUIRE_TOKEN"] = "0"
    os.environ["AURA_ROOT"] = str(ROOT)
    os.environ["PYTHONUTF8"] = "1"

    PY = find_python(ROOT)
    log(f"=== AURA Orchestrator {VERSION} ===")
    log(f"ROOT={ROOT}")
    log(f"PYTHON={PY}")
    log(f"Invariantes: paper_trade={PAPER} execution_allowed={EXEC}")

    # 1) Limpeza de portas
    log("--- 1/8 Limpeza de portas ---")
    for port in (8080, 8765, 8099, 8766):
        if port_open(port):
            log(f"Liberando porta {port}...")
            kill_port_windows(port)
    time.sleep(2)

    # 2) Patch rotas
    log("--- 2/8 Correcao de rotas (anti-404) ---")
    patch_desktop_json(ROOT)
    apply_domain_lock(ROOT)

    env = os.environ.copy()

    # 3) Bridge
    log("--- 3/8 Bridge :8080 ---")
    start_py(ROOT / "bridge" / "server.py", ["--host", "127.0.0.1", "--port", "8080"], "Bridge", env)
    wait_port(8080, 35, "Bridge")

    # 4) Engine
    log("--- 4/8 Engine :8765 ---")
    start_py(ROOT / "engine" / "server.py", ["--host", "127.0.0.1", "--port", "8765"], "Engine", env)
    wait_port(8765, 45, "Engine")

    # 5) Voice
    log("--- 5/8 Voice :8099 ---")
    start_py(
        ROOT / "bridge" / "jarvis_voice_server.py",
        ["--host", "127.0.0.1", "--port", "8099", "--lazy"],
        "Voice",
        env,
    )
    wait_port(8099, 20, "Voice")

    # 6) Matriz HTTP (solucao 404)
    log("--- 6/8 Matriz Operator OS (HTTP local) ---")
    ui = find_matriz_dir(ROOT)
    server = None
    if ui:
        server = start_matriz_http(ui, 8766)
        if server and wait_port(8766, 10, "Matriz"):
            url = "http://127.0.0.1:8766/index.html"
            try:
                webbrowser.open(url)
                log(f"Matriz aberta: {url}")
            except Exception as e:
                log(f"webbrowser: {e}")
    else:
        log("ERRO CRITICO: pasta Matriz com index.html nao encontrada")

    open_desktop_exe(ROOT)

    # 7) Diagnostico profundo automatico
    log("--- 7/8 Hermes Deep Diagnostic (autonomo) ---")
    run_deep_diagnostic(ROOT)

    # 8) Painel Hermes
    log("--- 8/8 Hermes Painel ---")
    open_hermes_panel(ROOT)

    log("=== CONCLUIDO — ZERO TOUCH ===")
    log("Matriz:  http://127.0.0.1:8766/index.html")
    log("Bridge:  http://127.0.0.1:8080/health")
    log("Engine:  http://127.0.0.1:8765/api/health")
    log("Report:  logs_supervisor/HERMES_DEEP_LATEST.txt")
    log("Log:     logs_supervisor/ORCHESTRATOR_V30.log")
    log("Sistema permanece no ar. Feche esta janela apenas quando quiser parar o orquestrador.")

    # Mantem processo vivo para o servidor HTTP da Matriz
    try:
        while True:
            time.sleep(60)
            # self-heal leve: se matriz caiu, tenta de novo
            if ui and not port_open(8766):
                log("Self-heal: Matriz caiu — reiniciando HTTP")
                server = start_matriz_http(ui, 8766)
    except KeyboardInterrupt:
        log("Encerrado pelo utilizador")
        if server:
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
