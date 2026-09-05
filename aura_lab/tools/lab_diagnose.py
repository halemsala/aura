#!/usr/bin/env python3
"""
AURA LAB — lab_diagnose

Sintoma (texto) + snapshot HTTP opcional → match no catálogo → diagnóstico
estruturado → registro em lab_failures.jsonl.

Somente advisory. Não aplica reparo. Não muta o AURA de uso.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_loader import load_yaml, match_symptom, validate_catalog  # noqa: E402
from record_writer import append_record  # noqa: E402
from snapshot import collect_snapshot, offline_services, snapshot_hints  # noqa: E402

DEFAULT_CATALOG = ROOT / "catalog" / "failure_modes_v1.yaml"
DEFAULT_RECORDS = ROOT / "records" / "lab_failures.jsonl"


def format_report(
    symptom: str,
    snapshot: dict[str, Any] | None,
    hits: list[tuple[float, dict]],
) -> str:
    lines: list[str] = []
    lines.append("══ AURA LAB — diagnóstico (advisory) ══")
    lines.append(f"Sintoma: {symptom or '(somente snapshot)'}")
    if snapshot:
        offline = offline_services(snapshot)
        lines.append(f"Snapshot: {snapshot.get('timestamp')}")
        for name, item in (snapshot.get("services") or {}).items():
            st = "ONLINE" if item.get("online") else "OFFLINE"
            lat = "-"
            health = item.get("health") or {}
            if item.get("online") and health.get("latency_ms") is not None:
                lat = f"{health.get('latency_ms')}ms"
            lines.append(f"  · {name:7} {st:7} porta={item.get('port')} lat={lat}")
        if offline:
            lines.append(f"Offline: {', '.join(offline)}")
        else:
            lines.append("Offline: (nenhum pelo TCP/health básico)")
        lines.append(f"Policy: paper_trade={snapshot.get('policy', {}).get('paper_trade')} "
                     f"execution_allowed={snapshot.get('policy', {}).get('execution_allowed')}")
    lines.append("")

    if not hits:
        lines.append("FM_ID: (nenhum match)")
        lines.append("PROXIMO: aguarda")
        lines.append("Diagnóstico: sem modo de falha correspondente no catálogo.")
        lines.append("Colete: status dos serviços, log runtime_*, /api/ui/state, sintoma mais específico.")
        return "\n".join(lines)

    best_score, best = hits[0]
    lines.append(f"FM_ID: {best.get('id')}")
    lines.append(f"SEVERIDADE: {best.get('severity')}")
    lines.append(f"SERVICO: {best.get('service')}")
    lines.append(f"TITULO: {best.get('title')}")
    lines.append(f"MATCH_SCORE: {best_score:.1f}")
    lines.append("DIAGNOSTICO:")
    lines.append(f"  {best.get('symptom')}")
    causes = best.get("likely_causes") or []
    if causes:
        lines.append("CAUSAS_PROVAVEIS:")
        for c in causes:
            lines.append(f"  - {c}")
    steps = best.get("repair_steps") or []
    lines.append("PASSOS:")
    for i, step in enumerate(steps, 1):
        lines.append(f"  {i}. {step}")
    verify = best.get("verify") or []
    lines.append("VERIFICAR:")
    for v in verify:
        lines.append(f"  - {v}")
    tools = best.get("official_tools") or []
    if tools:
        lines.append("FERRAMENTAS_OFICIAIS: " + ", ".join(tools))
    lab = "sim (só LAB)" if best.get("lab_safe") else "não — só documentar/diagnosticar"
    lines.append(f"INJECAO_LAB: {lab}")
    lines.append("PROXIMO: advisory")
    if len(hits) > 1:
        lines.append("")
        lines.append("Outros candidatos:")
        for score, m in hits[1:]:
            lines.append(f"  [{score:.1f}] {m.get('id')} — {m.get('title')}")
    lines.append("")
    lines.append("Nada foi alterado no sistema. Mutação real exige plano Harness + CONFIRMAR.")
    return "\n".join(lines)


def build_query(symptom: str, snapshot: dict[str, Any] | None) -> str:
    parts = [symptom.strip()] if symptom else []
    if snapshot:
        parts.extend(snapshot_hints(snapshot))
    return " ".join(p for p in parts if p)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AURA LAB diagnose — advisory only",
    )
    parser.add_argument(
        "symptom",
        nargs="?",
        default="",
        help="Sintoma em texto livre (opcional se --snapshot)",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Coletar health TCP/HTTP local (8080/8765/8099/11434)",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Não gravar em lab_failures.jsonl",
    )
    parser.add_argument("--json", action="store_true", help="Saída JSON")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if not args.symptom and not args.snapshot:
        parser.error("informe um sintoma e/ou --snapshot")

    if not args.catalog.is_file():
        print(f"ERRO: catálogo ausente: {args.catalog}", file=sys.stderr)
        return 2

    data = load_yaml(args.catalog)
    modes, errors = validate_catalog(data)
    if errors:
        print("Catálogo inválido:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    snapshot = collect_snapshot() if args.snapshot else None
    query = build_query(args.symptom, snapshot)
    hits = match_symptom(modes, query, limit=max(1, args.limit))

    report = format_report(args.symptom, snapshot, hits)
    best = hits[0][1] if hits else None

    record = None
    if not args.no_record:
        observed: dict[str, Any] = {"symptom_text": args.symptom or query}
        if snapshot:
            observed["services"] = {
                k: {"online": v.get("online"), "port": v.get("port")}
                for k, v in (snapshot.get("services") or {}).items()
            }
            observed["offline"] = offline_services(snapshot)
        record = append_record(
            args.records,
            failure_mode_id=(best or {}).get("id") or "FM-UNKNOWN-000",
            phase="diagnosed" if best else "detected",
            observed=observed,
            diagnosis=(best or {}).get("title"),
            proposed_repair=list((best or {}).get("repair_steps") or []),
            notes="lab_diagnose CLI",
            operator="lab_diagnose",
        )

    if args.json:
        payload = {
            "query": query,
            "snapshot": snapshot,
            "matches": [
                {
                    "score": s,
                    "id": m.get("id"),
                    "title": m.get("title"),
                    "severity": m.get("severity"),
                    "service": m.get("service"),
                    "repair_steps": m.get("repair_steps"),
                    "verify": m.get("verify"),
                    "official_tools": m.get("official_tools"),
                    "lab_safe": m.get("lab_safe"),
                }
                for s, m in hits
            ],
            "record_id": (record or {}).get("record_id"),
            "advisory_only": True,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(report)
        if record:
            print(f"Registro: {record.get('record_id')} → {args.records}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
