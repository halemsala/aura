#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Policy V7 — invariantes paper-trade. Nunca promove live."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


VERSION = "7.0.0"
INVARIANTS = {
    "PAPER_TRADE": "true",
    "EXECUTION_ALLOWED": "false",
    "GLM_ADVISORY_ONLY": "true",
}


@dataclass
class PolicySnapshot:
    paper_trade: str = "true"
    execution_allowed: str = "false"
    glm_advisory_only: str = "true"
    enforced_at: str = ""
    root: str = ""

    def ok(self) -> bool:
        return (
            self.paper_trade.lower() == "true"
            and self.execution_allowed.lower() == "false"
            and self.glm_advisory_only.lower() == "true"
        )


class PolicyGuard:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "logs_supervisor" / "hermes_policy.json"

    def enforce_env(self) -> PolicySnapshot:
        for k, v in INVARIANTS.items():
            os.environ[k] = v
        snap = PolicySnapshot(
            paper_trade=os.environ.get("PAPER_TRADE", "true"),
            execution_allowed=os.environ.get("EXECUTION_ALLOWED", "false"),
            glm_advisory_only=os.environ.get("GLM_ADVISORY_ONLY", "true"),
            enforced_at=datetime.now(timezone.utc).isoformat(),
            root=str(self.root),
        )
        self._persist(snap)
        return snap

    def current(self) -> PolicySnapshot:
        return PolicySnapshot(
            paper_trade=os.environ.get("PAPER_TRADE", "unset"),
            execution_allowed=os.environ.get("EXECUTION_ALLOWED", "unset"),
            glm_advisory_only=os.environ.get("GLM_ADVISORY_ONLY", "unset"),
        )

    def _persist(self, snap: PolicySnapshot) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload: Dict = asdict(snap)
            payload["version"] = VERSION
            payload["note"] = "Hermes never flips execution_allowed to true"
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
