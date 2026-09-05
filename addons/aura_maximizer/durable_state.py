"""Estado durável nativo do AURA — padrões inspirados em LangGraph, sem dependência externa.

Design (native_pattern_first):
  - Grafo de nós com estado explícito e serializável
  - Checkpoints em disco (JSON) para retomada
  - Interrupção human-in-the-loop (AGUARDA) sem execução
  - Fail-closed: execution_allowed=False; nós mutantes rejeitados

NÃO instala langgraph, NÃO abre rede, NÃO agenda jobs.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from .contracts import EXECUTION_ALLOWED, GLM_ADVISORY_ONLY, PAPER_TRADE

NodeStatus = Literal["pending", "running", "completed", "interrupted", "failed", "blocked"]
GraphDecision = Literal["CONTINUE", "AGUARDA", "BLOCK", "DONE"]


@dataclass
class GraphState:
    """Estado explícito do grafo (serializável)."""
    run_id: str
    node_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    paper_trade: bool = True
    execution_allowed: bool = False
    glm_advisory_only: bool = True
    human_required: bool = False
    blocked_reason: str | None = None
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("execution_allowed must remain False in durable_state")
        if not self.paper_trade:
            raise ValueError("paper_trade must remain True in durable_state")


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    description: str
    mutating: bool = False
    requires_human: bool = False

    def __post_init__(self) -> None:
        if self.mutating:
            raise ValueError("mutating nodes are not allowed in this native graph")


@dataclass
class Checkpoint:
    checkpoint_id: str
    run_id: str
    node_id: str
    state: dict[str, Any]
    created_at: float
    parent_checkpoint_id: str | None = None


class CheckpointStore:
    """Persistência simples em JSON (um arquivo por run)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)[:128]
        return self.root / f"{safe}.json"

    def save(self, state: GraphState, parent_checkpoint_id: str | None = None) -> Checkpoint:
        cp = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            run_id=state.run_id,
            node_id=state.node_id,
            state={
                "run_id": state.run_id,
                "node_id": state.node_id,
                "payload": state.payload,
                "history": list(state.history),
                "paper_trade": True,
                "execution_allowed": False,
                "glm_advisory_only": True,
                "human_required": state.human_required,
                "blocked_reason": state.blocked_reason,
                "updated_at": state.updated_at,
            },
            created_at=time.time(),
            parent_checkpoint_id=parent_checkpoint_id,
        )
        path = self._path(state.run_id)
        data: dict[str, Any] = {"latest": asdict(cp), "checkpoints": []}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {"latest": None, "checkpoints": []}
        data.setdefault("checkpoints", []).append(asdict(cp))
        data["latest"] = asdict(cp)
        # keep last 50
        data["checkpoints"] = data["checkpoints"][-50:]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return cp

    def load_latest(self, run_id: str) -> Checkpoint | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        latest = data.get("latest")
        if not latest:
            return None
        return Checkpoint(**latest)

    def restore_state(self, run_id: str) -> GraphState | None:
        cp = self.load_latest(run_id)
        if cp is None:
            return None
        s = cp.state
        return GraphState(
            run_id=s["run_id"],
            node_id=s["node_id"],
            payload=dict(s.get("payload") or {}),
            history=list(s.get("history") or []),
            paper_trade=True,
            execution_allowed=False,
            glm_advisory_only=True,
            human_required=bool(s.get("human_required")),
            blocked_reason=s.get("blocked_reason"),
            updated_at=float(s.get("updated_at") or time.time()),
        )


NodeHandler = Callable[[GraphState], tuple[GraphDecision, GraphState]]


