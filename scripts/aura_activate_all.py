#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AURA QUANT-X — Ativar TODAS as ferramentas + interface (paper trade only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "agents" / "activation_manifest.json"
EN = ROOT / "agents" / "ENABLED"
INDEX = ROOT / "agents" / "activation_index.json"
UI_MARKERS = [
    ROOT / "agents" / "ENABLED" / "ui_central_nova.enabled",
    ROOT / "agents" / "ENABLED" / "central_nova.enabled",
    ROOT / "agents" / "ENABLED" / "index.html.enabled",
]

EXTRA_MODULES = [
    ("engine:browser_agent.py", "engine/agents/browser_agent.py", "4.0.0"),
    ("engine:cross_site_analyst.py", "engine/agents/cross_site_analyst.py", "2.0.0"),
    ("engine:odds_quality_monitor.py", "engine/agents/odds_quality_monitor.py", "1.0.0"),
    ("engine:cache_integration.py", "engine/core/cache_integration.py", "1.0.0"),
]


def main() -> int:
    EN.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.exists():
        print(json.dumps({"ok": False, "error": "manifest missing"}))
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    agents = data.setdefault("agents", {})

    for aid, path, ver in EXTRA_MODULES:
        agents[aid] = {
            "path": path,
            "status": "enabled",
            "layer": "engine" if "/agents/" in path else "core",
            "paper_trade": True,
            "version": ver,
            "implementation_state": "runnable",
        }

    markers = 0
    for aid, spec in list(agents.items()):
        if not isinstance(spec, dict):
            continue
        spec["status"] = "enabled"
        spec["paper_trade"] = True
        path = str(spec.get("path") or "")
        base = Path(path).name if path else aid.split(":")[-1]
        body = (
            f"enabled=true\nagent_id={aid}\npath={path}\n"
            f"status=enabled\npaper_trade=true\n"
        )
        for name in {
            f"{base}.enabled",
            aid.replace(":", "_").replace("/", "_") + ".enabled",
        }:
            (EN / name).write_text(body, encoding="utf-8")
            markers += 1

    # interface markers
    for p in UI_MARKERS:
        p.write_text(
            "enabled=true\ncomponent=interface\nstatus=enabled\n",
            encoding="utf-8",
        )
        markers += 1

    data["agents"] = agents
    data["paper_trade"] = True
    data["execution_allowed"] = False
    data["version"] = "12.7.0-V25O-ALL-ACTIVATED"
    data["agent_count"] = len(agents)
    data["activated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    enabled_files = len(list(EN.glob("*.enabled")))
    index = {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "declared": len(agents),
        "markers_written": markers,
        "enabled_files": enabled_files,
        "interface": "enabled",
        "activated_at": data["activated_at"],
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
