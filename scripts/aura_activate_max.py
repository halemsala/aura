from __future__ import annotations


# V23: forca paper-trade em todos os agentes do manifesto
try:
    from engine.core.security import AuraSecurityPolicy
except Exception:
    try:
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
        from engine.core.security import AuraSecurityPolicy
    except Exception:
        AuraSecurityPolicy = None

def _force_paper_trade_manifest(data: dict) -> dict:
    if AuraSecurityPolicy is None or not isinstance(data, dict):
        return data
    agents = data.get("agents") or {}
    for k, cfg in list(agents.items()):
        if isinstance(cfg, dict):
            agents[k] = AuraSecurityPolicy.validate_manifest_agent(cfg)
    data["agents"] = agents
    data["paper_trade"] = True
    data["execution_allowed"] = False
    return data

#!/usr/bin/env python3
"""Ativa o máximo possível offline: manifest + ENABLED + index. PAPER TRADE ONLY."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "agents" / "activation_manifest.json"
EN = ROOT / "agents" / "ENABLED"
INDEX = ROOT / "agents" / "activation_index.json"

def main() -> int:
    EN.mkdir(parents=True, exist_ok=True)
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    agents = data.get("agents") or {}
    markers = 0
    for aid, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        spec["status"] = "enabled"
        spec["paper_trade"] = True
        path = str(spec.get("path") or "")
        base = Path(path).name if path else aid.split(":")[-1]
        body = f"enabled=true\nagent_id={aid}\npath={path}\nstatus=enabled\npaper_trade=true\n"
        for name in {f"{base}.enabled", aid.replace(":", "_").replace("/", "_") + ".enabled"}:
            (EN / name).write_text(body, encoding="utf-8")
            markers += 1
    data["agents"] = agents
    data["version"] = "12.7.0-V22-P15-MAX-ACTIVATED"
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    index = {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "declared": len(agents),
        "markers_written": markers,
        "enabled_files": len(list(EN.glob("*.enabled"))),
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
