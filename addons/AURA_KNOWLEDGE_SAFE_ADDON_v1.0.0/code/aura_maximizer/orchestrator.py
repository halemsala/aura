"""Pipeline cooperativo AURA IA + Hermes, totalmente advisory e offline."""
from __future__ import annotations
from dataclasses import dataclass, is_dataclass, asdict
from enum import Enum
from typing import Any, Callable, Mapping
import hashlib
import json


class Decision(str, Enum):
    ADVISORY = "ADVISORY"
    AGUARDA = "AGUARDA"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class Evidence:
    source: str
    value: Any
    freshness: str = "unknown"
    confidence: float = 0.0


@dataclass(frozen=True)
class AURAProposal:
    task_id: str
    summary: str
    findings: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    suggested_next_step: str | None = None


@dataclass(frozen=True)
class HermesReview:
    task_id: str
    supported: bool
    concerns: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    confidence: float
    decision: Decision


@dataclass(frozen=True)
class JointResult:
    task_id: str
    aura: AURAProposal
    hermes: HermesReview
    decision: Decision
    audit_hash: str
    cycles: int
    execution_allowed: bool = False


class AURAHermesPipeline:
    """Coordena duas passagens sem executar ferramentas ou alterar o host."""

    def __init__(self, max_cycles: int = 3, paper_trade: bool = True):
        if not 1 <= max_cycles <= 3:
            raise ValueError("max_cycles deve estar entre 1 e 3")
        self.max_cycles = max_cycles
        self.paper_trade = paper_trade

    def run(
        self,
        task_id: str,
        snapshot: Mapping[str, Any],
        aura_fn: Callable[[Mapping[str, Any]], AURAProposal],
        hermes_fn: Callable[[AURAProposal], HermesReview],
    ) -> JointResult:
        if not task_id or not isinstance(snapshot, Mapping):
            raise ValueError("task_id e snapshot são obrigatórios")
        proposal = aura_fn(snapshot)
        if proposal.task_id != task_id:
            raise ValueError("AURA IA retornou task_id divergente")
        review = hermes_fn(proposal)
        if review.task_id != task_id:
            raise ValueError("Hermes retornou task_id divergente")
        decision = self._decide(proposal, review)
        payload = {
            "task_id": task_id,
            "aura": self._jsonable(proposal),
            "hermes": self._jsonable(review),
            "decision": decision.value,
            "cycles": 1,
            "paper_trade": self.paper_trade,
            "execution_allowed": False,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return JointResult(task_id, proposal, review, decision, digest, 1, False)

    @staticmethod
    def _decide(proposal: AURAProposal, review: HermesReview) -> Decision:
        if not review.supported or review.decision == Decision.BLOCK:
            return Decision.BLOCK
        if review.missing_evidence or review.confidence < 0.70 or not proposal.evidence:
            return Decision.AGUARDA
        return Decision.ADVISORY

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {k: AURAHermesPipeline._jsonable(v) for k, v in asdict(value).items()}
        if isinstance(value, tuple):
            return [AURAHermesPipeline._jsonable(v) for v in value]
        if isinstance(value, dict):
            return {k: AURAHermesPipeline._jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [AURAHermesPipeline._jsonable(v) for v in value]
        return value
