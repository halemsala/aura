"""Contratos inertes e fail-closed para o addon AURA Maximizer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

Decision = Literal["ADVISORY", "AGUARDA", "BLOCK"]

PAPER_TRADE = True
EXECUTION_ALLOWED = False
GLM_ADVISORY_ONLY = True


@dataclass(frozen=True)
class Capability:
    name: str
    mode: Literal["read", "plan"] = "read"
    mutating: bool = False

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 120:
            raise ValueError("capability name must be 1..120 chars")
        if self.mutating:
            raise ValueError("mutating capabilities are not allowed in this addon")


@dataclass(frozen=True)
class ConnectorRequest:
    connector: str
    operation: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.connector or not self.operation:
            raise ValueError("connector and operation are required")
        if not 0.1 <= self.timeout_seconds <= 30.0:
            raise ValueError("timeout must be between 0.1 and 30 seconds")


@dataclass(frozen=True)
class AdvisoryDecision:
    decision: Decision
    rationale: str
    confidence: float = 0.0
    source_ids: tuple[str, ...] = ()
    skill_versions: tuple[str, ...] = ()
    blocked_reason: str | None = None
    paper_trade: Literal[True] = True
    execution_allowed: Literal[False] = False
    glm_advisory_only: Literal[True] = True

    def __post_init__(self) -> None:
        if not self.rationale or len(self.rationale) > 4000:
            raise ValueError("rationale must be 1..4000 chars")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class RoutinePlan:
    routine_id: str
    description: str
    schedule: str
    steps: tuple[str, ...]
    enabled: bool = False
    execution_allowed: Literal[False] = False

    def __post_init__(self) -> None:
        if not self.routine_id or not self.steps:
            raise ValueError("routine_id and at least one step are required")
        if self.enabled:
            raise ValueError("routines must remain disabled until explicit activation")


@dataclass(frozen=True)
class AgentRun:
    agent_id: str
    decision: AdvisoryDecision
    trace_id: str
    tool_calls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("trace_id is required")
        if self.tool_calls:
            raise ValueError("tool calls are not executed by this addon")
