"""Advisory pipeline com estado durável (plan-only).

Integra o grafo nativo `addons/aura_maximizer/durable_state.py` ao fluxo
AURA IA One → Hermes, sem execução, sem rede e sem dependência pip de langgraph.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter import AuraAIOneAdapter, HermesAuditAdapter
from .contracts import AuraAIOneProposal, CornerFeatures, HermesReview


def _ensure_maximizer_path() -> None:
    here = Path(__file__).resolve()
    root = here.parents[2]
    addons = root / "addons"
    if str(addons) not in sys.path:
        sys.path.insert(0, str(addons))


_ensure_maximizer_path()

try:
    from aura_maximizer.durable_state import (  # type: ignore
        CheckpointStore,
        GraphState,
        build_advisory_pipeline_graph,
    )
except Exception:  # pragma: no cover
    CheckpointStore = None  # type: ignore
    GraphState = None  # type: ignore
    build_advisory_pipeline_graph = None  # type: ignore


DEFAULT_CHECKPOINT_DIR = "runtime/checkpoints/advisory_durable"


@dataclass(frozen=True)
class DurableAdvisoryResult:
    run_id: str
    node_id: str
    graph_decision: str
    proposal: AuraAIOneProposal | None
    review: HermesReview | None
    final_decision: str
    paper_trade: bool = True
    execution_allowed: bool = False
    human_required: bool = False
    checkpoint_dir: str = DEFAULT_CHECKPOINT_DIR
    payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("execution_allowed must remain False")
        if not self.paper_trade:
            raise ValueError("paper_trade must remain True")


def _map_final(
    graph_decision: str,
    proposal: AuraAIOneProposal | None,
    review: HermesReview | None,
) -> str:
    if graph_decision == "BLOCK":
        return "BLOCK"
    if graph_decision == "AGUARDA":
        return "AGUARDA"
    if review is not None:
        return str(getattr(review, "decision", "AGUARDA"))
    if proposal is not None:
        return str(getattr(proposal, "decision", "AGUARDA"))
    return "AGUARDA"


def run_durable_advisory(
    features: CornerFeatures,
    *,
    checkpoint_dir: str | Path | None = None,
    confidence_hint: float | None = None,
    aura_adapter: AuraAIOneAdapter | None = None,
    hermes_adapter: HermesAuditAdapter | None = None,
) -> DurableAdvisoryResult:
    """Propose → Hermes → gate com checkpoints; nunca executa ordens."""
    aura = aura_adapter or AuraAIOneAdapter()
    hermes = hermes_adapter or HermesAuditAdapter()

    proposal = aura.propose(features)
    review = hermes.review(proposal, features)

    if build_advisory_pipeline_graph is None:
        return DurableAdvisoryResult(
            run_id="no-graph",
            node_id="fallback",
            graph_decision="DONE",
            proposal=proposal,
            review=review,
            final_decision=_map_final("DONE", proposal, review),
            paper_trade=True,
            execution_allowed=False,
            human_required=False,
            checkpoint_dir=str(checkpoint_dir or DEFAULT_CHECKPOINT_DIR),
            payload={"mode": "fallback_no_maximizer"},
        )

    cdir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)
    cdir.mkdir(parents=True, exist_ok=True)

    conf = confidence_hint
    if conf is None:
        conf = float(getattr(review, "confidence", None) or getattr(proposal, "confidence", 0.5) or 0.5)

    graph = build_advisory_pipeline_graph(cdir)
    state = graph.start(
        "propose",
        {
            "confidence": conf,
            "fixture_id": features.fixture_id,
            "proposal_decision": str(proposal.decision),
            "review_decision": str(review.decision),
        },
    )

    last_decision = "CONTINUE"
    for _ in range(8):
        last_decision, state = graph.step(state)
        if last_decision in ("DONE", "AGUARDA", "BLOCK"):
            break

    final = _map_final(last_decision, proposal, review)
    if str(getattr(review, "decision", "")) == "BLOCK":
        final = "BLOCK"
        last_decision = "BLOCK"

    return DurableAdvisoryResult(
        run_id=state.run_id,
        node_id=state.node_id,
        graph_decision=last_decision,
        proposal=proposal,
        review=review,
        final_decision=final,
        paper_trade=True,
        execution_allowed=False,
        human_required=bool(state.human_required) or last_decision == "AGUARDA",
        checkpoint_dir=str(cdir),
        payload=dict(state.payload),
    )


def resume_durable_advisory(
    run_id: str,
    *,
    approved: bool,
    note: str = "",
    checkpoint_dir: str | Path | None = None,
):
    """Retoma após aprovação humana (ainda sem execução)."""
    if build_advisory_pipeline_graph is None or CheckpointStore is None:
        return None
    cdir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)
    store = CheckpointStore(cdir)
    state = store.restore_state(run_id)
    if state is None:
        return None
    graph = build_advisory_pipeline_graph(cdir)
    return graph.resume_after_human(state, approved=approved, note=note)


__all__ = [
    "DurableAdvisoryResult",
    "run_durable_advisory",
    "resume_durable_advisory",
    "DEFAULT_CHECKPOINT_DIR",
]
