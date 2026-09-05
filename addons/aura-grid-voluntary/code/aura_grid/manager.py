"""AURA Grid Manager — read/watch grid_status.json (temps, power, util)."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .status_registry import format_status_table


def load_status(path: str | Path | None = None) -> dict:
    p = Path(path or os.environ.get("AURA_GRID_STATUS_FILE", "grid_status.json"))
    if not p.is_file():
        return {"updated_at": None, "master": {}, "workers": [], "worker_count": 0, "online_count": 0, "error": f"missing {p}"}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="AURA Grid terminal monitor")
    ap.add_argument("--file", default=os.environ.get("AURA_GRID_STATUS_FILE", "grid_status.json"))
    ap.add_argument("--watch", type=float, default=0, help="Refresh seconds (0 = once)")
    ap.add_argument("--json", action="store_true", help="Print raw JSON")
    args = ap.parse_args()
    while True:
        snap = load_status(args.file)
        if args.json:
            print(json.dumps(snap, indent=2, ensure_ascii=False))
        else:
            print(format_status_table(snap))
            print()
        if args.watch <= 0:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
