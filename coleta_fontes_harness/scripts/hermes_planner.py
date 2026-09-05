#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Planner V10 — plano ordenado de tools a partir dos findings
================================================================
Prioridade: safety → syntax → venv/deps → start → zombie recycle → canary.
Nunca inclui tools que liguem execution_allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


@dataclass
class Step:
    priority: int
    tool: str
    kwargs: Dict[str, Any]
    reason: str
    finding_code: str = ""


def plan(findings: Sequence[Dict[str, Any]], incident: str = "", recipe: Sequence[str] | None = None) -> List[Step]:
    steps: List[Step] = [
        Step(0, "reinforce_safety_env", {}, "invariante paper-trade"),
    ]
    if incident in ("CAPTURE_ONLY", "HEALTHY", "CODE_DRIFT", "OPTIONAL"):
        # não reciclar nem subir processos — core não é o problema
        return steps
    codes = {str(f.get("code", "")): f for f in findings}

    for f in findings:
        if not f.get("auto_fixable") or f.get("fixed"):
            continue
        code = str(f.get("code", ""))
        if code.startswith("SYNTAX_"):
            steps.append(Step(1, "apply_syntax_fix", {"file": (f.get("detail") or {}).get("file", "")},
                              "syntax allowlisted", code))
        elif code == "VENV_MISSING":
            steps.append(Step(2, "ensure_venv", {}, "criar venv 3.10/3.11", code))
        elif code == "DEPS_MISSING":
            steps.append(Step(3, "pip_install_critical", {}, "deps críticas", code))
        elif "BRIDGE_ZOMBIE" in code or code == "PORT_8080_OFF" or code == "BRIDGE_DOWN":
            if "ZOMBIE" in code:
                steps.append(Step(4, "recycle_port", {"port": 8080}, "zombie bridge", code))
            steps.append(Step(5, "safe_start_bridge", {}, "subir bridge", code))
        elif "ENGINE_ZOMBIE" in code or code == "PORT_8765_OFF" or code == "ENGINE_DOWN":
            if "ZOMBIE" in code:
                steps.append(Step(4, "recycle_port", {"port": 8765}, "zombie engine", code))
            steps.append(Step(5, "safe_start_engine", {}, "subir engine", code))
        elif "VOICE_ZOMBIE" in code or code == "PORT_8099_OFF" or code == "VOICE_DOWN":
            if "ZOMBIE" in code:
                steps.append(Step(6, "recycle_port", {"port": 8099}, "zombie voice", code))
            steps.append(Step(7, "safe_start_voice", {}, "subir voice", code))

    # dedup by (tool, kwargs)
    seen = set()
    out: List[Step] = []
    for s in sorted(steps, key=lambda x: x.priority):
        key = (s.tool, tuple(sorted(s.kwargs.items())))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    if recipe:
        order = {name: i for i, name in enumerate(recipe)}
        head, tail = [], []
        for s in out:
            if s.priority == 0:
                head.append(s)
            else:
                tail.append(s)
        tail.sort(key=lambda s: order.get(s.tool, 100 + s.priority))
        out = head + tail
    return out
