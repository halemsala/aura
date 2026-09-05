#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HERMES AUTONOMOUS OS — V10.1
===========================
Grafo + planner + auditor CLEAN + venv + recycle zombie + telemetry JSONL.

Invariantes: paper_trade=true · execution_allowed=false
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hermes_state_machine import AgentState, Node, StateMachine  # noqa: E402
from hermes_knowledge import KnowledgeIndex  # noqa: E402
from hermes_tools import ToolRegistry  # noqa: E402
from hermes_swarm import Blackboard, SwarmOrchestrator, export_runbook  # noqa: E402
from hermes_sensors import Finding, detect_all, compile_file, port_open  # noqa: E402
from hermes_memory import FixMemory  # noqa: E402
from hermes_policy import PolicyGuard  # noqa: E402
from hermes_planner import plan as build_plan  # noqa: E402
from hermes_telemetry import Telemetry  # noqa: E402
from hermes_incident import classify as classify_incident, human as incident_human  # noqa: E402
from hermes_rag import retrieve as rag_retrieve  # noqa: E402
from hermes_episodes import EpisodeMemory  # noqa: E402
from hermes_skills import load_skills  # noqa: E402

VERSION = "10.1.0"
KNOWN_SYNTAX_FIXES = {
    "deep_diagnostic_try_nest": {
        "old": (
            "try:\n    from deep_diagnostic import collect_diagnostic\n"
            "try:\n    from matrix_full_diagnostic import run_full as matrix_run_full\n"
            "except Exception:\n    try:\n        from engine.matrix_full_diagnostic import run_full as matrix_run_full\n"
            "    except Exception:\n        matrix_run_full = None\n"
            "except ImportError:\n    from engine.deep_diagnostic import collect_diagnostic"
        ),
        "new": (
            "try:\n    from deep_diagnostic import collect_diagnostic\n"
            "except ImportError:\n    from engine.deep_diagnostic import collect_diagnostic\n"
            "try:\n    from matrix_full_diagnostic import run_full as matrix_run_full\n"
            "except Exception:\n    try:\n        from engine.matrix_full_diagnostic import run_full as matrix_run_full\n"
            "    except Exception:\n        matrix_run_full = None"
        ),
    },
}


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def _find_root(explicit: Optional[str] = None) -> Path:
    cands = []
    if explicit:
        cands.append(Path(explicit))
    if os.environ.get("AURA_ROOT"):
        cands.append(Path(os.environ["AURA_ROOT"]))
    cands += [Path(r"C:\aura"), Path(r"C:\AURA_V25"), Path.cwd(), Path(__file__).resolve().parents[1]]
    for c in cands:
        if c and (c / "engine" / "server.py").exists():
            return c.resolve()
    return Path.cwd().resolve()


def _fp(code: str, msg: str) -> str:
    return hashlib.sha256(f"{code}|{msg}".encode()).hexdigest()[:16]


