"""CLI: status | grant-session | revoke | submit | list-queue"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from .config import TelegramIntelConfig
from .dispatch import Dispatch
from .policy_gate import PolicyGate
from .dispatch import default_paths


def main():
    p = argparse.ArgumentParser(description="AURA Telegram Intel — policy dispatch")
    p.add_argument("--status", action="store_true")
    p.add_argument("--grant-session", action="store_true", help="Open auto-publish window")
    p.add_argument("--revoke-session", action="store_true")
    p.add_argument("--operator-token", type=str, default="")
    p.add_argument("--hours", type=float, default=None)
    p.add_argument("--submit", type=str, default="", help="Raw text tip")
    p.add_argument("--list-pending", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.dry_run:
        os.environ["AURA_TELEGRAM_DRY_RUN"] = "1"

    cfg = TelegramIntelConfig.from_env()
    paths = default_paths(Path(os.environ.get("AURA_ROOT", "C:/aura")))
    policy_path = paths["policy"]
    if not policy_path.exists():
        policy_path = Path(__file__).resolve().parents[2] / "config" / "operator_publish_policy.example.json"
    gate = PolicyGate(policy_path, paths["state"])

    if args.grant_session:
        expected = os.environ.get("AURA_TELEGRAM_OPERATOR_TOKEN", "")
        print(json.dumps(gate.grant_session(args.operator_token, expected, args.hours), ensure_ascii=False))
        return
    if args.revoke_session:
        print(json.dumps(gate.revoke_session(), ensure_ascii=False))
        return
    if args.list_pending:
        d = Dispatch(Path(os.environ.get("AURA_ROOT", "C:/aura")))
        print(json.dumps(d.queue.list("pending")[:50], ensure_ascii=False, indent=2))
        return
    if args.submit:
        d = Dispatch(Path(os.environ.get("AURA_ROOT", "C:/aura")))
        print(json.dumps(d.submit(args.submit, use_template="generic"), ensure_ascii=False, indent=2))
        return

    # status
    print(json.dumps({
        "telegram_enabled": cfg.enabled,
        "dry_run": cfg.dry_run,
        "kill_switch": gate.kill_switch_on(),
        "policy_enabled": gate.policy.get("enabled"),
        "auto_publish": (gate.policy.get("auto_publish") or {}).get("enabled"),
        "session_until": gate.session_until,
        "counters": {
            "hour": gate.counters.hour_count,
            "day": gate.counters.day_count,
        },
        "ready_to_publish": cfg.ready_to_publish(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
