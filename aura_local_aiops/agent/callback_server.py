#!/usr/bin/env python3
"""Callback receiver — recebe feedback do Orchestrator local."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

EXPECTED_TOKEN = "local-secret-token"
pending: dict[str, dict] = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/api/agent/callback":
            self.send_error(404)
            return
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {EXPECTED_TOKEN}":
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_error(400)
            return
        corr = payload.get("correlation_id", "?")
        status = payload.get("status", "?")
        print(f"[CALLBACK] {corr} → {status}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if corr:
            pending[corr] = payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    port = 8090
    print(f"Callback server em http://127.0.0.1:{port}/api/agent/callback")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
