"""Adapters advisory-only da AURA IA One e do Hermes.

Nenhum adapter deste módulo chama rede ou executa ferramentas. Um provider pode
ser injetado explicitamente por código de integração, mas sua saída é validada
pelos contratos estritos e uma falha sempre cai em AGUARDA/BLOCK.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .contracts import AuraAIOneProposal, CornerFeatures, HermesReview


class ProposalProvider(Protocol):
    def __call__(self, features: CornerFeatures) -> Mapping[str, Any] | AuraAIOneProposal: ...


class ReviewProvider(Protocol):
    def __call__(self, proposal: AuraAIOneProposal, features: CornerFeatures) -> Mapping[str, Any] | HermesReview: ...


def _fallback_proposal(features: CornerFeatures, *, reason: str | None = None) -> AuraAIOneProposal:
    evidence = [
        f"corner_delta_10m={features.corner_delta_10m}",
        f"attack_delta_10m={features.attack_delta_10m}",
        f"dangerous_delta_10m={features.dangerous_delta_10m}",
        f"quality_score={features.quality_score:.2f}",
        f"freshness_seconds={features.freshness_seconds:.1f}",
    ]
    if reason:
        evidence.append(reason)
    stale = features.freshness_seconds > 180.0
    enough_signal = (
        features.quality_score >= 0.70
        and not stale
        and features.evidence_count >= 2
        and features.corner_delta_10m >= 2
        and (features.attack_delta_10m >= 4 or features.dangerous_delta_10m >= 3)
    )
    decision = "ENTRA" if enough_signal else "AGUARDA"
    confidence = 0.78 if enough_signal else 0.38
    if features.quality_score < 0.70 or stale:
        confidence = min(confidence, 0.20)
    kills: list[str] = []
    if stale:
        kills.append("evidence_stale")
    if features.quality_score < 0.70:
        kills.append("quality_below_gate")
    if features.evidence_count < 2:
        kills.append("insufficient_evidence")
    return AuraAIOneProposal(
        fixture_id=features.fixture_id,
        decision=decision,
        confidence=confidence,
        horizon_minutes=5,
        evidence=evidence,
        kills=kills,
        rationale=(
            "Sinal quantitativo compatível com pressão e ritmo de escanteios."
            if enough_signal
            else "Evidência insuficiente para propor ENTRA; aguardar atualização."
        ),
    )


class AuraAIOneAdapter:
    """Primeira camada quantitativa, sem autoridade de execução."""

    def __init__(self, provider: ProposalProvider | None = None) -> None:
        self.provider = provider

    def propose(self, features: CornerFeatures) -> AuraAIOneProposal:
        if self.provider is None:
            return _fallback_proposal(features)
        try:
            raw = self.provider(features)
            proposal = raw if isinstance(raw, AuraAIOneProposal) else AuraAIOneProposal.model_validate(raw)
            if proposal.fixture_id != features.fixture_id:
                raise ValueError("provider fixture_id mismatch")
            return proposal
        except Exception:
            return _fallback_proposal(features, reason="provider_output_invalid")


class HermesAuditAdapter:
    """Segunda camada auditora; nunca eleva a confiança sem evidência."""

    def __init__(self, provider: ReviewProvider | None = None) -> None:
        self.provider = provider

    def review(self, proposal: AuraAIOneProposal, features: CornerFeatures) -> HermesReview:
        if self.provider is not None:
            try:
                raw = self.provider(proposal, features)
                review = raw if isinstance(raw, HermesReview) else HermesReview.model_validate(raw)
                if review.fixture_id != proposal.fixture_id:
                    raise ValueError("provider fixture_id mismatch")
                if review.confidence > proposal.confidence:
                    return HermesReview(
                        fixture_id=proposal.fixture_id,
                        status="DOWNGRADE",
                        decision="AGUARDA",
                        confidence=proposal.confidence,
                        rationale="Hermes rejeitou aumento de confiança sem evidência adicional.",
                        audit_findings=["confidence_increase_without_evidence"],
                    )
                return review
            except Exception:
                return HermesReview(
                    fixture_id=proposal.fixture_id,
                    status="BLOCK",
                    decision="BLOCK",
                    confidence=0.0,
                    rationale="Saída do auditor/provider inválida; bloqueio fail-closed.",
                    audit_findings=["provider_output_invalid"],
                )

        findings: list[str] = []
        if features.freshness_seconds > 180.0:
            findings.append("evidence_stale")
        if features.quality_score < 0.70:
            findings.append("quality_below_gate")
        if features.evidence_count < 2:
            findings.append("insufficient_evidence")
        if findings:
            return HermesReview(
                fixture_id=proposal.fixture_id,
                status="BLOCK" if "evidence_stale" in findings else "DOWNGRADE",
                decision="BLOCK" if "evidence_stale" in findings else "AGUARDA",
                confidence=0.0 if "evidence_stale" in findings else min(proposal.confidence, 0.20),
                rationale="Hermes encontrou evidência insuficiente ou stale.",
                audit_findings=findings,
            )

        decision = proposal.decision
        confidence = min(proposal.confidence, 0.90)
        if decision == "ENTRA" and len(proposal.evidence) < 2:
            decision = "AGUARDA"
            confidence = min(confidence, 0.20)
            findings.append("proposal_evidence_too_short")
        return HermesReview(
            fixture_id=proposal.fixture_id,
            status="DOWNGRADE" if findings else "PASS",
            decision=decision,
            confidence=confidence,
            rationale="Hermes confirmou coerência da proposta dentro do escopo advisory.",
            audit_findings=findings or ["paper_only_advisory_confirmed"],
        )


__all__ = ["AuraAIOneAdapter", "HermesAuditAdapter", "ProposalProvider", "ReviewProvider"]
