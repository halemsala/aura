#!/usr/bin/env python3
"""Append seguro de registros do AURA LAB (jsonl). Não aplica reparo."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = ROOT / "records" / "lab_failures.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_record(
    path: Path,
    *,
    failure_mode_id: str,
    phase: str,
    observed: dict[str, Any] | None = None,
    diagnosis: str | None = None,
    proposed_repair: list[str] | None = None,
    plan_id: str | None = None,
    notes: str = "",
    operator: str = "human",
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "record_id": f"lab-{int(time.time())}-{uuid.uuid4().hex[:8]}",
        "timestamp_utc": utc_now(),
        "failure_mode_id": failure_mode_id,
        "phase": phase,
        "observed": observed or {},
        "diagnosis": diagnosis,
        "proposed_repair": proposed_repair or [],
        "plan_id": plan_id,
        "applied": False,
        "verified": None,
        "advisory_only": True,
        "lab_mode": True,
        "notes": notes,
        "operator": operator,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA LAB record writer")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--fm-id", required=True, help="ex.: FM-ENGINE-001")
    parser.add_argument("--phase", default="diagnosed")
    parser.add_argument("--diagnosis", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--symptom", default="")
    args = parser.parse_args()

    observed = {"symptom_text": args.symptom} if args.symptom else {}
    rec = append_record(
        args.records,
        failure_mode_id=args.fm_id,
        phase=args.phase,
        observed=observed,
        diagnosis=args.diagnosis or None,
        notes=args.notes,
    )
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
