#!/usr/bin/env python3
"""Dependency-free smoke tests for the AURA administrator core."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aura_admin_core import (
    AuditLedger,
    AutonomyMode,
    DecisionStatus,
    GLMPlanner,
    PlanVerifier,
    PolicyGate,
    RiskLevel,
    ToolManifest,
    ToolRegistry,
)


def object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def manifest(name: str, risk: str, modes: list[str], effects: list[str], approval: bool) -> ToolManifest:
    return ToolManifest.from_dict({
        "name": name,
        "version": "1.0.0",
        "description": name,
        "risk_level": risk,
        "input_schema": object_schema({"service": {"type": "string", "enum": ["engine"]}}, ["service"]),
        "output_schema": object_schema({}, []),
        "allowed_agents": ["aura-admin"],
        "allowed_modes": modes,
        "side_effects": effects,
        "timeout_s": 10,
        "idempotency": "keyed" if effects else "idempotent",
        "rollback": "restart_previous_process" if effects else "not_applicable_read_only",
        "requires_approval": approval,
        "audit_events": ["tool_requested", "tool_completed", "tool_rejected"],
    })


def main() -> int:
    registry = ToolRegistry([
        manifest("read_health", "LOW", ["OBSERVE", "PLAN_ONLY", "DRY_RUN"], [], False),
        manifest("restart_service", "HIGH", ["SUPERVISED"], ["process_restart"], True),
    ])
    gate = PolicyGate(registry)
    assert gate.decide("read_health", {"service": "engine"}, agent="aura-admin", mode=AutonomyMode.OBSERVE).status is DecisionStatus.ALLOW
    assert gate.decide("unknown", {}, agent="aura-admin", mode=AutonomyMode.OBSERVE).status is DecisionStatus.DENY
    assert gate.decide("restart_service", {"service": "engine"}, agent="aura-admin", mode=AutonomyMode.SUPERVISED).status is DecisionStatus.REQUIRE_APPROVAL

    verifier = PlanVerifier(gate)
    plan = {
        "task_id": "task-smoke",
        "goal": "diagnosticar o Engine",
        "assumptions": [],
        "steps": [{
            "step_id": "s1", "tool": "read_health", "arguments": {"service": "engine"},
            "reason": "coletar evidência", "risk_level": "LOW", "requires_approval": False,
            "expected": {"status": "PASS_RUNTIME"}, "depends_on": [],
        }],
        "stop_conditions": ["parar se a evidência estiver ausente"],
        "evidence_requirements": ["health_payload"],
    }
    result = verifier.verify(plan, agent="aura-admin", mode=AutonomyMode.PLAN_ONLY)
    assert result.valid
    unsafe = dict(plan)
    unsafe["goal"] = "enviar ordem real"
    assert not verifier.verify(unsafe, agent="aura-admin", mode=AutonomyMode.PLAN_ONLY).valid

    class FakeAdapter:
        def complete(self, *, messages, response_schema, timeout_s):
            request = json.loads(messages[1]["content"])
            return {**plan, "task_id": request["task_id"], "goal": request["goal"]}

    planner = GLMPlanner(FakeAdapter(), verifier)
    assert planner.plan(task_id="task-planner", goal="diagnosticar o Engine", context={"token": "redact"}, agent="aura-admin", mode=AutonomyMode.PLAN_ONLY).status == "VALID"

    with tempfile.TemporaryDirectory() as directory:
        ledger = AuditLedger(Path(directory) / "aura_quant_x.db")
        event_id = ledger.append_event(trace_id="trace-smoke", task_id="task-smoke", event_type="plan_requested", actor="aura-admin", status="RECEIVED", payload={"api_key": "secret"}, idempotency_key="event-1")
        assert ledger.append_event(trace_id="trace-smoke", task_id="task-smoke", event_type="plan_requested", actor="aura-admin", status="RECEIVED", payload={}, idempotency_key="event-1") == event_id
        ledger.remember_episode(task_id="task-smoke", episode_type="plan", summary="diagnóstico", status="PLANNED", source_event_id=event_id, metadata={"password": "secret"}, memory_key="episode-1")
        assert ledger.trace_events("trace-smoke")[0]["payload"]["api_key"] == "[REDACTED]"
        assert ledger.recent_episodes(task_id="task-smoke")[0]["metadata"]["password"] == "[REDACTED]"
        assert ledger.health()["status"] == "READY"
    print("aura_admin_core_smoke_pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
