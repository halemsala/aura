# -*- coding: utf-8 -*-
"""Matriz :8766 + proxy /api/aura/* para o Engine. Chat deixa de dar Failed to fetch."""
from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
CANDIDATES = [
    ROOT / "desktop" / "ui" / "matriz_v22",
    ROOT / "desktop" / "publish" / "ui" / "matriz_v22",
]
UI = next((p for p in CANDIDATES if (p / "index.html").exists()), None)
PORT = int(os.environ.get("AURA_MATRIZ_PORT", "8766"))
ENGINE = os.environ.get("AURA_ENGINE_URL", "http://127.0.0.1:8765").rstrip("/")
HERMES = os.environ.get("AURA_HERMES_URL", "http://127.0.0.1:8777").rstrip("/")
BRIDGE = os.environ.get("AURA_BRIDGE_URL", "http://127.0.0.1:8080").rstrip("/")
VOICE = os.environ.get("AURA_VOICE_URL", "http://127.0.0.1:8099").rstrip("/")

AURA_MAP = {
    "health": (ENGINE, "/api/health"),
    "status": (ENGINE, "/api/status"),
    "diagnostic": (ENGINE, "/api/diagnostics/deep"),
    "agents": (ENGINE, "/api/agents"),
    "activation": (ENGINE, "/api/activation"),
    "glm": (ENGINE, "/api/agents/glm/status"),
    "chat": (ENGINE, "/api/trader/chat"),
    "glm-chat": (ENGINE, "/api/glm_chat"),
    "tools": (ENGINE, "/api/tools"),
    "ui-state": (ENGINE, "/api/ui/state"),
    "feedback": (ENGINE, "/api/feedback"),
    "bridge": (BRIDGE, "/health"),
    "voice": (VOICE, "/api/voice/health"),
    "voice-tts": (VOICE, "/api/voice/tts"),
    "voice-talk": (VOICE, "/api/voice/talk"),
}

MANUS_SVG = {
    "aura-quant-x-mark": "aura-quant-x-mark.svg",
    "aura-command-core": "aura-command-core.svg",
    "aura-timeline-arc": "aura-timeline-arc.svg",
    "aura-temporal-match-stage": "aura-timeline-arc.svg",
    "aura-decision-capsule": "aura-command-core.svg",
    "sporting": "aura-sporting-crest.svg",
    "braga": "aura-braga-crest.svg",
}


def http_json(method, url, payload=None, timeout=12.0, extra_headers=None):
    data = None
    headers = {"Accept": "application/json", "X-AURA-UI": "matriz-8766"}
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, raw, resp.headers.get("Content-Type", "application/json")
    except HTTPError as e:
        raw = e.read()
        return e.code, raw, "application/json"
    except Exception as exc:
        body = json.dumps({"ok": False, "error": str(exc), "url": url}).encode("utf-8")
        return 502, body, "application/json"


def deterministic_chat(message: str) -> dict:
    st, raw, _ = http_json("GET", ENGINE + "/api/ui/state", timeout=3)
    view = {}
    try:
        snap = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        view = snap.get("snapshot", {}).get("view") or snap.get("view") or {}
    except Exception:
        view = {}
    home = view.get("home") or view.get("home_team")
    away = view.get("away") or view.get("away_team")
    minute = view.get("minute")
    if home and away:
        reply = (
            f"Core local OK. Live {home} x {away}"
            + (f", {minute}′" if minute is not None else "")
            + ". Paper trade; sem ordem real. Não invento odd nem canto que não esteja no ui/state."
        )
    else:
        reply = (
            "Chat local no ar. Engine sem fixture no ui/state — não invento jogo. "
            "Abra SokkerPRO no Desktop (F2) e volte com F1. paper_trade=true."
        )
    if message:
        reply += " Pedido: " + message[:180]
    return {
        "reply": reply,
        "message": reply,
        "text": reply,
        "model": "aura-local-fallback",
        "paper_trade": True,
        "execution_allowed": False,
        "source": "matriz_proxy_fallback",
    }


