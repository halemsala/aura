#!/usr/bin/env python3
"""
monitor_bsd_divergences.py — Monitora divergências SokkerPro vs BSD.

Lê data/bsd_vs_sokkerpro.jsonl e gera resumo + alerta.
Uso:
  python scripts/monitor_bsd_divergences.py
  python scripts/monitor_bsd_divergences.py --last 50
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "bsd_vs_sokkerpro.jsonl"
REPORT = ROOT / "data" / "bsd_divergence_report.json"

def load_entries(limit: int = 200):
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries

def analyze(entries):
    if not entries:
        return {
            "status": "no_data",
            "total": 0,
            "corner_mismatches": 0,
            "minute_mismatches": 0,
            "score_mismatches": 0,
            "samples": [],
        }
    corner_mm = 0
    minute_mm = 0
    score_mm = 0
    samples = []
    for e in entries:
        sc_h = e.get("sokker_corners_h")
        bc_h = e.get("bsd_corners_h")
        sc_a = e.get("sokker_corners_a")
        bc_a = e.get("bsd_corners_a")
        if sc_h is not None and bc_h is not None and int(sc_h) != int(bc_h):
            corner_mm += 1
        if sc_a is not None and bc_a is not None and int(sc_a) != int(bc_a):
            corner_mm += 1
        if e.get("sokker_minute") is not None and e.get("bsd_minute") is not None:
            if abs(int(e["sokker_minute"]) - int(e["bsd_minute"])) > 2:
                minute_mm += 1
        if e.get("sokker_score") and e.get("bsd_score") and e["sokker_score"] != e["bsd_score"]:
            score_mm += 1
        samples.append({
            "ts": e.get("ts"),
            "match": f"{e.get('home')} x {e.get('away')}",
            "sokker_corners": f"{sc_h}-{sc_a}",
            "bsd_corners": f"{bc_h}-{bc_a}",
        })
    return {
        "status": "ok",
        "total": len(entries),
        "corner_mismatches": corner_mm,
        "minute_mismatches": minute_mm,
        "score_mismatches": score_mm,
        "mismatch_rate": round(corner_mm / max(1, len(entries)), 3),
        "samples": samples[-10:],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=200)
    args = ap.parse_args()
    entries = load_entries(args.last)
    report = analyze(entries)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "no_data":
        print("\n[INFO] Ainda não há divergências registadas. O conector BSD regista quando é chamado.")
    elif report["corner_mismatches"] > 0:
        print(f"\n[ALERT] {report['corner_mismatches']} divergências de corners em {report['total']} amostras")
    else:
        print("\n[OK] Sem divergências significativas de corners")

if __name__ == "__main__":
    main()
