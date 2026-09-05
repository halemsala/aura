#!/usr/bin/env python3
"""
Painel mínimo de visão AURA (só leitura) — http://127.0.0.1:3029

Não muta sistema. Não exige browser externo além de localhost.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

from snapshot import collect_snapshot, offline_services  # noqa: E402
from ops_loop import run_loop  # noqa: E402

try:
    import harness_lab_vision as hv  # noqa: E402
except Exception:
    hv = None  # type: ignore

HOST = "127.0.0.1"
PORT = int(__import__("os").environ.get("AURA_VISION_PORT", "3029"))


def _payload() -> dict:
    snap = collect_snapshot(include_ui_state=True)
    vision = None
    if hv is not None:
        # sem AURA_ROOT real: usa path vazio / cwd
        aura = Path(__import__("os").environ.get("AURA_ROOT", "C:/aura"))
        expanded = hv.expand_snapshot(
            {
                **snap,
                "model": snap.get("model", "?"),
                "keep_alive": "?",
                "num_ctx": 0,
                "boot_state": {},
                "diagnostic": {},
                "policy": snap.get("policy")
                or {"paper_trade": True, "execution_allowed": False, "mode": "analise_operante"},
            },
            aura,
        )
        vision = expanded.get("vision")
    ops = run_loop("", record=False)
    return {
        "snapshot": snap,
        "offline": offline_services(snap),
        "vision": vision,
        "ops": {
            "phase": ops.get("phase"),
            "failure_mode": ops.get("failure_mode"),
            "official_tools": ops.get("official_tools"),
            "proposed_recovery": ops.get("proposed_recovery"),
        },
        "policy": {"paper_trade": True, "execution_allowed": False, "advisory_only": True},
    }


HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AURA Vision Panel</title>
<style>
  body{font-family:ui-sans-serif,system-ui,sans-serif;background:#0b1220;color:#e6eefc;margin:0;padding:1.2rem}
  h1{font-size:1.2rem;margin:0 0 .5rem}
  .muted{color:#8aa0c0;font-size:.9rem}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.6rem;margin:1rem 0}
  .card{background:#121a2b;border:1px solid #24304a;border-radius:10px;padding:.8rem}
  .on{color:#3ddc97}.off{color:#ff6b6b}
  pre{background:#0a0f18;border-radius:8px;padding:.8rem;overflow:auto;font-size:.78rem;line-height:1.35}
  button{background:#2b6cb0;color:#fff;border:0;border-radius:8px;padding:.5rem .9rem;cursor:pointer}
  button:hover{background:#3182ce}
</style>
</head>
<body>
  <h1>AURA Vision Panel <span class="muted">só leitura · paper</span></h1>
  <p class="muted">localhost only · não executa recovery · use Harness + CONFIRMAR para mutação</p>
  <button onclick="load()">Atualizar</button>
  <div class="grid" id="svc"></div>
  <div class="card"><strong>OPS (sugestão)</strong><pre id="ops">…</pre></div>
  <div class="card"><strong>Visão / snapshot</strong><pre id="raw">…</pre></div>
<script>
async function load(){
  const r = await fetch('/api/snapshot');
  const j = await r.json();
  const svc = document.getElementById('svc');
  svc.innerHTML = '';
  const services = (j.snapshot && j.snapshot.services) || {};
  for (const [name, item] of Object.entries(services)){
    const on = item.online;
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `<div><strong>${name}</strong></div>
      <div class="${on?'on':'off'}">${on?'ONLINE':'OFFLINE'}</div>
      <div class="muted">porta ${item.port||'-'}</div>`;
    svc.appendChild(el);
  }
  document.getElementById('ops').textContent = JSON.stringify(j.ops, null, 2);
  document.getElementById('raw').textContent = JSON.stringify({
    offline: j.offline,
    coverage: j.vision && j.vision.coverage_score_approx,
    layers: j.vision && j.vision.layers ? Object.keys(j.vision.layers) : [],
    policy: j.policy
  }, null, 2);
}
load();
setInterval(load, 15000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[vision_panel] " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/snapshot":
            try:
                data = _payload()
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, body, "application/json; charset=utf-8")
            return
        if path == "/api/ops":
            qs = parse_qs(urlparse(self.path).query)
            symptom = (qs.get("symptom") or [""])[0]
            try:
                data = run_loop(symptom, record=False)
                self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AURA Vision Panel: http://{HOST}:{PORT}/  (Ctrl+C para sair)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