def paper_activate_all() -> dict:
    """Marcadores paper-only. Nao habilita apostas reais."""
    path = ROOT / "agents" / "activation_manifest.json"
    en_dir = ROOT / "agents" / "ENABLED"
    en_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"agents": {}}
    agents = data.get("agents") or {}
    changed = 0
    markers = 0
    for aid, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("status") != "enabled":
            changed += 1
        spec["status"] = "enabled"
        spec["paper_trade"] = True
        pth = str(spec.get("path") or "")
        base = Path(pth).name if pth else aid.split(":")[-1]
        content = (
            f"enabled=true\nagent_id={aid}\npath={pth}\nstatus=enabled\npaper_trade=true\n"
        )
        for name in dict.fromkeys([base + ".enabled", aid.replace(":", "_").replace("/", "_") + ".enabled"]):
            (en_dir / name).write_text(content, encoding="utf-8")
            markers += 1
    data["agents"] = agents
    data["version"] = str(data.get("version") or "") + "+activated"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    index = {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "changed_status": changed,
        "markers_written": markers,
        "declared": len(agents),
        "source": "matriz_paper_activate",
    }
    (ROOT / "agents" / "activation_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index


def _trpc_payload(path: str, query: str) -> bytes:
    """Cliente tRPC faz C.data.filter(...). list = ARRAY. batch=1 = [result]."""
    is_list = "alertCenter.list" in path
    inner = {"result": {"data": {"json": [] if is_list else {"ok": True}}}}
    qs = parse_qs(query or "")
    batched = (qs.get("batch") or ["0"])[0] == "1"
    body = [inner] if batched else inner
    return json.dumps(body).encode("utf-8")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("[matriz8766] " + (fmt % args) + "\n")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        super().end_headers()

    def _send(self, code, raw, ctype="application/json; charset=utf-8"):
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def do_OPTIONS(self):
        self._send(204, b"")

    def _send_manus(self, path: str) -> bool:
        name = Path(path).name.lower()
        svg_name = "aura-club-placeholder.svg"
        for key, fname in MANUS_SVG.items():
            if key in name:
                svg_name = fname
                break
        fp = (UI / svg_name) if UI else None
        if fp and fp.is_file():
            self._send(200, fp.read_bytes(), "image/svg+xml")
            return True
        self._send(204, b"", "image/svg+xml")
        return True

    def _proxy_aura(self, method):
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        qs = parsed.query or ""

        if path.startswith("/api/trpc/") or "alertCenter." in path:
            if method == "POST":
                self._read_body()
            self._send(200, _trpc_payload(path, qs))
            return True

        if path in ("/api/chat", "/api/hermes/chat"):
            incoming = self._read_body() if method == "POST" else b""
            code, raw, ctype = http_json(
                method, HERMES + "/api/chat", incoming or b"{}", timeout=90
            )
            self._send(code, raw, ctype)
            return True

        if path in ("/health", "/api/health"):
            self._send(200, json.dumps({
                "ok": True, "service": "matriz", "port": PORT, "ui": str(UI),
                "paper_trade": True, "execution_allowed": False,
            }))
            return True
        if path in ("/api/ui/state", "/api/aura/ui-state"):
            code, raw, ctype = http_json("GET", ENGINE + "/api/ui/state")
            self._send(code, raw, ctype)
            return True
        if not path.startswith("/api/aura/"):
            return False
        route = path[len("/api/aura/"):].strip("/")
        base = route.split("/", 1)[0]
        rest = route.split("/", 1)[1] if "/" in route else ""
        mapped = AURA_MAP.get(base)
        incoming = self._read_body() if method in ("POST", "PUT", "PATCH") else b""
        if route == "tools/activate-all" and method == "POST":
            self._send(200, json.dumps(paper_activate_all(), ensure_ascii=False))
            return True
        if mapped:
            url = mapped[0] + mapped[1]
            if rest:
                url = url.rstrip("/") + "/" + rest
            if qs:
                url += "?" + qs
            payload = incoming if incoming else None
            if base in ("chat", "glm-chat") and method == "POST":
                code, raw, ctype = http_json(method, url, payload or b"{}", timeout=20)
                text = ""
                try:
                    data = json.loads(raw.decode("utf-8", "replace") or "{}")
                    if isinstance(data, dict):
                        text = str(data.get("reply") or data.get("message") or data.get("text") or "").strip()
                except Exception:
                    data = {}
                if code >= 400 or not text:
                    msg = ""
                    try:
                        msg = json.loads(incoming.decode("utf-8") or "{}").get("message") or ""
                    except Exception:
                        msg = ""
                    fb = deterministic_chat(str(msg))
                    if isinstance(data, dict):
                        data.update(fb)
                    else:
                        data = fb
                    self._send(200, json.dumps(data, ensure_ascii=False))
                    return True
                self._send(code, raw, ctype)
                return True
            code, raw, ctype = http_json(method, url, payload if incoming else None)
            self._send(code, raw, ctype)
            return True
        url = ENGINE + "/api/" + route
        if qs:
            url += "?" + qs
        code, raw, ctype = http_json(method, url, incoming if incoming else None)
        self._send(code, raw, ctype)
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        if path.startswith("/manus-storage/"):
            self._send_manus(path)
            return
        if path in ("/favicon.ico", "/favicon.png"):
            mark = (UI / "aura-quant-x-mark.svg") if UI else None
            if mark and mark.is_file():
                self._send(200, mark.read_bytes(), "image/svg+xml")
            else:
                self._send(204, b"")
            return
        if path in ("/index.html", "/index.htm"):
            self.send_response(302)
            self.send_header("Location", "/" + (("?" + parsed.query) if parsed.query else ""))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self._proxy_aura("GET"):
            return
        ext = Path(path).suffix.lower()
        fs = Path(self.translate_path(path))
        if (not fs.exists()) and (not path.startswith("/api/")) and ext in ("", ".html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self._proxy_aura("POST"):
            return
        self._send(404, json.dumps({"ok": False, "error": "not_found"}))


def main():
    if UI is None:
        print("[FATAL] desktop/ui/matriz_v22/index.html ausente", file=sys.stderr)
        return 2
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("MATRIZ_LISTEN http://127.0.0.1:%s/" % PORT)
    print("PROXY /api/aura/* -> Engine %s" % ENGINE)
    print("PROXY /api/chat -> Hermes %s" % HERMES)
    print("UI=%s" % UI)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
