#!/usr/bin/env python3
"""Persist last RedTeam audit for Tools Hub."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import os

ROOT = Path(os.environ.get("AURA_ROOT", r"C:\aura"))
if not (ROOT / "engine").exists():
    ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "elite_squad" / "last_veto.json"

def main():
    # optional JSON on stdin or args
    data = {"verdict": "UNKNOWN", "effective_decision": "AGUARDA", "reasons": [], "at": time.time()}
    if not sys.stdin.isatty():
        try:
            data.update(json.load(sys.stdin))
        except json.JSONDecodeError:
            pass
    data.setdefault("paper_trade", True)
    data.setdefault("execution_allowed", False)
    data["at"] = time.time()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(OUT)

if __name__ == "__main__":
    main()
