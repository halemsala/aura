#!/usr/bin/env python3
"""CLI do gate de conhecimento: nenhuma aprovação é automática."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import knowledge_review_gate as gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Revisão humana do conhecimento candidato AURA")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    pending = sub.add_parser("pending")
    pending.add_argument("--limit", type=int, default=20)
    for name in ("approve", "reject"):
        command = sub.add_parser(name)
        command.add_argument("candidate_id")
        command.add_argument("--reviewer", required=True)
        command.add_argument("--note", required=True)
        command.add_argument("--validation-reference", default="")
    context = sub.add_parser("context")
    context.add_argument("query", nargs="?", default="")
    context.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    if args.command == "status":
        result = gate.status()
    elif args.command == "pending":
        result = {"items": gate.pending(args.limit), "status": gate.status()}
    elif args.command == "context":
        result = gate.context(args.query, args.limit)
    else:
        result = gate.decide(args.candidate_id, args.reviewer, args.command, args.note, args.validation_reference)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
