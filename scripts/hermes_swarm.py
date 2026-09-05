#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Swarm V7 — agentes executam trabalho real via hooks
==========================================================
Scanner / Knowledge / Fixer / Validator / Reporter / Sentinel
Blackboard partilhado. Hooks injectados pelo OS.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Message:
    from_agent: str
    to_agent: str
    kind: str
    payload: Dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Blackboard:
    root: str = ""
    cycle: int = 0
    status: str = "UNKNOWN"
    findings: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    recommendations: List[str, ] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_hits: List[str] = field(default_factory=list)
    memory_hits: int = 0
    llm_used: bool = False
    verify_passed: bool = False
    canary_passed: bool = False
    confidence_avg: float = 0.0
    runbook_path: str = ""
    health_score: int = 0
    circuit_open: bool = False
    score_delta: int = 0

    def post(self, msg: Message) -> None:
        self.messages.append(asdict(msg))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# fix typo in type - I accidentally wrote List[str, ] which is still valid
# actually List[str, ] works in Python 3.9+ as List[str]. OK.

class BaseAgent:
    name = "base"

    def __init__(self, board: Blackboard, hook: Optional[Callable[[Blackboard], None]] = None):
        self.board = board
        self.hook = hook

    def run(self) -> None:
        if self.hook:
            self.hook(self.board)


class ScannerAgent(BaseAgent):
    name = "Scanner"

    def run(self) -> None:
        super().run()
        n = len(self.board.findings)
        crit = sum(1 for f in self.board.findings if f.get("severity") == "CRITICAL")
        self.board.post(Message(self.name, "Knowledge", "finding", {"count": n, "critical": crit}))


class KnowledgeAgent(BaseAgent):
    name = "Knowledge"

    def run(self) -> None:
        super().run()
        self.board.post(Message(
            self.name, "Fixer", "advice",
            {"hits": self.board.knowledge_hits, "recs": self.board.recommendations[:5]},
        ))


class FixerAgent(BaseAgent):
    name = "Fixer"

    def run(self) -> None:
        super().run()
        self.board.post(Message(
            self.name, "Validator", "action",
            {"actions": self.board.actions, "tools": self.board.tool_results[-5:]},
        ))


class ValidatorAgent(BaseAgent):
    name = "Validator"

    def run(self) -> None:
        super().run()
        self.board.post(Message(
            self.name, "Reporter", "verify",
            {
                "verify_passed": self.board.verify_passed,
                "canary_passed": self.board.canary_passed,
                "status": self.board.status,
                "score": self.board.health_score,
            },
        ))


class ReporterAgent(BaseAgent):
    name = "Reporter"

    def run(self) -> None:
        super().run()
        self.board.post(Message(
            self.name, "ALL", "report",
            {
                "status": self.board.status,
                "actions": len(self.board.actions),
                "runbook": self.board.runbook_path,
                "score": self.board.health_score,
            },
        ))


class SentinelAgent(BaseAgent):
    name = "Sentinel"

    def run(self) -> None:
        super().run()
        self.board.post(Message(
            self.name, "ALL", "watch",
            {"circuit_open": self.board.circuit_open, "score_delta": self.board.score_delta},
        ))


class SwarmOrchestrator:
    def __init__(self, board: Blackboard, hooks: Optional[Dict[str, Callable]] = None):
        hooks = hooks or {}
        self.board = board
        self.agents = [
            ScannerAgent(board, hooks.get("scanner")),
            KnowledgeAgent(board, hooks.get("knowledge")),
            FixerAgent(board, hooks.get("fixer")),
            ValidatorAgent(board, hooks.get("validator")),
            ReporterAgent(board, hooks.get("reporter")),
            SentinelAgent(board, hooks.get("sentinel")),
        ]

    def run(self) -> Blackboard:
        for agent in self.agents:
            agent.run()
        return self.board


def export_runbook(board: Blackboard, root: Path) -> Path:
    rb_dir = root / "logs_supervisor" / "runbooks"
    rb_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = rb_dir / f"runbook_{ts}.md"
    lines = [
        f"# Hermes V7 Runbook — ciclo {board.cycle}",
        f"Status final: **{board.status}**  score={board.health_score}  Δ={board.score_delta}",
        f"Gerado: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Findings CRITICAL/HIGH",
    ]
    for f in board.findings:
        if f.get("severity") in ("CRITICAL", "HIGH"):
            lines.append(f"- `{f.get('code')}`: {f.get('message')} → {f.get('fix_hint', '')}")
    lines += ["", "## Ações"]
    for a in board.actions:
        lines.append(f"- {a}")
    lines += ["", "## Tools"]
    for t in board.tool_results[-12:]:
        lines.append(f"- `{t.get('name')}` ok={t.get('ok')}: {t.get('message')}")
    lines += ["", "## Recomendações"]
    for r in board.recommendations:
        lines.append(f"- {r}")
    lines += ["", "## Swarm"]
    for m in board.messages:
        lines.append(f"- {m.get('from_agent')} → {m.get('to_agent')} [{m.get('kind')}]")
    path.write_text("\n".join(lines), encoding="utf-8")
    latest = rb_dir / "RUNBOOK_LATEST.md"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path
