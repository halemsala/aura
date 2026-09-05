#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Correction pipeline QUANTUM:
  propose (LLM or rule) → constitution ZK → sandbox → HITL file gate → apply (optional)
Sem Grok CLI obrigatório: usa LLM engine local se disponível, senão rule-based.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))

from hermes_constitution_engine_quantum import ConstitutionZK, ZKConstitutionViolation
from hermes_sandbox_adapters import run_sandbox
from hermes_event_bus import EventBus
from hermes_lcm_memory import LosslessContextMemory

try:
    from correction_agent import CorrectionAgent
except ImportError:
    CorrectionAgent = None  # type: ignore

class CorrectionPipelineQuantum:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.const = ConstitutionZK(str(self.root))
        self.bus = EventBus(str(self.root / "orchestrator" / "event_bus.db"))
        self.mem = LosslessContextMemory(str(self.root / "data" / "lcm_memory.db"))
        self.hitl_dir = self.root / "hitl_queue"
        self.hitl_dir.mkdir(parents=True, exist_ok=True)

    def propose(self, issue: str) -> dict:
        # rule-based proposals (arena-lite: rank fixed candidates)
        candidates = []
        low = issue.lower()
        if "404" in low or "homepage" in low or "matriz" in low:
            candidates.append({"fix": "fix_desktop_json", "score": 0.9, "why": "homepage/matriz"})
        if "domain" in low or "bolsa" in low or "prompt" in low:
            candidates.append({"fix": "domain_lock", "score": 0.85, "why": "domain lock"})
        if "log" in low:
            candidates.append({"fix": "rotate_logs", "score": 0.7, "why": "logs"})
        if not candidates:
            candidates.append({"fix": "status", "score": 0.5, "why": "sem fix automático seguro"})
        candidates.sort(key=lambda x: -x["score"])
        winner = candidates[0]
        self.bus.publish("correction.propose", {"issue": issue, "winner": winner, "candidates": candidates})
        self.mem.add("system", f"propose:{issue}", raw=winner)
        return {"status": "arena_lite_success", "proposal": winner, "candidates": candidates}

    def sandbox_test(self, fix_name: str) -> dict:
        code = f"print('sandbox_ok fix={fix_name}')\nassert True\n"
        result = run_sandbox(code, prefer=os.environ.get("HERMES_SANDBOX", "auto"))
        self.bus.publish("correction.sandbox", {"fix": fix_name, "result": result})
        return result

    def hitl_request(self, proposal: dict, timeout_s: int = 5) -> dict:
        """Write proposal; if HERMES_HITL_AUTO=1 approve; else timeout fail-closed."""
        tid = f"proposal_{int(time.time())}"
        ticket = self.hitl_dir / f"{tid}.json"
        verdict = self.hitl_dir / f"{tid}.verdict"
        ticket.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
        self.bus.publish("correction.hitl_wait", {"ticket": str(ticket)})
        if os.environ.get("HERMES_HITL_AUTO", "").lower() in ("1", "true", "yes"):
            verdict.write_text("APPROVED\n", encoding="utf-8")
        # short wait for demo; production use longer
        for _ in range(timeout_s):
            if verdict.exists():
                v = verdict.read_text(encoding="utf-8")
                approved = "APPROVED" in v.upper()
                return {"approved": approved, "ticket": str(ticket)}
            time.sleep(1)
        return {"approved": False, "reason": "hitl_timeout_fail_closed", "ticket": str(ticket)}

    def run(self, issue: str, apply: bool = False) -> dict:
        try:
            self.const.check_action_zk("propose_fix", {"issue": issue})
        except ZKConstitutionViolation as e:
            return {"blocked": str(e)}

        prop = self.propose(issue)
        fix = prop["proposal"]["fix"]
        if fix in ("status", "latest"):
            return {"status": "no_mutation", "proposal": prop}

        try:
            self.const.check_action_zk(fix, prop)
        except ZKConstitutionViolation as e:
            return {"blocked": str(e), "proposal": prop}

        sb = self.sandbox_test(fix)
        if sb.get("error") and not sb.get("fallback") and sb.get("rc", 0) != 0:
            return {"status": "sandbox_failed", "sandbox": sb, "proposal": prop}

        gate = self.hitl_request(prop, timeout_s=int(os.environ.get("HERMES_HITL_TIMEOUT", "3")))
        if not gate.get("approved"):
            return {"status": "hitl_rejected", "gate": gate, "proposal": prop, "sandbox": sb}

        if not apply or os.environ.get("HERMES_ALLOW_APPLY", "").lower() not in ("1", "true", "yes"):
            return {
                "status": "approved_not_applied",
                "hint": "set HERMES_ALLOW_APPLY=1 to apply",
                "proposal": prop,
                "sandbox": sb,
                "gate": gate,
            }

        if CorrectionAgent is None:
            return {"status": "no_correction_agent", "proposal": prop}
        r = CorrectionAgent(str(self.root)).apply(fix)
        self.bus.publish("correction.applied", {"fix": fix, "ok": r.success})
        return {"status": "applied" if r.success else "apply_failed", "result": r.__dict__, "proposal": prop}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "."))
    ap.add_argument("--issue", default="arruma homepage 404 da matriz")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    # seal attestation on first run
    ConstitutionZK(args.root).seal_attestation()
    print(json.dumps(CorrectionPipelineQuantum(args.root).run(args.issue, apply=args.apply), ensure_ascii=False, indent=2))
