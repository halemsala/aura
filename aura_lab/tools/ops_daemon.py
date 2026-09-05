#!/usr/bin/env python3
"""
Daemon de observação AURA (automação segura).

- A cada N segundos: snapshot + ops_loop
- Grava lab_failures.jsonl + experiences.jsonl
- NÃO executa BAT/recovery (auto_repair sempre off neste módulo)

Uso:
  python tools/ops_daemon.py --once
  python tools/ops_daemon.py --interval 120
  python tools/ops_daemon.py --interval 60 --symptom ""

Windows (sessão atual):
  python tools\\ops_daemon.py --interval 180
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from experiences import append_experience  # noqa: E402
from ops_loop import format_ops_report, run_loop  # noqa: E402

_STOP = False


def _handle_sig(_sig, _frame) -> None:
    global _STOP
    _STOP = True


def tick(symptom: str = "", quiet: bool = False) -> dict:
    result = run_loop(symptom, record=True, wait_verify_s=0.0)
    fm = result.get("failure_mode") or {}
    offline = (result.get("snapshot_before") or {}).get("offline") or []
    phase = result.get("phase") or "unknown"
    # Só grava experiência se houver algo relevante (não spamar healthy a cada tick)
    if phase != "healthy" or symptom.strip():
        append_experience(
            source="ops_daemon",
            phase=phase,
            offline=list(offline),
            failure_mode_id=(fm or {}).get("id"),
            title=(fm or {}).get("title"),
            symptom=symptom or None,
            proposed_repair=list(result.get("proposed_repair") or []),
            official_tools=list(result.get("official_tools") or []),
            verified=result.get("verified"),
            notes="daemon tick; auto_repair=off",
            extra={"match_reason": result.get("match_reason"), "record_id": result.get("record_id")},
        )
    elif not quiet:
        # heartbeat mínimo: uma linha em stderr
        print(f"[{time.strftime('%H:%M:%S')}] healthy offline={offline}", flush=True)
    if not quiet and phase != "healthy":
        print(format_ops_report(result), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA ops daemon (observe + memory, no auto-repair)")
    parser.add_argument("--interval", type=int, default=120, help="segundos entre ticks (default 120)")
    parser.add_argument("--once", action="store_true", help="um único tick e sai")
    parser.add_argument("--symptom", default="", help="sintoma fixo opcional em todo tick")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_sig)
    try:
        signal.signal(signal.SIGTERM, _handle_sig)
    except Exception:
        pass

    print(
        "AURA ops_daemon — só observação + memória. auto_repair=OFF. Ctrl+C para parar.",
        flush=True,
    )
    if args.once:
        tick(args.symptom, quiet=args.quiet)
        return 0

    interval = max(30, int(args.interval))
    while not _STOP:
        try:
            tick(args.symptom, quiet=args.quiet)
        except Exception as exc:
            print(f"[ops_daemon] erro no tick: {exc}", flush=True)
        # sleep em fatias para reagir ao Ctrl+C
        for _ in range(interval):
            if _STOP:
                break
            time.sleep(1)
    print("ops_daemon encerrado.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
