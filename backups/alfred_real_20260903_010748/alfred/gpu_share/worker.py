#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker GPU para um PC secundário. Só stdlib + urllib.
Arranque: python worker.py --token SEGREDO [--lan] [--max-pct 60] [--port 8795]
Por defeito escuta 127.0.0.1. --lan liga 0.0.0.0 (o dono deste PC escolhe).
Nunca apaga ficheiros. Pausa com jogos / VRAM cheia.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import URLError

GAME_HINTS = {
    "valorant", "cs2", "csgo", "fortnite", "gta5", "gtav", "r5apex", "overwatch",
    "league of legends", "leagueclient", "riotclient", "steam", "epicgameslauncher",
    "battle.net", "wow", "cod", "warzone", "minecraft", "roblox", "genshin",
    "eldenring", "cyberpunk", "dota2", "pubg", "rainbowsix", "fifa", "fc25",
}


def nvidia():
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True, timeout=3, stderr=subprocess.DEVNULL)
        parts = [p.strip() for p in out.strip().split(",")]
        return {
            "total": float(parts[0]), "used": float(parts[1]),
            "free": float(parts[2]), "util": float(parts[3]),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:160]}


def games_running() -> list:
    found = []
    try:
        out = subprocess.check_output(["tasklist", "/fo", "csv", "/nh"],
                                      text=True, timeout=8, errors="replace")
    except Exception:
        return found
    low = out.lower()
    for g in GAME_HINTS:
        if g in low:
            found.append(g)
    return found


class WorkerState:
    def __init__(self, token: str, max_pct: float):
        self.token = token
        self.max_pct = max(10.0, min(float(max_pct), 60.0))
        self.paused = False
        self.reason = ""
        self.lock = threading.Lock()
        self.jobs = 0

    def refresh(self):
        g = games_running()
        nv = nvidia()
        paused, reason = False, ""
        if g:
            paused, reason = True, "jogo detectado: " + ",".join(g[:4])
        elif "total" in nv:
            cap = nv["total"] * (self.max_pct / 100.0)
            if nv["used"] > cap:
                paused, reason = True, f"VRAM {nv['used']:.0f} > tecto {cap:.0f} MiB ({self.max_pct}%)"
            elif nv["free"] < 400:
                paused, reason = True, "Windows a pedir VRAM (free < 400 MiB)"
        with self.lock:
            self.paused, self.reason = paused, reason
        return {"paused": paused, "reason": reason, "gpu": nv, "games": g, "max_pct": self.max_pct}


STATE: WorkerState | None = None


def _ollama_chat(payload: dict) -> dict:
    body = json.dumps({
        "model": payload.get("model") or os.environ.get("AURA_OLLAMA_MODEL", "qwen3:8b"),
        "messages": payload.get("messages") or [],
        "stream": False,
        "keep_alive": "5m",
        "think": False,
        "options": {
            "num_ctx": int(payload.get("num_ctx") or 1024),
            "num_predict": int(payload.get("num_predict") or 256),
            "temperature": float(payload.get("temperature") or 0.2),
        },
    }).encode("utf-8")
    req = urlrequest.Request("http://127.0.0.1:11434/api/chat", data=body,
                             headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        msg = (data.get("message") or {}).get("content") or ""
        return {"ok": True, "reply": msg, "model": data.get("model")}
    except URLError as e:
        return {"ok": False, "error": str(e)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[gpu-worker] " + (fmt % args) + "\n")

    def _auth(self) -> bool:
        got = self.headers.get("X-Aura-Share-Token") or ""
        return bool(STATE and got and got == STATE.token)

    def _json(self, code: int, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/health", "/status"):
            snap = STATE.refresh() if STATE else {}
            snap["ok"] = True
            return self._json(200, snap)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return self._json(401, {"error": "token inválido"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200_000:
            return self._json(413, {"error": "payload grande"})
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "json inválido"})
        snap = STATE.refresh()
        if self.path == "/pause":
            STATE.paused = True
            STATE.reason = "pausa manual"
            return self._json(200, {"paused": True})
        if self.path == "/resume":
            STATE.paused = False
            STATE.reason = ""
            return self._json(200, STATE.refresh())
        if self.path != "/work":
            return self._json(404, {"error": "not found"})
        if snap.get("paused"):
            return self._json(503, {"error": "worker em pausa", "status": snap})
        kind = str(payload.get("kind") or "ollama_chat")
        if kind != "ollama_chat":
            return self._json(400, {"error": f"kind não suportado: {kind}"})
        STATE.jobs += 1
        result = _ollama_chat(payload)
        result["worker_status"] = STATE.refresh()
        return self._json(200 if result.get("ok") else 502, result)


def main():
    global STATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--port", type=int, default=int(os.environ.get("AURA_GPU_SHARE_PORT", "8795")))
    ap.add_argument("--max-pct", type=float, default=float(os.environ.get("AURA_GPU_SHARE_MAX_PCT", "60")))
    ap.add_argument("--lan", action="store_true", help="escuta 0.0.0.0 — só se TU neste PC quiseres")
    args = ap.parse_args()
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    STATE = WorkerState(args.token, args.max_pct)
    httpd = ThreadingHTTPServer((host, args.port), Handler)
    print(f"AURA GPU worker em http://{host}:{args.port}  max_vram={STATE.max_pct}%  lan={args.lan}")
    print("GET /health  POST /work (header X-Aura-Share-Token)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stop")


if __name__ == "__main__":
    main()
