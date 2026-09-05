#!/usr/bin/env python3
"""Tool standalone para chamar o Orchestrator local (sem Ollama)."""

from __future__ import annotations

import json
import uuid
import urllib.request
from typing import Any

ORCH_URL = "http://127.0.0.1:8095/trigger"


def trigger_neo4j_local(
    cypher_query: str,
    rollback_cypher: str = "",
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    payload = {
        "cypher_query": cypher_query,
        "rollback_cypher": rollback_cypher,
        "correlation_id": correlation_id,
        "dry_run": dry_run,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ORCH_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "RETURN 1 AS ok"
    print(json.dumps(trigger_neo4j_local(q, dry_run=True), indent=2, ensure_ascii=False))
