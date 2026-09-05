#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Control Plane V10 — HTTP stdlib :8777
===========================================
GET  /health
GET  /latest          → último relatório JSON
GET  /incident        → classificador sobre o latest
POST /cycle?fix=1     → corre um ciclo (lock respeitado)
Nunca altera execution_allowed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def find_root() -> Path:
    env = os.environ.get("AURA_ROOT")
    cands = [Path(env)] if env else []
    cands += [Path(r"C:\aura"), Path.cwd(), Path(__file__).resolve().parents[1]]
    for c in cands:
        if c and (c / "engine" / "server.py").exists():
            return c.resolve()
    return Path.cwd().resolve()


ROOT = find_root()
PORT = int(os.environ.get("HERMES_API_PORT", "8777"))


def _latest() -> dict:
    p = ROOT / "logs_supervisor" / "HERMES_AUTONOMOUS_LATEST.json"
    if not p.exists():
        return {"ok": False, "error": "no_latest"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[hermes-api] " + (fmt % args) + "\n")

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            latest = _latest()
            self._send(200, {
                "ok": True,
                "service": "hermes-control-plane",
                "version": "10.0.0",
                "root": str(ROOT),
                "paper_trade": True,
                "execution_allowed": False,
                "has_latest": "status" in latest,
                "status": latest.get("status", "UNKNOWN"),
            })
            return
        if path == "/latest":
            self._send(200, _latest())
            return
        if path == "/incident":
            latest = _latest()
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from hermes_incident import classify, human
                cls, reasons = classify(latest.get("findings") or [])
                self._send(200, {"incident": cls, "why": human(cls), "reasons": reasons})
            except Exception as e:
                self._send(500, {"error": str(e)})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/cycle":
            self._send(404, {"error": "not_found"})
            return
        qs = parse_qs(parsed.query)
        fix = "1" in qs.get("fix", ["1"])
        script = Path(__file__).resolve().parent / "hermes_autonomous_os.py"
        py = ROOT / "engine" / "venv" / "Scripts" / "python.exe"
        exe = str(py) if py.exists() else sys.executable
        cmd = [exe, str(script), "--once", "--root", str(ROOT)]
        if fix:
            cmd.append("--fix")
        env = os.environ.copy()
        env["PAPER_TRADE"] = "true"
        env["EXECUTION_ALLOWED"] = "false"
        env["AURA_ROOT"] = str(ROOT)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, env=env, cwd=str(ROOT))
            self._send(200, {
                "ok": r.returncode in (0, 1),
                "returncode": r.returncode,
                "latest": _latest(),
            })
        except Exception as e:
            self._send(500, {"error": str(e)})


def main() -> int:
    os.environ["PAPER_TRADE"] = "true"
    os.environ["EXECUTION_ALLOWED"] = "false"
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Hermes control plane http://127.0.0.1:{PORT}/health  root={ROOT}", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
