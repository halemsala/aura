"""Firewall offline para saídas advisory de LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FirewallStatus(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class LLMAdvisoryOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["aura-llm-advisory-v1"] = "aura-llm-advisory-v1"
    decision: Literal["ENTRA", "AGUARDA", "NAO_ENTRA"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=32)
    paper_trade: Literal[True] = True
    execution_allowed: Literal[False] = False
    approved: Literal[False] = False
    stake_pct: Literal[0.0] = 0.0
    exposure: Literal[0.0] = 0.0


@dataclass(frozen=True)
class FirewallResult:
    status: FirewallStatus
    output: LLMAdvisoryOutput | None
    reason: str


def parse_advisory_output(raw: str | Mapping[str, Any]) -> FirewallResult:
    """Valida uma saída externa sem executar, corrigir ou completar JSON."""
    try:
        if isinstance(raw, str):
            if not raw.strip():
                raise ValueError("empty_llm_output")
            data = json.loads(raw)
        elif isinstance(raw, Mapping):
            data = dict(raw)
        else:
            raise TypeError("llm_output_must_be_json_or_mapping")
        output = LLMAdvisoryOutput.model_validate(data)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
        return FirewallResult(
            status=FirewallStatus.BLOCK,
            output=None,
            reason=f"invalid_advisory_output:{type(exc).__name__}",
        )
    return FirewallResult(status=FirewallStatus.ALLOW, output=output, reason="validated")


__all__ = ["FirewallResult", "FirewallStatus", "LLMAdvisoryOutput", "parse_advisory_output"]
