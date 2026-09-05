#!/usr/bin/env python3
"""AURA Emergency Bridge - stdlib only - port 8080"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PORT = 8080
HOST = "127.0.0.1"
DATA = Path(__file__).resolve().parent / "data_emergency"
DATA.mkdir(parents=True, exist_ok=True)
FEED_LOG = DATA / "feed.jsonl"
COUNT = {"n": 0}

def now():
    return datetime.now(timezone.utc).isoformat()

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/health", "/api/cornerai/health"):
            self._json(200, {
                "ok": True,
                "status": "ok",
                "service": "aura_emergency_bridge",
                "port": PORT,
                "received": COUNT["n"],
                "ts": now(),
            })
            return
        if path in ("/api/cornerai/latest", "/latest"):
            last = None
            if FEED_LOG.exists():
                lines = FEED_LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                if lines:
                    try:
                        last = json.loads(lines[-1])
                    except Exception:
                        last = {"raw": lines[-1][:200]}
            self._json(200, {"ok": True, "latest": last, "count": COUNT["n"]})
            return
        self._json(404, {"ok": False, "error": "not found", "path": path})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except Exception as e:
            self._json(400, {"ok": False, "error": "invalid json", "detail": str(e)})
            return
        COUNT["n"] += 1
        entry = {"ts": now(), "n": COUNT["n"], "path": path, "payload": payload}
        try:
            with FEED_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print("write error", e, flush=True)
        # Accept any feed path the extension might use
        if path in (
            "/api/cornerai/feed", "/feed",
            "/api/cornerai/skill-feed", "/skill-feed",
            "/api/cornerai/skill-latest",
        ) or path.startswith("/api/"):
            self._json(200, {
                "ok": True,
                "accepted": True,
                "n": COUNT["n"],
                "service": "aura_emergency_bridge",
                "ts": now(),
            })
            return
        self._json(404, {"ok": False, "error": "not found", "path": path})

def main():
    print("=" * 60, flush=True)
    print(" AURA EMERGENCY BRIDGE", flush=True)
    print(" http://%s:%s/health" % (HOST, PORT), flush=True)
    print(" Deixe esta janela ABERTA", flush=True)
    print("=" * 60, flush=True)
    httpd = ThreadingHTTPServer((HOST, PORT), H)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutdown", flush=True)
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main()
