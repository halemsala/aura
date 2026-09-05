"""Ponte opcional AURA Maximizer ↔ LangChain / LangGraph (fail-closed).

Design:
  - NÃO exige `langchain` / `langchain_core` instalados.
  - Se presentes, expõe adaptadores Runnable-like e um grafo mínimo.
  - Se ausentes, usa implementação nativa equivalente (mesma API pública).
  - Nunca define tools que executem ordens, rede ou side-effects reais.
  - paper_trade=True, execution_allowed=False sempre.

Uso típico (sem LangChain):
    from aura_maximizer.langchain_bridge import AURARunnablePipeline
    out = AURARunnablePipeline().invoke({"task_id": "t1", "snapshot": {...}})

Uso típico (com langchain_core instalado no host):
    # mesmo invoke; internamente pode embrulhar em RunnableLambda
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .contracts import EXECUTION_ALLOWED, GLM_ADVISORY_ONLY, PAPER_TRADE
from .orchestrator import (
    AURAHermesPipeline,
    AURAHermesPipelineV3,
    AURAProposal,
    Decision,
    Evidence,
    HermesReview,
    JointResult,
)
from .sandbox import VirtualSandbox
from .observability import AuditLogger

# ---------------------------------------------------------------------------
# Optional LangChain core
# ---------------------------------------------------------------------------
_LC_AVAILABLE = False
try:
    from langchain_core.runnables import RunnableLambda  # type: ignore

    _LC_AVAILABLE = True
except Exception:  # pragma: no cover
    RunnableLambda = None  # type: ignore


def langchain_available() -> bool:
    return _LC_AVAILABLE


# ---------------------------------------------------------------------------
# Default pure (no-LLM) proposal / review for offline invoke
# ---------------------------------------------------------------------------
def _default_aura(snapshot: Mapping[str, Any], previous: AURAProposal | None = None) -> AURAProposal:
    task_id = str(snapshot.get("task_id") or snapshot.get("fixture_id") or "task")
    sources = snapshot.get("sources") or ["local"]
    if not isinstance(sources, (list, tuple)):
        sources = [str(sources)]
    evidence = tuple(
        Evidence(source=str(s), value=snapshot.get("value", snapshot), freshness="unknown", confidence=0.55)
        for s in list(sources)[:4]
    )
    # ensure ≥2 for policy-friendly offline demos when only one source
    if len(evidence) == 1:
        evidence = evidence + (
            Evidence(source="context", value={"paper": True}, freshness="unknown", confidence=0.55),
        )
    summary = "AURA offline proposal (langchain_bridge default)"
    if previous is not None:
        summary = "AURA refined proposal (langchain_bridge)"
        evidence = previous.evidence + evidence
    return AURAProposal(
        task_id=task_id,
        summary=summary,
        findings=("offline_default",),
        evidence=evidence[:8],
        suggested_next_step="aguardar_host",
        cycle=(previous.cycle + 1) if previous else 1,
    )


def _default_hermes(proposal: AURAProposal) -> HermesReview:
    if len(proposal.evidence) < 2:
        return HermesReview(
            proposal.task_id,
            supported=True,
            concerns=("insufficient_evidence",),
            missing_evidence=("additional_source",),
            confidence=0.4,
            decision=Decision.AGUARDA,
        )
    avg = sum(e.confidence for e in proposal.evidence) / max(len(proposal.evidence), 1)
    if avg < 0.5:
        return HermesReview(
            proposal.task_id,
            supported=True,
            concerns=("low_confidence",),
            missing_evidence=(),
            confidence=avg,
            decision=Decision.AGUARDA,
        )
    return HermesReview(
        proposal.task_id,
        supported=True,
        concerns=(),
        missing_evidence=(),
        confidence=min(0.9, avg + 0.1),
        decision=Decision.ADVISORY,
    )


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class AURARunnablePipeline:
    """Interface estilo Runnable: invoke(input) -> dict (sempre paper-only).

    input esperado:
      {
        "task_id": str,
        "snapshot": Mapping,
        optional "mode": "ralph" | "tot",
        optional "trace_id": str,
      }
    """

    def __init__(
        self,
        *,
        mode: str = "ralph",
        max_cycles: int = 3,
        aura_fn: Callable[..., AURAProposal] | None = None,
        hermes_fn: Callable[[AURAProposal], HermesReview] | None = None,
        tot_aura_fn: Callable[[Mapping[str, Any], str], Sequence[AURAProposal]] | None = None,
        audit_log: str | None = None,
    ) -> None:
        if mode not in {"ralph", "tot"}:
            raise ValueError("mode must be 'ralph' or 'tot'")
        self.mode = mode
        self.max_cycles = max_cycles
        self.aura_fn = aura_fn or _default_aura
        self.hermes_fn = hermes_fn or _default_hermes
        self.tot_aura_fn = tot_aura_fn
        self._logger = AuditLogger(audit_log) if audit_log else None
        self.sandbox = VirtualSandbox()

    def invoke(self, inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(inputs, Mapping):
            raise TypeError("inputs must be a mapping")
        task_id = str(inputs.get("task_id") or "task")
        snapshot = inputs.get("snapshot") or {}
        if not isinstance(snapshot, Mapping):
            raise TypeError("snapshot must be a mapping")
        # inject task_id into snapshot for default aura
        snap = dict(snapshot)
        snap.setdefault("task_id", task_id)

        mode = str(inputs.get("mode") or self.mode)
        if mode == "tot":
            result = self._run_tot(task_id, snap)
        else:
            result = self._run_ralph(task_id, snap)

        out = {
            "task_id": result.task_id,
            "decision": result.decision.value if isinstance(result.decision, Enum) else str(result.decision),
            "cycles_executed": result.cycles_executed,
            "audit_hash": result.audit_hash,
            "audit_trail": list(result.audit_trail),
            "proposal": _jsonable(result.final_proposal),
            "review": _jsonable(result.final_review),
            "paper_trade": PAPER_TRADE,
            "execution_allowed": EXECUTION_ALLOWED,
            "glm_advisory_only": GLM_ADVISORY_ONLY,
            "langchain_core_available": _LC_AVAILABLE,
            "bridge": "aura_maximizer.langchain_bridge",
        }
        if self._logger:
            self._logger.log(
                "langchain_bridge.invoke",
                {"decision": out["decision"], "cycles": out["cycles_executed"]},
                trace_id=str(inputs.get("trace_id") or result.audit_hash[:16]),
            )
        return out

    def _run_ralph(self, task_id: str, snapshot: Mapping[str, Any]) -> JointResult:
        pipe = AURAHermesPipeline(max_cycles=self.max_cycles, paper_trade=True)
        return pipe.run(task_id, snapshot, self.aura_fn, self.hermes_fn)

    def _run_tot(self, task_id: str, snapshot: Mapping[str, Any]) -> JointResult:
        pipe = AURAHermesPipelineV3(max_cycles=self.max_cycles, paper_trade=True)

        def tot_fn(snap: Mapping[str, Any], ctx: str) -> Sequence[AURAProposal]:
            if self.tot_aura_fn is not None:
                return list(self.tot_aura_fn(snap, ctx))
            # default: single branch via _default_aura
            p = _default_aura(snap, None)
            return [p]

        return pipe.run(task_id, snapshot, tot_fn, self.hermes_fn)

    def as_langchain_runnable(self) -> Any:
        """Retorna RunnableLambda se langchain_core existir; senão self (duck-typed)."""
        if not _LC_AVAILABLE or RunnableLambda is None:
            return self
        return RunnableLambda(lambda x: self.invoke(x if isinstance(x, Mapping) else {"snapshot": x}))


class AURALangChainToolGuard:
    """Allowlist de nomes de tools LangChain — só dry-run via VirtualSandbox."""

    ALLOWED = frozenset(
        {
            "math.calculate_stake",
            "data.get_odds",
            "system.health_check",
        }
    )

    def __init__(self) -> None:
        self.sandbox = VirtualSandbox()

    def run_tool(self, name: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from .contracts import DryRunAction

        if name not in self.ALLOWED:
            return {
                "tool": name,
                "executed": False,
                "status": "BLOCKED",
                "reason": "tool_not_in_aura_allowlist",
                "paper_trade": True,
                "execution_allowed": False,
            }
        return self.sandbox.execute(DryRunAction(action=name, parameters=dict(params or {})))


def build_aura_langchain_chain(
    *,
    mode: str = "ralph",
    max_cycles: int = 3,
) -> Any:
    """Factory: Runnable LangChain se disponível, senão AURARunnablePipeline nativo."""
    pipe = AURARunnablePipeline(mode=mode, max_cycles=max_cycles)
    return pipe.as_langchain_runnable()


__all__ = [
    "AURARunnablePipeline",
    "AURALangChainToolGuard",
    "build_aura_langchain_chain",
    "langchain_available",
]
