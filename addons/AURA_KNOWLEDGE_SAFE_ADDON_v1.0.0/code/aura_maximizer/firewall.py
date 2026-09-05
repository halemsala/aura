"""Firewall local para saídas de LLM; não cria clientes nem executa ferramentas."""
from __future__ import annotations

import json
from typing import Any

from .contracts import AdvisoryDecision

_ALLOWED = {"decision", "rationale", "confidence", "source_ids", "skill_versions"}
_DECISIONS = {"ADVISORY", "AGUARDA", "BLOCK"}


def _blocked(reason: str) -> AdvisoryDecision:
    return AdvisoryDecision(
        decision="BLOCK",
        rationale="Saída rejeitada pelo firewall LLM.",
        confidence=0.0,
        blocked_reason=reason[:160],
    )


def parse_llm_output(raw: Any) -> AdvisoryDecision:
    """Converte somente JSON-objeto estrito em decisão advisory.

    Texto livre, JSON inválido, campos extras, confidence inválida e decisões
    desconhecidas retornam BLOCK. Nenhum conteúdo é interpretado como comando.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _blocked("invalid_utf8")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return _blocked("invalid_json")
    if not isinstance(raw, dict):
        return _blocked("object_required")
    if set(raw) - _ALLOWED:
        return _blocked("extra_field")
    if not {"decision", "rationale", "confidence"}.issubset(raw):
        return _blocked("missing_field")
    if raw["decision"] not in _DECISIONS:
        return _blocked("unknown_decision")
    if not isinstance(raw["rationale"], str) or not raw["rationale"].strip():
        return _blocked("invalid_rationale")
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
    return AdvisoryDecision(
        decision=raw["decision"],
        rationale=raw["rationale"][:4000],
        confidence=float(confidence),
        source_ids=tuple(source_ids[:16]),
        skill_versions=tuple(skill_versions[:16]),
    )
