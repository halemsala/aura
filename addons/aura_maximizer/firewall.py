"""Firewall local com extração de markdown e sanitização avançada."""
from __future__ import annotations

import json
import re
from typing import Any

from .contracts import AdvisoryDecision, DryRunAction

_ALLOWED = {
    "decision",
    "rationale",
    "confidence",
    "source_ids",
    "skill_versions",
    "proposed_actions",
    "blocked_reason",
}
_DECISIONS = {"ADVISORY", "AGUARDA", "BLOCK"}
_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|system prompt|rm -rf|exec\(|eval\(|__import__|subprocess)",
    re.IGNORECASE,
)


def _blocked(reason: str) -> AdvisoryDecision:
    return AdvisoryDecision(
        decision="BLOCK",
        rationale="Saída rejeitada pelo firewall LLM.",
        confidence=0.0,
        blocked_reason=reason[:160],
    )


def _extract_json(raw_str: str) -> Any:
    """Extrai JSON de string pura ou bloco markdown ```json ... ```."""
    raw_str = raw_str.strip()
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_str, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    # fallback: first {...} span
    brace = re.search(r"\{.*\}", raw_str, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            return None
    return None


def parse_llm_output(raw: Any) -> AdvisoryDecision:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _blocked("invalid_utf8")

    if isinstance(raw, str):
        parsed = _extract_json(raw)
        if parsed is None:
            return _blocked("invalid_json_or_markdown_malformed")
        raw = parsed

    if not isinstance(raw, dict):
        return _blocked("object_required")

    extra = set(raw) - _ALLOWED
    if extra:
        return _blocked("extra_field:" + ",".join(sorted(extra)[:4]))

    if not {"decision", "rationale", "confidence"}.issubset(raw):
        return _blocked("missing_field")

    if raw["decision"] not in _DECISIONS:
        return _blocked("unknown_decision")

    rationale = raw["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        return _blocked("invalid_rationale")
    if _INJECTION_PATTERNS.search(rationale):
        return _blocked("prompt_injection_detected")

    confidence = raw["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return _blocked("invalid_confidence")
    if not 0.0 <= float(confidence) <= 1.0:
        return _blocked("confidence_out_of_range")

    source_ids = raw.get("source_ids", ())
    skill_versions = raw.get("skill_versions", ())
    if not isinstance(source_ids, (list, tuple)) or not all(isinstance(x, str) for x in source_ids):
        return _blocked("invalid_source_ids")
    if not isinstance(skill_versions, (list, tuple)) or not all(isinstance(x, str) for x in skill_versions):
        return _blocked("invalid_skill_versions")

    actions: list[DryRunAction] = []
    for act in raw.get("proposed_actions", []) or []:
        if isinstance(act, dict) and "action" in act and "parameters" in act:
            params = act["parameters"]
            if not isinstance(params, dict):
                return _blocked("invalid_proposed_action_schema")
            actions.append(
                DryRunAction(
                    action=str(act["action"])[:120],
                    parameters=dict(params),
                    simulated_result=str(act.get("simulated_result", "DRY_RUN_SUCCESS"))[:200],
                )
            )
        else:
            return _blocked("invalid_proposed_action_schema")

    return AdvisoryDecision(
        decision=raw["decision"],
        rationale=rationale[:4000],
        confidence=float(confidence),
        source_ids=tuple(source_ids[:16]),
        skill_versions=tuple(skill_versions[:16]),
        proposed_actions=tuple(actions),
        blocked_reason=(str(raw["blocked_reason"])[:160] if raw.get("blocked_reason") else None),
    )
