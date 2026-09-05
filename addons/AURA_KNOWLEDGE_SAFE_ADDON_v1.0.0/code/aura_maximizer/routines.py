"""Planejamento de rotinas sem agendamento ou execução automática."""
from __future__ import annotations

from .contracts import RoutinePlan


def build_default_routines() -> tuple[RoutinePlan, ...]:
    return (
        RoutinePlan(
            routine_id="aura.daily_health_report.v1",
            description="Consolidar saúde, drift, latência e bloqueios do AURA.",
            schedule="0 3 * * *",
            steps=("collect_health", "collect_drift", "redact", "emit_advisory_report"),
        ),
        RoutinePlan(
            routine_id="aura.knowledge_review.v1",
            description="Revisar candidatos de conhecimento antes de aprovação.",
            schedule="manual-or-approved-event",
            steps=("collect_candidates", "validate_schema", "request_human_review", "append_decision"),
        ),
        RoutinePlan(
            routine_id="aura.release_precheck.v1",
            description="Validar manifesto, hashes, exclusões e testes offline do release.",
            schedule="manual",
            steps=("scan_files", "compile_static", "test_archive", "write_report"),
        ),
    )


def plan_routine(routine_id: str) -> dict[str, object]:
    for routine in build_default_routines():
        if routine.routine_id == routine_id:
            return {"status": "PLAN_ONLY", "routine": routine, "execution_allowed": False}
    raise KeyError(routine_id)
