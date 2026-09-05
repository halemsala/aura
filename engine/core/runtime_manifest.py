"""Manifesto canonico do runtime — paper por padrao; LIVE so com unlock completo."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.core.policy_runtime import assert_safety_invariants, get_system_policy


class RuntimeManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Literal["aura-runtime-manifest-v1"] = "aura-runtime-manifest-v1"
    profile_id: str = Field(default="aura-corners-pro-v1", min_length=1, max_length=128)
    domain: Literal["sports_corner_analysis"] = "sports_corner_analysis"
    paper_trade: bool = True
    execution_allowed: bool = False
    approved: bool = False
    stake_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    exposure: float = Field(default=0.0, ge=0.0, le=1.0)
    advisory_only: bool = True
    network_default: bool = False
    tool_authority: bool = False
    financial_operations_enabled: bool = False
    refresh_target_seconds: int = Field(default=60, ge=1, le=3600)
    max_staleness_seconds: int = Field(default=180, ge=1, le=86_400)
    horizons_minutes: tuple[int, ...] = (1, 3, 5, 10)
    hermes_primary: bool = True
    glm_enabled: bool = False

    @model_validator(mode="after")
    def _reject_paper_and_live(self) -> "RuntimeManifest":
        # FIX V26.5: proibir construction com paper_trade=True e execution_allowed=True
        if self.execution_allowed and self.paper_trade:
            raise ValueError(
                "RUNTIME_MANIFEST_CONFLICT_PAPER_AND_EXEC: "
                "execution_allowed=True e incompatível com paper_trade=True"
            )
        if self.execution_allowed and self.advisory_only:
            raise ValueError(
                "RUNTIME_MANIFEST_CONFLICT_ADVISORY_AND_EXEC: "
                "execution_allowed=True exige advisory_only=False"
            )
        return self

    @classmethod
    def from_policy(cls) -> "RuntimeManifest":
        policy = get_system_policy()
        paper = bool(policy["paper_trade"])
        execution = bool(policy["execution_allowed"]) and not paper
        return cls(
            paper_trade=paper,
            execution_allowed=execution,
            approved=execution,
            stake_pct=0.0 if paper else 0.0,
            exposure=0.0,
            advisory_only=not execution,
            financial_operations_enabled=execution,
            hermes_primary=bool(policy.get("hermes_primary", True)),
            glm_enabled=bool(policy.get("glm_enabled", False)),
        )

    def assert_policy(self) -> None:
        assert_safety_invariants()
        if self.execution_allowed and self.paper_trade:
            raise RuntimeError("RUNTIME_MANIFEST_CONFLICT_PAPER_AND_EXEC")
        if self.execution_allowed and not get_system_policy().get("unlock_active"):
            raise RuntimeError("RUNTIME_MANIFEST_LIVE_WITHOUT_UNLOCK")


__all__ = ["RuntimeManifest"]
