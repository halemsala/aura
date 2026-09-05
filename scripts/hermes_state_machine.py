#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes State Machine V7 — grafo cíclico com arestas condicionais
================================================================
DETECT → DIAGNOSE → ACT → VERIFY → LEARN → ROUTE
ROUTE:
  HEALTHY + streak>=2 → END
  CRITICAL streak>=5 → CIRCUIT_OPEN → END
  cycle >= max → END
  senão → DETECT
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class Node(str, Enum):
    DETECT = "DETECT"
    DIAGNOSE = "DIAGNOSE"
    ACT = "ACT"
    VERIFY = "VERIFY"
    LEARN = "LEARN"
    ROUTE = "ROUTE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    END = "END"


@dataclass
class AgentState:
    root: str = ""
    cycle: int = 0
    max_cycles: int = 25
    do_fix: bool = True
    use_llm: bool = False
    status: str = "UNKNOWN"
    findings: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    memory_hits: int = 0
    llm_used: bool = False
    verify_passed: bool = False
    canary_passed: bool = False
    confidence_avg: float = 0.0
    last_node: str = ""
    consecutive_critical: int = 0
    healthy_streak: int = 0
    knowledge_hits: List[str] = field(default_factory=list)
    checkpoint_id: str = ""
    history: List[str] = field(default_factory=list)
    health_score: int = 0
    circuit_open: bool = False
    score_delta: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentState":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        return cls(**{k: v for k, v in d.items() if k in known})


class StateMachine:
    def __init__(self) -> None:
        self.nodes: Dict[Node, Callable[[AgentState], AgentState]] = {}

    def register(self, node: Node, fn: Callable[[AgentState], AgentState]) -> None:
        self.nodes[node] = fn

    def _call(self, node: Node, state: AgentState) -> AgentState:
        fn = self.nodes.get(node)
        state.last_node = node.value
        state.history.append(node.value)
        if not fn:
            return state
        return fn(state)

    def run_once(self, state: AgentState) -> AgentState:
        for node in (Node.DETECT, Node.DIAGNOSE, Node.ACT, Node.VERIFY, Node.LEARN):
            state = self._call(node, state)
        state = self._route(state)
        return state

    def _route(self, state: AgentState) -> AgentState:
        state.history.append(Node.ROUTE.value)
        state.last_node = Node.ROUTE.value
        if state.status == "CRITICAL":
            state.consecutive_critical += 1
            state.healthy_streak = 0
        elif state.status == "HEALTHY":
            state.healthy_streak += 1
            state.consecutive_critical = 0
        else:
            state.healthy_streak = 0

        if state.consecutive_critical >= 5:
            state.circuit_open = True
            state.history.append(Node.CIRCUIT_OPEN.value)
            state.actions.append("CIRCUIT_BREAKER_OPEN consecutive_critical>=5")
            state.last_node = Node.END.value
            state.history.append(Node.END.value)
            return state
        if state.healthy_streak >= 2 or state.cycle >= state.max_cycles:
            state.history.append(Node.END.value)
            state.last_node = Node.END.value
        return state

    def should_continue(self, state: AgentState) -> bool:
        if state.circuit_open:
            return False
        if state.healthy_streak >= 2:
            return False
        if state.cycle >= state.max_cycles:
            return False
        return True

    def checkpoint(self, state: AgentState, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        state.checkpoint_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_checkpoint(self, path: Path) -> Optional[AgentState]:
        if not path.exists():
            return None
        try:
            return AgentState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None
