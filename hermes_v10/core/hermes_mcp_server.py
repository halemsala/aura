#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal local MCP-style tool server over stdio JSON lines.
Not full MCP wire protocol — safe allowlist tools for agents.
Protocol: each stdin line is JSON {"id":1,"method":"tools/list"|"tools/call","params":{}}
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

# ensure core on path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hermes_llm_engine import ToolRegistry  # type: ignore

ROOT = Path(os.environ.get("AURA_ROOT", Path(__file__).resolve().parents[2]))
TOKEN = (os.environ.get("HERMES_API_TOKEN") or "").strip()
ALLOW = {
    "read_file", "list_dir", "system_status", "search_logs",
    "search_memory", "check_constitution", "run_digital_twin",
}
# apply_fix never via MCP by default

def main():
    tools = ToolRegistry(ROOT)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        # optional token
        if TOKEN and params.get("token") != TOKEN and msg.get("token") != TOKEN:
            print(json.dumps({"id": mid, "error": "unauthorized"}), flush=True)
            continue
        if method == "tools/list":
            schemas = [s for s in tools.schemas() if s["name"] in ALLOW]
            print(json.dumps({"id": mid, "result": schemas}), flush=True)
        elif method == "tools/call":
            name = params.get("name") or params.get("tool")
            args = params.get("arguments") or params.get("args") or {}
            if name not in ALLOW:
                print(json.dumps({"id": mid, "error": f"tool not allowed: {name}"}), flush=True)
                continue
            result = tools.call(name, args if isinstance(args, dict) else {})
            print(json.dumps({"id": mid, "result": result}), flush=True)
        else:
            print(json.dumps({"id": mid, "error": f"unknown method {method}"}), flush=True)

if __name__ == "__main__":
    main()
