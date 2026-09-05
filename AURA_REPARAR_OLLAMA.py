#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA_REPARAR_OLLAMA.py
Ciclo VRAM CONTROL sem urllib/urlopen (corrige [Errno 11001] getaddrinfo failed).

Uso (Admin, Windows 11):
    python AURA_REPARAR_OLLAMA.py

Pode ser importado por outros módulos AURA no lugar de urlopen:
    from AURA_REPARAR_OLLAMA import ollama_json
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
from typing import Any, Optional, Tuple

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
MODEL_LIGHT = "llama3.2:1b"
MODEL_SMART = "llama3.1:8b-instruct-q4_K_M"


def neutralize_http_proxy() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
    os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
    try:
        import urllib.request as ur

        ur.getproxies = lambda: {}  # type: ignore[method-assign]
        ur.install_opener(ur.build_opener(ur.ProxyHandler({})))
    except Exception:
        pass


class LoopbackHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        socket.inet_aton(self.host)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout or 60)
        sock.connect((self.host, int(self.port)))
        self.sock = sock


def ollama_json(
    method: str,
    path: str,
    payload: Optional[dict] = None,
    *,
    host: str = OLLAMA_HOST,
    port: int = OLLAMA_PORT,
    timeout: int = 180,
) -> Tuple[int, Any]:
    """
    Substitui urllib.request.urlopen('http://127.0.0.1:11434/...').
    Host e porta entram SEPARADOS. Sem string '127.0.0.1:11434'.
    """
    if ":" in str(host):
        raise ValueError("host deve ser '127.0.0.1' sem porta")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn = LoopbackHTTPConnection(host, int(port), timeout=timeout)
    try:
        headers = {"Host": host, "Accept": "application/json", "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            headers["Content-Length"] = str(len(body))
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return resp.status, parsed
    finally:
        try:
            conn.close()
        except Exception:
            pass


def reparar() -> int:
    neutralize_http_proxy()
    print("🚨 [VRAM CONTROL] Expulsando", MODEL_LIGHT, "e injetando", MODEL_SMART, "na GPU...")
    print("🧠 [LAUDO DE REPARO EM TEMPO REAL]:")
    print(f"   transporte: HTTPConnection({OLLAMA_HOST!r}, {OLLAMA_PORT}) — urlopen DESLIGADO")
    try:
        st, tags = ollama_json("GET", "/api/tags")
    except OSError as exc:
        print(f"[FALHA NA API] TCP {OLLAMA_HOST} porta {OLLAMA_PORT}: {exc}")
        print("Verifique se o painel do Ollama está aberto e ativo na barra de tarefas.")
        print("🔄 Ciclo abortado.")
        return 2
    print(f"   GET /api/tags HTTP {st}")
    if st >= 400:
        print(f"[FALHA NA API] Ollama respondeu {st}: {tags!r}")
        print("🔄 Ciclo abortado.")
        return 3

    st_u, body_u = ollama_json(
        "POST",
        "/api/generate",
        {"model": MODEL_LIGHT, "prompt": "", "stream": False, "keep_alive": 0},
    )
    print(f"   unload {MODEL_LIGHT}: HTTP {st_u}")
    if isinstance(body_u, dict) and body_u.get("error"):
        print("   aviso:", body_u.get("error"))

    st_l, body_l = ollama_json(
        "POST",
        "/api/generate",
        {
            "model": MODEL_SMART,
            "prompt": ".",
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_gpu": 99, "temperature": 0.2, "num_predict": 1},
        },
    )
    if st_l >= 400:
        err = body_l.get("error") if isinstance(body_l, dict) else body_l
        print(f"[FALHA NA API] HTTP {st_l} ao injetar {MODEL_SMART}: {err}")
        print("🔄 Ciclo concluído com falha.")
        return 4

    st_ps, ps = ollama_json("GET", "/api/ps")
    loaded = []
    if isinstance(ps, dict):
        loaded = [str(m.get("name") or m.get("model")) for m in (ps.get("models") or [])]
    print(f"   preload {MODEL_SMART}: HTTP {st_l}  keep_alive=15m  num_gpu=99")
    print(f"   GET /api/ps HTTP {st_ps}  residentes={loaded or ['N/D']}")
    print("🔄 Ciclo concluido. VRAM limpa com sucesso!")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        os.system("chcp 65001 >NUL")
    sys.exit(reparar())
