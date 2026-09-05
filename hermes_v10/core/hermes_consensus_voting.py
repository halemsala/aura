#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-agent consensus voting (Team of Rivals) — rule + optional LLM voters."""
from __future__ import annotations
import hashlib, json, os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional

@dataclass
class Vote:
    agent: str
    decision: str  # APPROVE | REJECT | ESCALATE
    rationale: str
    confidence: float
    signature: str

@dataclass
class ConsensusResult:
    decision: str
    tally: Dict[str, int]
    divergence: float
    votes: List[Vote]

def _rule_voter(name: str, payload: dict, payload_hash: str) -> Vote:
    action = str(payload.get("action", "")).lower()
    # hard rejects
    if action in ("set_execution_true", "enable_execution", "disable_paper_trade"):
        d, r, c = "REJECT", "forbidden by policy", 1.0
    elif "execution_allowed" in json.dumps(payload).lower() and "true" in json.dumps(payload).lower():
        d, r, c = "REJECT", "execution_allowed true", 0.95
    elif action in ("fix_desktop_json", "domain_lock", "rotate_logs", "status"):
        d, r, c = "APPROVE", "allowlisted paper-safe", 0.85
    else:
        d, r, c = "ESCALATE", "unknown action", 0.5
    sig = hashlib.sha256(f"{name}{d}{payload_hash}".encode()).hexdigest()[:16]
    return Vote(name, d, r, c, sig)

class ConsensusVoting:
    def __init__(self, quorum: int = 3, agreement_threshold: float = 0.67, escalation_divergence: float = 0.34):
        self.quorum = quorum
        self.agreement_threshold = agreement_threshold
        self.escalation_divergence = escalation_divergence

    def decide(self, payload: dict, agent_runners: Optional[List[tuple]] = None) -> ConsensusResult:
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()
        votes: List[Vote] = []
        # default rule rivals
        for name in ("policy_a", "policy_b", "policy_c")[: max(self.quorum, 3)]:
            votes.append(_rule_voter(name, payload, payload_hash))
        # optional external runners: (name, callable(payload)->Vote|dict)
        for item in agent_runners or []:
            name, runner = item[0], item[1]
            try:
                out = runner(payload)
                if isinstance(out, Vote):
                    votes.append(out)
                elif isinstance(out, dict):
                    votes.append(Vote(
                        name, out.get("decision", "ESCALATE"), out.get("rationale", ""),
                        float(out.get("confidence", 0.5)),
                        hashlib.sha256(f"{name}{out.get('decision')}{payload_hash}".encode()).hexdigest()[:16],
                    ))
            except Exception as e:
                votes.append(Vote(name, "ESCALATE", str(e), 0.0, "ERR"))

        tally = {"APPROVE": 0, "REJECT": 0, "ESCALATE": 0}
        for v in votes:
            tally[v.decision] = tally.get(v.decision, 0) + 1
        total = max(len(votes), 1)
        approve_ratio = tally["APPROVE"] / total
        reject_ratio = tally["REJECT"] / total
        divergence = 1.0 - max(approve_ratio, reject_ratio)
        if divergence >= self.escalation_divergence:
            decision = "ESCALATE_HITL"
        elif approve_ratio >= self.agreement_threshold:
            decision = "APPROVED"
        elif reject_ratio >= self.agreement_threshold:
            decision = "REJECTED"
        else:
            decision = "ESCALATE_HITL"
        return ConsensusResult(decision, tally, round(divergence, 3), votes)

if __name__ == "__main__":
    cv = ConsensusVoting()
    print(asdict(cv.decide({"action": "domain_lock", "args": {}})))
    print(asdict(cv.decide({"action": "set_execution_true"})))
