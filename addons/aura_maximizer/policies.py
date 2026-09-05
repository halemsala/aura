"""Policy Engine: regras determinísticas de negócio (pré-Hermes)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import AURAProposal, Decision
else:
    from enum import Enum

    class Decision(str, Enum):
        ADVISORY = "ADVISORY"
        AGUARDA = "AGUARDA"
        BLOCK = "BLOCK"


_BLOCK_TERMS = ("execute order", "live trade", "real money", "place bet", "send order")


class PolicyEngine:
    @staticmethod
    def evaluate(proposal: "AURAProposal") -> tuple["Decision", str]:
        summary_l = (proposal.summary or "").lower()
        for term in _BLOCK_TERMS:
            if term in summary_l:
                return Decision.BLOCK, f"Policy violation: forbidden term '{term}'."

        if len(proposal.evidence) < 2:
            return Decision.AGUARDA, "Policy violation: minimum 2 evidence items required."

        avg_conf = sum(e.confidence for e in proposal.evidence) / max(len(proposal.evidence), 1)
        if avg_conf < 0.5:
            return Decision.AGUARDA, "Policy violation: evidence confidence too low."

        return Decision.ADVISORY, "Passed deterministic policy checks."
