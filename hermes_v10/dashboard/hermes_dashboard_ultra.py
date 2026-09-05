#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dashboard stdlib — bind 127.0.0.1 only."""
from __future__ import annotations
import json, os, socket, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("HERMES_DASH_PORT", "8778"))
ROOT = Path(os.environ.get("AURA_ROOT", Path(__file__).resolve().parents[1]))

def snapshot():
    def up(p):
        try:
            with socket.create_connection(("127.0.0.1", p), timeout=0.25):
                return True
        except OSError:
            return False
    return {
        "version": "10.2.0-COMPLETE",
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ports": {str(p): up(p) for p in (8080, 8765, 8766, 8777, 8099, 11434)},
        "paper_trade": True,
        "execution_allowed": False,
        "auth_required": bool(os.environ.get("HERMES_API_TOKEN")),
    }

HTML = """<!DOCTYPE html><html><head><meta charset=utf-8><title>Hermes</title>
<style>body{font-family:system-ui;background:#0b0f16;color:#e5e7eb;padding:24px}
pre{background:#121826;padding:16px;border-radius:8px}</style></head><body>
<h1>Hermes V10 Ultra</h1><pre id=s>...</pre>
<script>async function t(){const r=await fetch('/api/status');s.textContent=JSON.stringify(await r.json(),null,2)}
t();setInterval(t,5000)</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            b = HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif self.path in ("/api/status", "/health"):
            b = json.dumps(snapshot()).encode(); self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()

if __name__ == "__main__":
    print(f"Dashboard http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
