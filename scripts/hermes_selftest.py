#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Self-Test V10 — integridade + episodes + control plane."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    here = Path(__file__).resolve().parent
    required = [
        "hermes_tools.py",
        "hermes_swarm.py",
        "hermes_knowledge.py",
        "hermes_state_machine.py",
        "hermes_autonomous_os.py",
        "hermes_control_panel.py",
        "hermes_sensors.py",
        "hermes_memory.py",
        "hermes_policy.py",
        "hermes_postmortem.py",
        "hermes_auditor.py",
        "hermes_planner.py",
        "hermes_telemetry.py",
        "hermes_incident.py",
        "hermes_rag.py",
        "hermes_episodes.py",
        "hermes_control_plane.py",
        "hermes_evidence.py",
        "hermes_skills.py",
    ]
    ok = True
    print("=== HERMES V10 SELF-TEST ===")
    for fname in required:
        p = here / fname
        if not p.exists():
            print(f"[FAIL] ausente: {fname}")
            ok = False
            continue
        try:
            ast.parse(p.read_text(encoding="utf-8"))
            print(f"[OK]   syntax {fname}")
        except SyntaxError as e:
            print(f"[FAIL] syntax {fname}: {e}")
            ok = False

    try:
        tools = _load("hermes_tools", here / "hermes_tools.py")
        reg = tools.ToolRegistry(Path.cwd())
        names = reg.list_tools()
        for need in ("health_score", "safe_start_engine", "safe_start_voice",
                     "canary_trader_chat", "acquire_lock", "ensure_venv",
                     "wait_port", "recycle_port", "deep_diagnostic"):
            assert need in names, need
        print(f"[OK]   ToolRegistry n={len(names)}")
    except Exception as e:
        print(f"[FAIL] tools: {e}")
        ok = False

    try:
        kb = _load("hermes_knowledge", here / "hermes_knowledge.py")
        idx = kb.KnowledgeIndex()
        hits = idx.query("porta bridge engine off captura live_latest stale grounding view")
        assert len(hits) >= 1
        print(f"[OK]   KnowledgeIndex hits={len(hits)}")
    except Exception as e:
        print(f"[FAIL] knowledge: {e}")
        ok = False

    try:
        sm = _load("hermes_state_machine", here / "hermes_state_machine.py")
        st = sm.AgentState(root=".", cycle=1, status="CRITICAL", consecutive_critical=4)
        machine = sm.StateMachine()
        machine.register(sm.Node.DETECT, lambda s: s)
        out = machine.run_once(st)
        assert "ROUTE" in out.history
        assert out.circuit_open is True
        print("[OK]   StateMachine circuit breaker")
    except Exception as e:
        print(f"[FAIL] state_machine: {e}")
        ok = False

    try:
        sw = _load("hermes_swarm", here / "hermes_swarm.py")
        board = sw.Blackboard(root=".", cycle=1)
        sw.SwarmOrchestrator(board).run()
        assert len(board.messages) >= 6
        print(f"[OK]   Swarm messages={len(board.messages)}")
    except Exception as e:
        print(f"[FAIL] swarm: {e}")
        ok = False

    try:
        pol = _load("hermes_policy", here / "hermes_policy.py")
        snap = pol.PolicyGuard(Path.cwd()).enforce_env()
        assert snap.ok()
        print("[OK]   PolicyGuard")
    except Exception as e:
        print(f"[FAIL] policy: {e}")
        ok = False

    try:
        aud = _load("hermes_auditor", here / "hermes_auditor.py")
        hits = aud.audit_tree(Path.cwd())
        assert hits
        print(f"[OK]   Auditor hits={len(hits)}")
    except Exception as e:
        print(f"[FAIL] auditor: {e}")
        ok = False

    try:
        pl = _load("hermes_planner", here / "hermes_planner.py")
        steps = pl.plan([
            {"code": "VENV_MISSING", "auto_fixable": True, "fixed": False},
            {"code": "ENGINE_DOWN", "auto_fixable": True, "fixed": False},
        ], incident="CORE_DOWN")
        names = [s.tool for s in steps]
        assert "ensure_venv" in names and "safe_start_engine" in names
        cap = pl.plan([
            {"code": "LIVE_STALE", "auto_fixable": True, "fixed": False},
            {"code": "ENGINE_DOWN", "auto_fixable": True, "fixed": False},
        ], incident="CAPTURE_ONLY")
        assert [s.tool for s in cap] == ["reinforce_safety_env"]
        print(f"[OK]   Planner core={len(steps)} capture={len(cap)}")
    except Exception as e:
        print(f"[FAIL] planner: {e}")
        ok = False


    try:
        inc = _load("hermes_incident", here / "hermes_incident.py")
        cls, _ = inc.classify([
            {"code": "LIVE_STALE", "severity": "HIGH", "fixed": False},
            {"code": "COMPILE_OK_server.py", "severity": "OK", "fixed": False},
        ])
        assert cls == "CAPTURE_ONLY"
        print("[OK]   Incident CAPTURE_ONLY")
    except Exception as e:
        print(f"[FAIL] incident: {e}")
        ok = False

    try:
        ep = _load("hermes_episodes", here / "hermes_episodes.py")
        mem = ep.EpisodeMemory(Path.cwd())
        mem.remember_success("CORE_DOWN", ["safe_start_engine", "safe_start_bridge"], 80)
        assert mem.recipe("CORE_DOWN")[0] == "safe_start_engine"
        print("[OK]   EpisodeMemory")
    except Exception as e:
        print(f"[FAIL] episodes: {e}")
        ok = False

    try:
        sk = _load("hermes_skills", here / "hermes_skills.py")
        packs = sk.load_skills(here.parents[0])
        assert any(p.id == "aura-ops-supervisor" and p.enabled for p in packs)
        print(f"[OK]   Skills enabled={sum(1 for p in packs if p.enabled)}")
    except Exception as e:
        print(f"[FAIL] skills: {e}")
        ok = False

    try:
        sen = _load("hermes_sensors", here / "hermes_sensors.py")
        findings = sen.detect_all(Path.cwd())
        assert isinstance(findings, list)
        print(f"[OK]   Sensors findings={len(findings)}")
    except Exception as e:
        print(f"[FAIL] sensors: {e}")
        ok = False

    print("=== RESULTADO:", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
