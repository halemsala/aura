"""Contratos AURA IA One e Hermes — paper por padrão; LIVE via policy_runtime."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.core.policy_runtime import get_system_policy

Decision = Literal["ENTRA", "AGUARDA", "NAO_ENTRA"]
FinalDecision = Literal["ENTRA", "AGUARDA", "NAO_ENTRA", "BLOCK"]


def _default_paper() -> bool:
    return bool(get_system_policy().get("paper_trade", True))


def _default_execution() -> bool:
    return bool(get_system_policy().get("execution_allowed", False))


class PolicyAwareModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_trade: bool = Field(default_factory=_default_paper)
    execution_allowed: bool = Field(default_factory=_default_execution)
    approved: bool = False
    stake_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    exposure: float = Field(default=0.0, ge=0.0, le=1.0)


# Alias legado
PaperLockedModel = PolicyAwareModel


class CornerFeatures(PolicyAwareModel):
    contract_version: Literal["aura-ai-one-features-v1"] = "aura-ai-one-features-v1"
    fixture_id: str = Field(min_length=1, max_length=128)
    minute: int = Field(ge=0, le=130)
    corner_total: int = Field(ge=0, le=1000)
    corner_delta_10m: int = Field(ge=0, le=1000)
    attack_delta_10m: int = Field(ge=-10000, le=10000)
    dangerous_delta_10m: int = Field(ge=-10000, le=10000)
    corner_rate_10m: float = Field(ge=0.0, le=100.0)
    evidence_count: int = Field(ge=0, le=1000)
    freshness_seconds: float = Field(ge=0.0, le=86_400.0)
    quality_score: float = Field(ge=0.0, le=1.0)
    source_count: int = Field(ge=0, le=100)
    # Campos estendidos (opcionais / default 0)
    shots_on_delta_10m: int = Field(default=0, ge=-10000, le=10000)
    shots_off_delta_10m: int = Field(default=0, ge=-10000, le=10000)
    possession_home: float = Field(default=0.0, ge=0.0, le=100.0)
    pressure_gauge: float = Field(default=0.0, ge=0.0, le=100.0)
    xg_home: float = Field(default=0.0, ge=0.0, le=50.0)
    xg_away: float = Field(default=0.0, ge=0.0, le=50.0)
    yellow_home: int = Field(default=0, ge=0, le=30)
    yellow_away: int = Field(default=0, ge=0, le=30)
    red_home: int = Field(default=0, ge=0, le=11)
    red_away: int = Field(default=0, ge=0, le=11)
    fouls_home: int = Field(default=0, ge=0, le=100)
    fouls_away: int = Field(default=0, ge=0, le=100)
    offsides_home: int = Field(default=0, ge=0, le=50)
    offsides_away: int = Field(default=0, ge=0, le=50)
    saves_home: int = Field(default=0, ge=0, le=50)
    saves_away: int = Field(default=0, ge=0, le=50)
    throw_ins_home: int = Field(default=0, ge=0, le=100)
    throw_ins_away: int = Field(default=0, ge=0, le=100)
    goal_kicks_home: int = Field(default=0, ge=0, le=100)
    goal_kicks_away: int = Field(default=0, ge=0, le=100)
    free_kicks_home: int = Field(default=0, ge=0, le=100)
    free_kicks_away: int = Field(default=0, ge=0, le=100)
    crosses_home: int = Field(default=0, ge=0, le=200)
    crosses_away: int = Field(default=0, ge=0, le=200)
    blocked_shots_home: int = Field(default=0, ge=0, le=100)
    blocked_shots_away: int = Field(default=0, ge=0, le=100)


class AuraAIOneProposal(PolicyAwareModel):
    contract_version: Literal["aura-ai-one-proposal-v1"] = "aura-ai-one-proposal-v1"
    fixture_id: str = Field(min_length=1, max_length=128)
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    horizon_minutes: int = Field(ge=1, le=10)
    evidence: list[str] = Field(default_factory=list, max_length=32)
    kills: list[str] = Field(default_factory=list, max_length=32)
    rationale: str = Field(default="", max_length=2000)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HermesReview(PolicyAwareModel):
    contract_version: Literal["hermes-review-v1"] = "hermes-review-v1"
    fixture_id: str = Field(min_length=1, max_length=128)
    status: Literal["PASS", "DOWNGRADE", "BLOCK"] = "PASS"
    decision: FinalDecision
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=2000)
    audit_findings: list[str] = Field(default_factory=list, max_length=32)


class AuraHermesEnvelope(PolicyAwareModel):
    contract_version: Literal["aura-hermes-envelope-v1"] = "aura-hermes-envelope-v1"
    fixture_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=64)
    proposal: AuraAIOneProposal
    review: HermesReview
    final_decision: FinalDecision
    final_confidence: float = Field(ge=0.0, le=1.0)
    audit_summary: str = Field(default="", max_length=2000)
    order: tuple[str, ...] = ("AURA_AI_ONE_QUANT", "HERMES_AUDIT")


__all__ = [
    "Decision",
    "FinalDecision",
    "PolicyAwareModel",
    "PaperLockedModel",
    "CornerFeatures",
    "AuraAIOneProposal",
    "HermesReview",
    "AuraHermesEnvelope",
]
