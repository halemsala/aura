#!/usr/bin/env python3
"""
AURA Local Orchestrator — substitui Harness CI/CD em ambiente 100% local.
Recebe pedidos do Agente (via Ollama tool-calling), aplica Cypher no Neo4j
local e devolve callback.
"""

from __future__ import annotations

import json
import os
import subprocess
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.request import Request, urlopen

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "aura_local_pass")
CALLBACK_URL = os.getenv("AURA_CALLBACK_URL", "http://127.0.0.1:8090/api/agent/callback")
CALLBACK_TOKEN = os.getenv("AURA_CALLBACK_TOKEN", "local-secret-token")
ORCH_PORT = int(os.getenv("ORCH_PORT", "8095"))


def run_cypher(query: str) -> tuple[bool, str]:
    if not query or not query.strip():
        return False, "query vazia"
    try:
        result = subprocess.run(
            [
                "cypher-shell",
                "-a", NEO4J_URI,
                "-u", NEO4J_USER,
                "-p", NEO4J_PASS,
                "--format", "plain",
                "--non-interactive",
            ],
            input=query,
            text=True,
            capture_output=True,
            timeout=45,
        )
        if result.returncode == 0:
            return True, (result.stdout or "").strip() or "OK"
        err = (result.stderr or result.stdout or "").strip()
        return False, err or f"exit code {result.returncode}"
    except FileNotFoundError:
        # Fallback: tenta via Python neo4j driver se cypher-shell não existir
        return run_cypher_driver(query)
    except Exception as e:
        return False, str(e)


def run_cypher_driver(query: str) -> tuple[bool, str]:
    """Fallback usando o driver oficial neo4j (pip install neo4j)."""
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            NEO4J_URI.replace("neo4j://", "bolt://"),
            auth=(NEO4J_USER, NEO4J_PASS),
        )
        with driver.session() as session:
            result = session.run(query)
            records = [dict(r) for r in result]
        driver.close()
        return True, json.dumps(records, default=str) if records else "OK"
    except ImportError:
        return False, "nem cypher-shell nem pacote 'neo4j' encontrados. Instale: pip install neo4j"
    except Exception as e:
        return False, str(e)


def send_callback(payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        CALLBACK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CALLBACK_TOKEN}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=5) as resp:
            print(f"[callback] HTTP {resp.status}")
    except Exception as e:
        print(f"[callback] falhou (ok se o agente ainda não escuta): {e}")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/trigger":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_error(400, "JSON inválido")
            return

        cypher = body.get("cypher_query", "")
        rollback = body.get("rollback_cypher", "")
        corr = body.get("correlation_id", "unknown")
        dry_run = str(body.get("dry_run", "false")).lower() in ("true", "1", "yes")

        print(f"\n=== [{corr}] dry_run={dry_run} ===")
        print(cypher[:300] if cypher else "(vazio)")

        if dry_run:
            ok, msg = True, "DRY_RUN – nada aplicado"
        else:
            ok, msg = run_cypher(cypher)

        if not ok and rollback:
            print("→ executando rollback")
            r_ok, r_msg = run_cypher(rollback)
            status = "FAILED_ROLLED_BACK" if r_ok else "FAILED"
            msg = f"erro: {msg} | rollback: {r_msg}"
        else:
            status = "SUCCESS" if ok else "FAILED"

        send_callback({
            "correlation_id": corr,
            "status": status,
            "message": msg,
            "source": "local_orchestrator",
        })

        resp = {
            "status": status,
            "correlation_id": corr,
            "message": msg,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"service":"aura-local-orchestrator"}')
        else:
            self.send_error(404)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    print("=" * 50)
    print("  AURA Local Orchestrator (Harness local)")
    print("=" * 50)
    print(f"  Porta     : {ORCH_PORT}")
    print(f"  Neo4j     : {NEO4J_URI}")
    print(f"  Callback  : {CALLBACK_URL}")
    print(f"  Endpoint  : http://127.0.0.1:{ORCH_PORT}/trigger")
    print("=" * 50)
    HTTPServer(("127.0.0.1", ORCH_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
