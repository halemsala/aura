#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meta Agent — plano operacional simples (ops AURA)."""
from __future__ import annotations
import argparse, json, os, socket, time
from pathlib import Path

def port_up(p: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", p), timeout=0.3):
            return True
    except OSError:
        return False

class MetaAgent:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def state(self) -> dict:
        return {
            "timestamp": time.time(),
            "ports": {
                "bridge": port_up(8080), "engine": port_up(8765),
                "matriz": port_up(8766), "hermes": port_up(8777),
                "voice": port_up(8099), "ollama": port_up(11434),
            },
            "live": (self.root / "bridge" / "live_latest.json").exists(),
            "paper_trade": os.environ.get("PAPER_TRADE", "true"),
            "execution_allowed": os.environ.get("EXECUTION_ALLOWED", "false"),
        }

    def plan(self, objective: str) -> dict:
        st = self.state()
        steps = []
        if objective == "health":
            steps = [{"action": "anomaly_check"}, {"action": "orchestrator"}, {"action": "status"}]
        elif objective == "security_audit":
            steps = [{"action": "red_team"}, {"action": "blue_team"}, {"action": "security_guard"}]
        elif objective == "exit_demo":
            steps = [
                {"action": "prepare_bridge_token"},
                {"action": "open_desktop"},
                {"action": "note", "msg": "Browser 8766 pode continuar demo; captura = Desktop"},
            ]
        else:
            steps = [{"action": "status"}]
        return {"objective": objective, "state": st, "steps": steps}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    ap.add_argument("--objective", default="health")
    m = MetaAgent(ap.parse_args().root)
    print(json.dumps(m.plan(ap.parse_args().objective), ensure_ascii=False, indent=2))
