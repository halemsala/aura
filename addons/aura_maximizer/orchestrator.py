"""Pipeline cooperativo AURA IA + Hermes: Ralph Loop, Policy, Sandbox, ToT."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .policies import PolicyEngine
from .sandbox import ContextEngine, VirtualSandbox


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
    proposed_actions: tuple = ()
    cycle: int = 1


@dataclass(frozen=True)
class HermesReview:
    task_id: str
    supported: bool
    concerns: tuple[str, ...]
    missing_evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    decision: Decision = Decision.AGUARDA


@dataclass(frozen=True)
class JointResult:
    task_id: str
    final_proposal: AURAProposal | None
    final_review: HermesReview | None
    decision: Decision
    audit_hash: str
    cycles_executed: int
    audit_trail: tuple[str, ...] = ()
    execution_allowed: bool = False
    # aliases for older callers
    proposal: AURAProposal | None = None
    review: HermesReview | None = None

    def __post_init__(self) -> None:
        # keep proposal/review mirrors if only final_* set
        object.__setattr__(self, "proposal", self.final_proposal if self.proposal is None else self.proposal)
        object.__setattr__(self, "review", self.final_review if self.review is None else self.review)


def _call_aura(
    aura_fn: Callable[..., AURAProposal],
    snapshot: Mapping[str, Any],
    previous: AURAProposal | None,
) -> AURAProposal:
    """Compat: aura_fn(snapshot) ou aura_fn(snapshot, previous_proposal)."""
    try:
        return aura_fn(snapshot, previous)  # type: ignore[call-arg]
    except TypeError:
        return aura_fn(snapshot)  # type: ignore[call-arg]


class AURAHermesPipeline:
    """Ralph Loop: até max_cycles; Hermes pede evidência → AURA refina."""

    def __init__(self, max_cycles: int = 3, paper_trade: bool = True) -> None:
        if not 1 <= max_cycles <= 3:
            raise ValueError("max_cycles deve estar entre 1 e 3")
        self.max_cycles = max_cycles
        self.paper_trade = paper_trade

    def run(
        self,
        task_id: str,
        snapshot: Mapping[str, Any],
        aura_fn: Callable[..., AURAProposal],
        hermes_fn: Callable[[AURAProposal], HermesReview],
    ) -> JointResult:
        if not task_id or not isinstance(snapshot, Mapping):
            raise ValueError("task_id e snapshot são obrigatórios")

        audit_trail: list[str] = []
        current_proposal: AURAProposal | None = None
        review: HermesReview | None = None
        cycle = 0

        for cycle in range(1, self.max_cycles + 1):
            audit_trail.append(f"Cycle {cycle}: Requesting AURA proposal.")
            current_proposal = _call_aura(aura_fn, snapshot, current_proposal)
            if current_proposal.task_id != task_id:
                raise ValueError("AURA IA retornou task_id divergente")

            audit_trail.append(
                f"Cycle {cycle}: AURA proposed {len(current_proposal.evidence)} evidence items."
            )
            review = hermes_fn(current_proposal)
            if review.task_id != task_id:
                raise ValueError("Hermes retornou task_id divergente")

            if review.decision == Decision.BLOCK:
                audit_trail.append(f"Cycle {cycle}: Hermes issued BLOCK. Halting.")
                break

            if review.decision == Decision.ADVISORY or not review.missing_evidence:
                audit_trail.append(
                    f"Cycle {cycle}: Hermes ADVISORY or no missing evidence. Halting."
                )
                break

            audit_trail.append(
                f"Cycle {cycle}: Hermes requested more evidence: {review.missing_evidence}"
            )

        decision = self._decide(current_proposal, review)
        payload = {
            "task_id": task_id,
            "final_proposal": self._jsonable(current_proposal),
            "final_review": self._jsonable(review),
            "decision": decision.value,
            "cycles_executed": cycle,
            "paper_trade": self.paper_trade,
            "execution_allowed": False,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

        return JointResult(
            task_id=task_id,
            final_proposal=current_proposal,
            final_review=review,
            decision=decision,
            audit_hash=digest,
            cycles_executed=cycle,
            audit_trail=tuple(audit_trail),
            execution_allowed=False,
            proposal=current_proposal,
            review=review,
        )

    @staticmethod
    def _decide(proposal: AURAProposal | None, review: HermesReview | None) -> Decision:
        if proposal is None or review is None:
            return Decision.BLOCK
        if not review.supported or review.decision == Decision.BLOCK:
            return Decision.BLOCK
        if review.missing_evidence or review.confidence < 0.70 or not proposal.evidence:
            return Decision.AGUARDA
        return Decision.ADVISORY

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if value is None:
            return None
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


class AURAHermesPipelineV3:
    """Tree of Thoughts + PolicyEngine + VirtualSandbox + ContextEngine."""

    def __init__(self, max_cycles: int = 3, paper_trade: bool = True) -> None:
        if not 1 <= max_cycles <= 3:
            raise ValueError("max_cycles deve estar entre 1 e 3")
        self.max_cycles = max_cycles
        self.paper_trade = paper_trade
        self.sandbox = VirtualSandbox()
        self.context = ContextEngine()

    def run(
        self,
        task_id: str,
        snapshot: Mapping[str, Any],
        aura_fn: Callable[[Mapping[str, Any], str], Sequence[AURAProposal]],
        hermes_fn: Callable[[AURAProposal], HermesReview],
    ) -> JointResult:
        if not task_id or not isinstance(snapshot, Mapping):
            raise ValueError("task_id e snapshot são obrigatórios")

        self.context.clear()
        audit_trail: list[str] = []
        current_proposal: AURAProposal | None = None
        review: HermesReview | None = None
        cycle = 0

        for cycle in range(1, self.max_cycles + 1):
            audit_trail.append(f"Cycle {cycle}: Requesting ToT proposals from AURA.")
            proposals = list(aura_fn(snapshot, self.context.get_context_string()))

            valid: list[AURAProposal] = []
            for p in proposals:
                if p.task_id != task_id:
                    raise ValueError("AURA IA retornou task_id divergente")
                decision, reason = PolicyEngine.evaluate(p)
                if decision != Decision.BLOCK:
                    valid.append(p)
                else:
                    audit_trail.append(f"Cycle {cycle}: Proposal blocked by PolicyEngine ({reason})")

            if not valid:
                audit_trail.append(f"Cycle {cycle}: All proposals blocked. Halting.")
                break

            best = max(valid, key=lambda p: (len(p.evidence), sum(e.confidence for e in p.evidence)))
            audit_trail.append(
                f"Cycle {cycle}: Selected proposal with {len(best.evidence)} evidence items."
            )

            for action in best.proposed_actions or ():
                # action may be DryRunAction-like
                from .contracts import DryRunAction

                if not isinstance(action, DryRunAction):
                    if isinstance(action, dict) and "action" in action:
                        action = DryRunAction(
                            action=str(action["action"]),
                            parameters=dict(action.get("parameters") or {}),
                        )
                    else:
                        continue
                sim = self.sandbox.execute(action)
                self.context.add(cycle, "sandbox_simulation", sim)
                audit_trail.append(
                    f"Cycle {cycle}: Sandbox {action.action} executed={sim.get('executed')} "
                    f"-> {sim.get('simulated_result') or sim.get('status')}"
                )

            review = hermes_fn(best)
            if review.task_id != task_id:
                raise ValueError("Hermes retornou task_id divergente")
            self.context.add(
                cycle,
                "hermes_review",
                {"supported": review.supported, "concerns": list(review.concerns)},
            )

            current_proposal = best
            if review.decision == Decision.BLOCK:
                audit_trail.append(f"Cycle {cycle}: Hermes issued BLOCK. Halting.")
                break
            if review.decision == Decision.ADVISORY and not review.missing_evidence:
                audit_trail.append(f"Cycle {cycle}: Hermes ADVISORY. Halting.")
                break
            audit_trail.append(f"Cycle {cycle}: Hermes requested more evidence / AGUARDA.")

        decision = AURAHermesPipeline._decide(current_proposal, review)
        payload = {
            "task_id": task_id,
            "decision": decision.value,
            "cycles_executed": cycle,
            "audit_trail": audit_trail,
            "paper_trade": True,
            "execution_allowed": False,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

        return JointResult(
            task_id=task_id,
            final_proposal=current_proposal,
            final_review=review,
            decision=decision,
            audit_hash=digest,
            cycles_executed=cycle,
            audit_trail=tuple(audit_trail),
            execution_allowed=False,
            proposal=current_proposal,
            review=review,
        )
