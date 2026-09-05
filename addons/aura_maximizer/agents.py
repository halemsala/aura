"""Agentes advisory determinísticos; o host fornece dados e funções puras."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Callable

from .contracts import AdvisoryDecision, AgentRun
from .firewall import parse_llm_output


def stable_trace_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def aura_one_proposal(snapshot: Mapping[str, Any]) -> AdvisoryDecision:
    """Produz uma proposta conservadora sem buscar dados nem chamar modelos."""
    required = ("fixture_id", "minute", "sources")
    missing = [key for key in required if key not in snapshot]
    if missing:
        return AdvisoryDecision("BLOCK", "Snapshot incompleto.", blocked_reason="missing:" + ",".join(missing))
    sources = snapshot.get("sources")
    if not isinstance(sources, (list, tuple)) or not sources:
        return AdvisoryDecision("BLOCK", "Nenhuma fonte verificável disponível.", blocked_reason="no_sources")
    return AdvisoryDecision(
        "AGUARDA",
        "Proposta advisory aguardando análise de evidência e política do host.",
        confidence=0.25,
        source_ids=tuple(str(x) for x in sources[:8]),
        skill_versions=("aura-ingestion.v1",),
    )


def hermes_review(proposal: AdvisoryDecision, snapshot: Mapping[str, Any]) -> AdvisoryDecision:
    """Rebaixa ou bloqueia propostas sem proveniência e qualidade explícitas."""
    if proposal.decision == "BLOCK":
        return proposal
    quality = snapshot.get("data_quality", "UNKNOWN")
    if quality not in {"VALID", "ACCEPT", "GOOD"}:
        return AdvisoryDecision("BLOCK", "Hermes bloqueou por qualidade de dados não comprovada.", blocked_reason="quality_gate")
    if not proposal.source_ids:
        return AdvisoryDecision("BLOCK", "Hermes bloqueou por ausência de fontes.", blocked_reason="provenance_gate")
    return AdvisoryDecision(
        "ADVISORY",
        "Hermes aceitou somente a camada advisory; nenhuma ação foi executada.",
        confidence=min(proposal.confidence, 0.8),
        source_ids=proposal.source_ids,
        skill_versions=proposal.skill_versions + ("aura-hermes-review.v1",),
    )


def run_advisory(snapshot: Mapping[str, Any]) -> AgentRun:
    proposal = aura_one_proposal(snapshot)
    reviewed = hermes_review(proposal, snapshot)
    return AgentRun(agent_id="aura.one.hermes.v1", decision=reviewed, trace_id=stable_trace_id(snapshot))


def review_external_llm(raw: Any, snapshot: Mapping[str, Any]) -> AgentRun:
    parsed = parse_llm_output(raw)
    reviewed = hermes_review(parsed, snapshot)
    return AgentRun(agent_id="aura.external.llm.firewall.v1", decision=reviewed, trace_id=stable_trace_id(snapshot))
