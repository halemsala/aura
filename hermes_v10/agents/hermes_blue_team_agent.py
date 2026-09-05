#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blue Team — responde a findings do Red Team com fixes allowlist."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class BlueTeamAgent:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def respond(self, findings: list) -> list:
        actions = []
        try:
            from correction_agent import CorrectionAgent
            agent = CorrectionAgent(str(self.root))
        except Exception as e:
            return [{"ok": False, "error": str(e)}]
        for f in findings:
            sev = f.get("severity")
            if sev == "critical" and "execution" in (f.get("evidence") or "").lower():
                r = agent.apply("set_execution_false")
                actions.append({"finding": f.get("vector"), "fix": "set_execution_false", "ok": r.success})
            if "desktop" in (f.get("target") or "") or "allowReal" in (f.get("evidence") or ""):
                r = agent.apply("fix_desktop_json")
                actions.append({"finding": f.get("vector"), "fix": "fix_desktop_json", "ok": r.success})
        return actions

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    root = ap.parse_args().root
    from hermes_red_team_agent import RedTeamAgent
    findings = RedTeamAgent(root).scan()
    acts = BlueTeamAgent(root).respond(findings)
    print(json.dumps({"findings": findings, "actions": acts}, ensure_ascii=False, indent=2))
