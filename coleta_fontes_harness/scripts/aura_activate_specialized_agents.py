#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AURA V32 - Activate specialized agents (paper-only, advisory)."""
from __future__ import annotations
import json, os, sys
from pathlib import Path

PAPER = "true"
EXEC = "false"

PRIORITY = [
    "corner_intelligence",
    "corner_window_specialist",
    "hawkes_corners",
    "digital_twin_monte_carlo",
    "market_edge",
    "odds_quality_monitor",
    "data_veracity",
    "drift_monitor",
    "gpu_resource_manager",
    "browser_agent",
    "health_score",
    "auto_calibrate_risk",
]

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    os.environ["PAPER_TRADE"] = PAPER
    os.environ["EXECUTION_ALLOWED"] = EXEC
    os.environ["GLM_ADVISORY_ONLY"] = "true"

    enabled_dir = root / "agents" / "ENABLED"
    enabled_dir.mkdir(parents=True, exist_ok=True)

    found = []
    if enabled_dir.exists():
        for p in sorted(enabled_dir.glob("*.enabled")):
            found.append(p.name)

    print(f"[AGENTS] ENABLED flags: {len(found)}")
    for name in found[:40]:
        print(f"  - {name}")

    manifest = root / "agents" / "activation_manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            print(f"[AGENTS] activation_manifest keys: {list(data)[:12]}")
        except Exception as e:
            print(f"[AGENTS] manifest read: {e}")

    # Marker for Hermes
    out = root / "engine" / "data" / "agents_v32_activated.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "version": "V32",
        "paper_trade": True,
        "execution_allowed": False,
        "priority": PRIORITY,
        "enabled_count": len(found),
    }, indent=2), encoding="utf-8")
    print(f"[AGENTS] marker: {out}")
    print("[AGENTS] Invariants: paper_trade=true execution_allowed=false")
    return 0

if __name__ == "__main__":
    sys.exit(main())