class DurableGraph:
    """Grafo mínimo: sequência de nós + interrupção humana + checkpoint."""

    def __init__(
        self,
        nodes: Mapping[str, NodeSpec],
        edges: Mapping[str, str | None],
        handlers: Mapping[str, NodeHandler],
        store: CheckpointStore,
    ) -> None:
        self.nodes = dict(nodes)
        self.edges = dict(edges)
        self.handlers = dict(handlers)
        self.store = store
        for nid, spec in self.nodes.items():
            if spec.mutating:
                raise ValueError(f"node {nid} is mutating — forbidden")
            if nid not in self.handlers:
                raise ValueError(f"missing handler for node {nid}")

    def start(self, entry_node: str, payload: dict[str, Any] | None = None) -> GraphState:
        if entry_node not in self.nodes:
            raise KeyError(entry_node)
        state = GraphState(
            run_id=str(uuid.uuid4()),
            node_id=entry_node,
            payload=dict(payload or {}),
            history=[entry_node],
            paper_trade=PAPER_TRADE,
            execution_allowed=EXECUTION_ALLOWED,
            glm_advisory_only=GLM_ADVISORY_ONLY,
        )
        self.store.save(state)
        return state

    def step(self, state: GraphState) -> tuple[GraphDecision, GraphState]:
        if state.execution_allowed:
            raise RuntimeError("execution_allowed=True is forbidden")
        spec = self.nodes[state.node_id]
        if spec.requires_human or state.human_required:
            state.human_required = True
            state.updated_at = time.time()
            self.store.save(state)
            return "AGUARDA", state

        decision, new_state = self.handlers[state.node_id](state)
        new_state.updated_at = time.time()
        new_state.paper_trade = True
        new_state.execution_allowed = False
        new_state.glm_advisory_only = True

        if decision == "BLOCK":
            new_state.blocked_reason = new_state.blocked_reason or "blocked by node handler"
            self.store.save(new_state)
            return "BLOCK", new_state

        if decision == "AGUARDA":
            new_state.human_required = True
            self.store.save(new_state)
            return "AGUARDA", new_state

        if decision == "DONE":
            self.store.save(new_state)
            return "DONE", new_state

        # CONTINUE → advance edge
        nxt = self.edges.get(state.node_id)
        if nxt is None:
            self.store.save(new_state)
            return "DONE", new_state
        new_state.node_id = nxt
        new_state.history = list(new_state.history) + [nxt]
        self.store.save(new_state)
        return "CONTINUE", new_state

    def resume_after_human(self, state: GraphState, approved: bool, note: str = "") -> GraphState:
        """Retoma após aprovação humana explícita (ainda sem execução)."""
        if not approved:
            state.blocked_reason = note or "human rejected"
            state.human_required = False
            self.store.save(state)
            return state
        state.human_required = False
        state.payload = {**state.payload, "human_note": note}
        # advance one edge if possible
        nxt = self.edges.get(state.node_id)
        if nxt:
            state.node_id = nxt
            state.history = list(state.history) + [nxt]
        state.updated_at = time.time()
        self.store.save(state)
        return state


def build_advisory_pipeline_graph(checkpoint_dir: str | Path) -> DurableGraph:
    """Grafo padrão AURA→Hermes→Gate (somente advisory)."""

    def propose(s: GraphState) -> tuple[GraphDecision, GraphState]:
        s.payload["proposal"] = s.payload.get("proposal") or {
            "type": "advisory",
            "text": "proposal-placeholder",
        }
        return "CONTINUE", s

    def hermes_review(s: GraphState) -> tuple[GraphDecision, GraphState]:
        conf = float(s.payload.get("confidence", 0.5))
        if conf < 0.35:
            s.blocked_reason = "hermes low confidence"
            return "BLOCK", s
        if conf < 0.6:
            s.human_required = True
            return "AGUARDA", s
        s.payload["hermes"] = {"ok": True, "confidence": conf}
        return "CONTINUE", s

    def security_gate(s: GraphState) -> tuple[GraphDecision, GraphState]:
        if s.payload.get("force_block"):
            s.blocked_reason = "security gate"
            return "BLOCK", s
        s.payload["gate"] = "passed"
        return "DONE", s

    nodes = {
        "propose": NodeSpec("propose", "AURA IA propõe (advisory)"),
        "hermes_review": NodeSpec("hermes_review", "Hermes revisa adversarialmente"),
        "security_gate": NodeSpec("security_gate", "Gate de segurança fail-closed"),
    }
    edges = {
        "propose": "hermes_review",
        "hermes_review": "security_gate",
        "security_gate": None,
    }
    handlers = {
        "propose": propose,
        "hermes_review": hermes_review,
        "security_gate": security_gate,
    }
    return DurableGraph(nodes, edges, handlers, CheckpointStore(checkpoint_dir))
