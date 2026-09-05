#!/usr/bin/env python3
"""Benchmark deterministic AURA administrator stages on a temporary database."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aura_admin_core import AuditLedger, AutonomyMode, PlanVerifier, PolicyGate, RiskAnalyzer, RiskLevel, ToolManifest, ToolRegistry, sanitize


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {"avg_ms": statistics.fmean(values), "p50_ms": percentile(values, 0.50), "p95_ms": percentile(values, 0.95), "p99_ms": percentile(values, 0.99), "max_ms": max(values)}


def run(iterations: int) -> dict[str, object]:
    if not 1 <= iterations <= 10_000:
        raise ValueError("iterations must be between 1 and 10000")
    read = ToolManifest(name="read_health", version="1.0.0", description="read engine health", risk_level=RiskLevel.LOW, input_schema={"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"], "additionalProperties": False}, output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}, allowed_agents=("aura-admin",), allowed_modes=(AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DRY_RUN, AutonomyMode.SUPERVISED), side_effects=(), timeout_s=5.0, idempotency="idempotent", rollback="none", requires_approval=False, audit_events=("read_health",))
    registry = ToolRegistry([read])
    gate = PolicyGate(registry)
    verifier = PlanVerifier(gate)
    risk = RiskAnalyzer()
    plan = {"task_id": "benchmark", "goal": "diagnosticar engine", "steps": [{"step_id": "s1", "tool": "read_health", "arguments": {"service": "engine"}, "reason": "health", "risk_level": "LOW", "requires_approval": False, "expected": {}, "depends_on": []}], "stop_conditions": ["parar no erro"], "evidence_requirements": ["health_payload"]}
    risk_samples: list[float] = []
    sanitize_samples: list[float] = []
    plan_samples: list[float] = []
    ledger_samples: list[float] = []
    with tempfile.TemporaryDirectory() as directory:
        ledger = AuditLedger(Path(directory) / "aura_quant_x.db")
        for index in range(iterations):
            started = time.perf_counter()
            risk.analyze("diagnostique o Engine", direction="prompt", allowed_scope=["engine"])
            risk_samples.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            sanitize({"service": "engine", "context": ["health", "paper"]})
            sanitize_samples.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            verification = verifier.verify(plan, agent="aura-admin", mode=AutonomyMode.PLAN_ONLY)
            if not verification.valid:
                raise RuntimeError(f"benchmark plan rejected: {verification.errors}")
            plan_samples.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            ledger.append_event(trace_id=f"trace-{index}", task_id="benchmark", event_type="benchmark", actor="benchmark", status="PASS", payload={"index": index}, idempotency_key=f"benchmark-{index}")
            ledger_samples.append((time.perf_counter() - started) * 1000)
    return {"iterations": iterations, "stages": {"risk_analysis": summarize(risk_samples), "context_sanitization": summarize(sanitize_samples), "plan_verification": summarize(plan_samples), "ledger_append": summarize(ledger_samples)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run(args.iterations), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