def apply_syntax(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        orig = text
        for fix in KNOWN_SYNTAX_FIXES.values():
            if fix["old"] in text:
                text = text.replace(fix["old"], fix["new"])
        if text == orig:
            return False
        bak = path.with_suffix(path.suffix + ".hermesbak")
        if not bak.exists():
            bak.write_text(orig, encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        if compile_file(path):
            path.write_text(orig, encoding="utf-8")
            return False
        return True
    except Exception:
        return False


def llm_tips(findings: List[Finding]) -> List[str]:
    if not port_open(11434):
        return []
    crit = [f for f in findings if f.severity in ("CRITICAL", "HIGH") and not f.fixed][:8]
    if not crit:
        return []
    summary = "\n".join(f"- [{f.severity}] {f.code}: {f.message}" for f in crit)
    prompt = (
        "SRE AURA paper-trade. PAPER_TRADE=true EXECUTION_ALLOWED=false. "
        "Não inventes placar, odd ou fixture. Liste até 5 acções seguras numeradas.\n" + summary
    )
    models = ["llama3.2:3b", "glm4:9b-chat-q4_0", "llama3.1:8b"]
    for model in models:
        try:
            payload = json.dumps({
                "model": model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.2, "num_predict": 280},
            }).encode()
            req = Request("http://127.0.0.1:11434/api/generate", data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=25) as resp:
                text = json.loads(resp.read().decode()).get("response", "")
                tips = [ln.strip() for ln in text.splitlines()
                        if ln.strip() and (ln.strip()[0].isdigit() or ln.strip().startswith("-"))][:5]
                if tips:
                    return tips
        except Exception:
            continue
    return []


def _prev_score(root: Path) -> int:
    hist = root / "logs_supervisor" / "hermes_history.json"
    if not hist.exists():
        return 0
    try:
        data = json.loads(hist.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return int(data[-1].get("score") or 0)
    except Exception:
        return 0
    return 0


def _status_from(findings: List[Finding]) -> str:
    sevs = [f.severity for f in findings if not f.fixed and f.severity not in ("OK", "INFO")]
    if any(s == "CRITICAL" for s in sevs):
        return "CRITICAL"
    if any(s in ("HIGH", "MEDIUM") for s in sevs):
        return "DEGRADED"
    return "HEALTHY"


class HermesRuntime:
    def __init__(self, root: Path, do_fix: bool, use_llm: bool):
        self.root = root
        self.do_fix = do_fix
        self.use_llm = use_llm
        self.memory = FixMemory(root)
        self.kb = KnowledgeIndex(root)
        self.tools = ToolRegistry(root)
        self.policy = PolicyGuard(root)
        self.tel = Telemetry(root)
        self.episodes = EpisodeMemory(root)
        self.findings: List[Finding] = []
        self.board = Blackboard(root=str(root))

    def node_detect(self, state: AgentState) -> AgentState:
        _log("GRAPH/DETECT")
        self.policy.enforce_env()
        tier = "full" if state.cycle <= 1 or state.status in ("CRITICAL", "UNKNOWN", "") else "medium"
        self.findings = detect_all(self.root, tier=tier)
        state.actions.append(f"SENSOR_TIER={tier}")
        state.findings = [asdict(f) for f in self.findings]
        confs = [f.confidence for f in self.findings]
        state.confidence_avg = sum(confs) / len(confs) if confs else 0
        state.status = _status_from(self.findings)
        return state

    def node_diagnose(self, state: AgentState) -> AgentState:
        _log("GRAPH/DIAGNOSE")
        blob = " ".join(f.code + " " + f.message for f in self.findings)
        hits = self.kb.query(blob, top_k=4)
        state.knowledge_hits = [f"{h.id}:{h.title}({h.score})" for h in hits]
        for h in hits:
            state.recommendations.append(f"[KB] {h.title} → {h.action}")
        cls, reasons = classify_incident(state.findings)
        state.recommendations.insert(0, f"[INCIDENT] {cls} — {incident_human(cls)}")
        if reasons:
            state.recommendations.append("[INCIDENT] " + ", ".join(reasons[:6]))
        packs = [s for s in load_skills(self.root) if s.enabled]
        if packs:
            state.recommendations.append('[SKILLS] ' + ', '.join(f'{s.id}@{s.version}' for s in packs[:8]))
        rag = rag_retrieve(self.root, blob, state.knowledge_hits)
        for hit in rag:
            state.recommendations.append(f"[RAG:{hit['src']}] {hit['title']} ({hit['score']})")
        if self.use_llm:
            tips = llm_tips(self.findings)
            if tips:
                state.llm_used = True
                state.recommendations.extend(f"[LLM] {t}" for t in tips)
        return state

    def node_act(self, state: AgentState) -> AgentState:
        _log("GRAPH/ACT")
        if not self.do_fix:
            return state
        cls, _ = classify_incident([asdict(f) for f in self.findings])
        recipe = self.episodes.recipe(cls)
        steps = build_plan([asdict(f) for f in self.findings], incident=cls, recipe=recipe)
        if recipe:
            state.actions.append(f"RECIPE={','.join(recipe[:6])}")
        state.actions.append(f"INCIDENT={cls}")
        syntax_broken = any(f.code.startswith("SYNTAX_") and not f.fixed for f in self.findings)
        for step in steps:
            if syntax_broken and step.tool.startswith("safe_start"):
                state.actions.append(f"SKIP {step.tool} (syntax ainda partido)")
                continue
            fp = _fp(step.tool, step.finding_code or step.reason)
            if self.memory.in_cooldown(fp):
                state.actions.append(f"COOLDOWN {step.tool}")
                continue
            if self.memory.recall(fp):
                state.actions.append(f"MEMORY HIT {step.tool}")
                state.memory_hits += 1
            ok = False
            if step.tool == "apply_syntax_fix":
                path = Path(step.kwargs.get("file") or "")
                if path.exists() and apply_syntax(path):
                    ok = True
                    state.actions.append(f"FIXED syntax {path.name}")
                    for f in self.findings:
                        if f.code.startswith("SYNTAX_"):
                            f.fixed = True
                    syntax_broken = any(f.code.startswith("SYNTAX_") and not f.fixed for f in self.findings)
                else:
                    state.actions.append(f"syntax skip {path.name or '?'}")
            else:
                r = self.tools.run(step.tool, **step.kwargs)
                ok = r.ok
                state.actions.append(f"{step.tool}={'OK' if r.ok else 'FAIL'} ({step.reason})")
                if r.ok:
                    for f in self.findings:
                        if f.code == step.finding_code:
                            f.fixed = True
            self.memory.remember(fp, step.tool, {"reason": step.reason}, ok)
            self.tel.emit("tool", {"tool": step.tool, "ok": ok, "reason": step.reason})
        state.actions.append(f"plan_steps={len(steps)} tools={len(self.tools.history)}")
        return state

    def node_verify(self, state: AgentState) -> AgentState:
        _log("GRAPH/VERIFY")
        tr = self.tools.run("check_health", service="engine")
        br = self.tools.run("check_health", service="bridge")
        state.verify_passed = bool(tr.ok and br.ok)
        can = self.tools.run("canary_ui_state")
        live = self.tools.run("read_live_latest")
        chat = self.tools.run("canary_trader_chat")
        state.canary_passed = can.ok or live.ok
        hs = self.tools.run("health_score")
        prev = _prev_score(self.root)
        state.health_score = int(hs.data.get("score", 0))
        state.score_delta = state.health_score - prev
        state.actions.append(f"VERIFY={'OK' if state.verify_passed else 'DEGRADED'}")
        state.actions.append(f"CANARY={'OK' if state.canary_passed else 'FAIL'}")
        state.actions.append(f"CHAT_CANARY={'OK' if chat.ok else 'SKIP/FAIL'}")
        state.actions.append(f"HEALTH_SCORE={state.health_score}")
        state.actions.append(f"SCORE_DELTA={state.score_delta:+d}")
        if state.score_delta <= -20 and prev > 0:
            state.recommendations.append("[ANOMALY] health score caiu ≥20 pts vs ciclo anterior")
        if state.verify_passed:
            deep = self.tools.run("deep_diagnostic")
            state.actions.append(f"DEEP={'OK' if deep.ok else 'SKIP'}")
        self.tel.emit("verify", {
            "score": state.health_score, "delta": state.score_delta,
            "verify": state.verify_passed, "canary": state.canary_passed,
            "status": state.status,
        })
        state.findings = [asdict(f) for f in self.findings]
        state.status = _status_from(self.findings)
        return state

    def node_learn(self, state: AgentState) -> AgentState:
        _log("GRAPH/LEARN")
        self.board = Blackboard(
            root=state.root,
            cycle=state.cycle,
            status=state.status,
            findings=state.findings,
            actions=state.actions,
            recommendations=state.recommendations,
            tool_results=[{"name": t.name, "ok": t.ok, "message": t.message} for t in self.tools.history],
            knowledge_hits=state.knowledge_hits,
            memory_hits=self.memory.data.get("stats", {}).get("hits", 0),
            llm_used=state.llm_used,
            verify_passed=state.verify_passed,
            canary_passed=state.canary_passed,
            confidence_avg=state.confidence_avg,
            health_score=state.health_score,
            circuit_open=state.circuit_open,
            score_delta=state.score_delta,
        )
        SwarmOrchestrator(self.board).run()
        if state.status == "HEALTHY":
            cls_ok, _ = classify_incident(state.findings)
            ok_tools = [t.name for t in self.tools.history if t.ok]
            self.episodes.remember_success(cls_ok, ok_tools, state.health_score)
        rb = export_runbook(self.board, self.root)
        self.board.runbook_path = str(rb)
        state.actions.append(f"RUNBOOK={rb.name}")
        _persist_history(self.root, state)
        _write_state_md(self.root, state, self.board)
        sm = StateMachine()
        sm.checkpoint(state, self.root / "logs_supervisor" / "hermes_checkpoint.json")
        return state



def _write_state_md(root: Path, state: AgentState, board: Blackboard) -> None:
    lines = [
        f"# Hermes V10 STATE",
        f"status: **{state.status}**  score: {state.health_score}  cycle: {state.cycle}",
        f"verify: {state.verify_passed}  canary: {state.canary_passed}",
        "",
        "## Acções",
    ]
    for a in state.actions[:20]:
        lines.append(f"- {a}")
    path = root / "logs_supervisor" / "HERMES_STATE.md"
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def _persist_history(root: Path, state: AgentState) -> None:
    hist_path = root / "logs_supervisor" / "hermes_history.json"
    try:
        hist: List[Dict[str, Any]] = []
        if hist_path.exists():
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
            if not isinstance(hist, list):
                hist = []
        hist.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "cycle": state.cycle,
            "status": state.status,
            "score": state.health_score,
            "delta": state.score_delta,
            "verify": state.verify_passed,
            "canary": state.canary_passed,
            "circuit": state.circuit_open,
        })
        hist_path.write_text(json.dumps(hist[-80:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def run_cycle(root: Path, do_fix: bool, use_llm: bool, cycle: int = 1,
              extra_state: Optional[AgentState] = None) -> Blackboard:
    rt = HermesRuntime(root, do_fix, use_llm)
    sm = StateMachine()
    sm.register(Node.DETECT, rt.node_detect)
    sm.register(Node.DIAGNOSE, rt.node_diagnose)
    sm.register(Node.ACT, rt.node_act)
    sm.register(Node.VERIFY, rt.node_verify)
    sm.register(Node.LEARN, rt.node_learn)
    state = extra_state or AgentState(root=str(root), cycle=cycle, do_fix=do_fix, use_llm=use_llm)
    state.cycle = cycle
    state = sm.run_once(state)
    board = rt.board
    board.status = state.status
    board.circuit_open = state.circuit_open
    board.health_score = state.health_score
    board.score_delta = state.score_delta
    return board


def save_report(root: Path, board: Blackboard) -> Path:
    log_dir = root / "logs_supervisor"
    log_dir.mkdir(parents=True, exist_ok=True)
    latest = log_dir / "HERMES_AUTONOMOUS_LATEST.txt"
    lines = [
        "=" * 64,
        f"HERMES V{VERSION}  cycle={board.cycle}",
        f"Status: {board.status}  conf={board.confidence_avg:.0%}  score={board.health_score} Δ={board.score_delta:+d}",
        f"MemoryHits: {board.memory_hits}  LLM: {board.llm_used}  Circuit: {board.circuit_open}",
        f"Verify: {board.verify_passed}  Canary: {board.canary_passed}",
        f"KB: {', '.join(board.knowledge_hits) or '—'}",
        f"Runbook: {board.runbook_path}",
        f"Agents msgs: {len(board.messages)}",
        "=" * 64, "",
    ]
    by: Dict[str, List] = {}
    for f in board.findings:
        by.setdefault(f.get("sector", "?"), []).append(f)
    for sec, items in by.items():
        lines.append(f"--- {sec.upper()} ---")
        for f in items:
            mark = "FIXED" if f.get("fixed") else f.get("severity")
            lines.append(f"  [{mark:8}] {f.get('code')}: {f.get('message')}")
        lines.append("")
    if board.actions:
        lines.append("--- AÇÕES / TOOLS ---")
        lines.extend(f"  · {a}" for a in board.actions)
        lines.append("")
    if board.recommendations:
        lines.append("--- RECOMENDAÇÕES ---")
        lines.extend(f"  · {r}" for r in board.recommendations)
        lines.append("")
    if board.messages:
        lines.append("--- SWARM MESSAGES ---")
        for m in board.messages:
            lines.append(f"  {m.get('from_agent')}→{m.get('to_agent')} [{m.get('kind')}]")
        lines.append("")
    lines.append("=" * 64)
    text = "\n".join(lines)
    latest.write_text(text, encoding="utf-8")
    (log_dir / "HERMES_AUTONOMOUS_LATEST.json").write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return latest


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Hermes V{VERSION}")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int)
    ap.add_argument("--supervise", action="store_true",
                    help="loop infinito com intervalo adaptativo (supervisor)")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--root", type=str)
    ap.add_argument("--max-cycles", type=int, default=25)
    args = ap.parse_args()

    root = _find_root(args.root)
    if not (root / "engine" / "server.py").exists():
        _log(f"[ERRO] sem engine/server.py em {root}")
        return 2

    tools = ToolRegistry(root)
    lock = tools.run("acquire_lock")
    if not lock.ok and args.supervise:
        _log(f"[LOCK] {lock.message}")
        return 3

    def one(c: int) -> Blackboard:
        extra = None
        try:
            sm0 = StateMachine()
            extra = sm0.load_checkpoint(root / "logs_supervisor" / "hermes_checkpoint.json")
            if extra:
                extra.cycle = c
                extra.do_fix = args.fix
                extra.use_llm = args.llm
                extra.findings = []
                extra.actions = []
                extra.recommendations = []
                extra.history = []
        except Exception:
            extra = None
        board = run_cycle(root, args.fix, args.llm, c, extra_state=extra)
        path = save_report(root, board)
        _log(f"Status: {board.status} score={board.health_score}")
        print()
        print(path.read_text(encoding="utf-8", errors="replace"))
        return board

    try:
        if args.supervise:
            c = 0
            while True:
                c += 1
                b = one(c)
                if b.circuit_open:
                    _log("CIRCUIT OPEN — a pausar 5 min")
                    time.sleep(300)
                    continue
                sleep_s = 90 if b.status == "HEALTHY" else 45 if b.status == "DEGRADED" else 20
                time.sleep(sleep_s)
        if args.loop:
            streak = 0
            crit = 0
            for c in range(1, max(2, args.max_cycles) + 1):
                b = one(c)
                if b.status == "HEALTHY":
                    streak += 1
                    crit = 0
                else:
                    streak = 0
                    crit += 1 if b.status == "CRITICAL" else 0
                if streak >= 2:
                    _log("2× HEALTHY — estável")
                    break
                if b.circuit_open or crit >= 5:
                    _log("circuit breaker — a sair")
                    return 4
                time.sleep(max(15, args.loop))
            return 0
        b = one(1)
        return 0 if b.status == "HEALTHY" else 1
    finally:
        tools.run("release_lock")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
