"""Dispatch: policy → auto_send | queue | block. Never bypasses kill switch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import TelegramIntelConfig
from .policy_gate import PolicyGate
from .publisher import TelegramPublisher
from .queue_store import TipQueue
from .templates import tip_corners_paper, tip_generic_paper


def default_paths(root: Path | None = None) -> dict[str, Path]:
    root = root or Path("C:/aura")
    return {
        "policy": root / "config" / "operator_publish_policy.json",
        "state": root / "data" / "telegram_intel" / "policy_state.json",
        "queue": root / "data" / "telegram_intel" / "tip_queue.json",
    }


class Dispatch:
    def __init__(self, root: Path | None = None):
        paths = default_paths(root)
        # fallback to addon example if operator file missing
        policy = paths["policy"]
        if not policy.exists():
            alt = Path(__file__).resolve().parents[2] / "config" / "operator_publish_policy.example.json"
            policy = alt if alt.exists() else policy
        self.gate = PolicyGate(policy, paths["state"])
        self.queue = TipQueue(paths["queue"])
        self.pub = TelegramPublisher(TelegramIntelConfig.from_env())

    def submit(self, text: str | None = None, meta: dict[str, Any] | None = None, use_template: str = "generic") -> dict[str, Any]:
        meta = dict(meta or {})
        if use_template == "corners":
            msg = tip_corners_paper(meta)
        else:
            msg = tip_generic_paper(text or "", meta)

        decision = self.gate.evaluate(msg, meta)
        d = decision.get("decision")
        if d == "block":
            iid = self.queue.enqueue(msg, meta, status="blocked")
            return {"ok": False, "decision": "block", "reason": decision.get("reason"), "queue_id": iid}
        if d == "queue":
            iid = self.queue.enqueue(msg, meta, status="pending")
            return {"ok": True, "decision": "queue", "reason": decision.get("reason"), "queue_id": iid}
        # auto_send
        result = self.pub.send_message(msg)
        if result.get("ok") and result.get("side_effect"):
            self.gate.record_send()
            iid = self.queue.enqueue(msg, meta, status="sent")
        elif result.get("ok") and result.get("reason") == "dry_run":
            iid = self.queue.enqueue(msg, meta, status="dry_run")
        else:
            iid = self.queue.enqueue(msg, meta, status="failed")
        return {"ok": result.get("ok"), "decision": "auto_send", "publish": result, "queue_id": iid, "reason": decision.get("reason")}
