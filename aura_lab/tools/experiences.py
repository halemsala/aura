#!/usr/bin/env python3
"""Memória de experiências AURA LAB (não é treino de LLM).

Arquivo: records/experiences.jsonl
Cada linha = um episódio: o que viu, FM, se verificou, notas.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "records" / "experiences.jsonl"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_experience(
    *,
    path: Path | None = None,
    source: str,
    phase: str,
    offline: list[str] | None = None,
    failure_mode_id: str | None = None,
    title: str | None = None,
    symptom: str | None = None,
    proposed_repair: list[str] | None = None,
    official_tools: list[str] | None = None,
    verified: bool | None = None,
    notes: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = path or DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "id": f"exp-{int(time.time())}-{uuid.uuid4().hex[:8]}",
        "ts": _utc(),
        "source": source,
        "phase": phase,
        "offline": offline or [],
        "failure_mode_id": failure_mode_id,
        "title": title,
        "symptom": symptom,
        "proposed_repair": proposed_repair or [],
        "official_tools": official_tools or [],
        "verified": verified,
        "notes": notes,
        "extra": extra or {},
        "policy": {"paper_trade": True, "auto_repair": False, "advisory": True},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_experiences(path: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = path or DEFAULT_PATH
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def summarize_experiences(path: Path | None = None, limit: int = 30) -> str:
    rows = load_experiences(path, limit=limit)
    if not rows:
        return (
            "Nenhuma experiência registrada ainda.\n"
            "Rode: python tools/ops_loop.py  ou  python tools/ops_daemon.py --once\n"
            "Arquivo: records/experiences.jsonl"
        )
    by_fm: dict[str, int] = {}
    verified_ok = 0
    verified_fail = 0
    for r in rows:
        fid = r.get("failure_mode_id") or "none"
        by_fm[fid] = by_fm.get(fid, 0) + 1
        if r.get("verified") is True:
            verified_ok += 1
        elif r.get("verified") is False:
            verified_fail += 1
    lines = [
        "══ AURA — memória de experiências (advisory) ══",
        f"Últimos episódios lidos: {len(rows)}",
        f"verified_ok={verified_ok}  verified_fail={verified_fail}  (auto_repair=OFF)",
        "Por FM:",
    ]
    for fid, n in sorted(by_fm.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  · {fid}: {n}")
    lines.append("Recentes:")
    for r in rows[-8:]:
        lines.append(
            f"  [{r.get('ts')}] {r.get('failure_mode_id') or '-'} "
            f"phase={r.get('phase')} offline={r.get('offline')} "
            f"verified={r.get('verified')}"
        )
    lines.append("Isto alimenta o operador/Harness com histórico — não treina pesos de LLM.")
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.json:
        print(json.dumps(load_experiences(limit=args.limit), ensure_ascii=False, indent=2))
    else:
        print(summarize_experiences(limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
