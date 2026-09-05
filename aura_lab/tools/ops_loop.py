#!/usr/bin/env python3
"""
AURA LAB — loop operacional (produtividade)

detectar OFF/anomalia → match FM → propor recovery oficial → (opcional) verificar de novo

Somente advisory por padrão.
Nunca executa BAT/recovery sozinho: imprime o comando oficial e exige Harness CONFIRMAR
se o operador for aplicar mutação.

Uso:
  python3 tools/ops_loop.py
  python3 tools/ops_loop.py --json
  python3 tools/ops_loop.py --symptom "painel nao abriu"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from catalog_loader import load_yaml, match_symptom, validate_catalog  # noqa: E402
from record_writer import append_record  # noqa: E402
from snapshot import collect_snapshot, offline_services, snapshot_hints  # noqa: E402

DEFAULT_CATALOG = ROOT / "catalog" / "failure_modes_v1.yaml"
DEFAULT_RECORDS = ROOT / "records" / "lab_failures.jsonl"

# Mapeamento serviço offline → FM prioritário
SERVICE_FM = {
    "engine": "FM-ENGINE-001",
    "bridge": "FM-BRIDGE-001",
    "voice": "FM-VOICE-001",
    "ollama": "FM-OLLAMA-001",
}


def _modes_by_id(modes: list[dict]) -> dict[str, dict]:
    return {m["id"]: m for m in modes if m.get("id")}


def _pick_fm(
    modes: list[dict],
    offline: list[str],
    symptom: str,
) -> tuple[dict | None, str]:
    by_id = _modes_by_id(modes)
    # 1) sintoma do operador
    if symptom.strip():
        hits = match_symptom(modes, symptom, limit=5)
        if hits:
            return hits[0][1], "symptom_match"
    # 2) prioridade: engine > bridge > voice > ollama
    for key in ("engine", "bridge", "voice", "ollama"):
        if key in offline:
            fid = SERVICE_FM.get(key)
            if fid and fid in by_id:
                return by_id[fid], f"service_offline:{key}"
    # 3) hints do snapshot
    hints = " ".join(snapshot_hints({"services": {s: {"online": s not in offline} for s in ("engine", "bridge", "voice", "ollama")}}))
    if offline:
        hits = match_symptom(modes, " ".join(offline) + " offline " + hints, limit=3)
        if hits:
            return hits[0][1], "offline_match"
    return None, "none"


def run_loop(
    symptom: str = "",
    *,
    record: bool = True,
    wait_verify_s: float = 0.0,
) -> dict[str, Any]:
    data = load_yaml(DEFAULT_CATALOG)
    modes, errors = validate_catalog(data)
    if errors:
        return {"ok": False, "errors": errors, "phase": "catalog_invalid"}

    snap1 = collect_snapshot(include_ui_state=True)
    offline1 = offline_services(snap1)
    fm, reason = _pick_fm(modes, offline1, symptom)

    result: dict[str, Any] = {
        "ok": True,
        "phase": "diagnosed",
        "advisory_only": True,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "symptom": symptom or None,
        "match_reason": reason,
        "snapshot_before": {
            "offline": offline1,
            "services": {
                k: {"online": v.get("online"), "port": v.get("port")}
                for k, v in (snap1.get("services") or {}).items()
            },
        },
        "failure_mode": None,
        "proposed_recovery": [],
        "official_tools": [],
        "verify_checklist": [],
        "human_gate": "Nada será executado automaticamente. No Harness: use o starter/BAT oficial e CONFIRMAR se for mutação.",
        "snapshot_after": None,
        "verified": None,
        "record_id": None,
    }

    if fm is None:
        result["phase"] = "healthy_or_unknown"
        result["message"] = (
            "Nenhum serviço OFF mapeado e sem match de sintoma. "
            "Sistema pode estar saudável ou o sintoma precisa ser mais específico."
        )
        if not offline1 and not symptom.strip():
            result["message"] = "Todos os serviços básicos respondem (TCP/health). Nada a recuperar."
            result["phase"] = "healthy"
        return result

    result["failure_mode"] = {
        "id": fm.get("id"),
        "title": fm.get("title"),
        "severity": fm.get("severity"),
        "service": fm.get("service"),
        "symptom": fm.get("symptom"),
    }
    result["proposed_recovery"] = list(fm.get("repair_steps") or [])
    result["official_tools"] = list(fm.get("official_tools") or [])
    result["verify_checklist"] = list(fm.get("verify") or [])

    # Verificação opcional (re-snapshot; não executa repair)
    if wait_verify_s > 0:
        time.sleep(wait_verify_s)
    snap2 = collect_snapshot(include_ui_state=False)
    offline2 = offline_services(snap2)
    result["snapshot_after"] = {
        "offline": offline2,
        "services": {
            k: {"online": v.get("online"), "port": v.get("port")}
            for k, v in (snap2.get("services") or {}).items()
        },
    }
    # verified = True só se o serviço do FM saiu de offline (operador pode ter recuperado entre snaps)
    svc = fm.get("service")
    if svc in ("engine", "bridge", "voice", "ollama"):
        was_off = svc in offline1
        now_on = svc not in offline2
        result["verified"] = (not was_off) or now_on
        result["phase"] = "verified_ok" if result["verified"] and was_off and now_on else "awaiting_human_repair"
    else:
        result["verified"] = None
        result["phase"] = "awaiting_human_repair"

    if record:
        phase_rec = result["phase"] if result["phase"] in {
            "detected", "diagnosed", "plan_proposed", "awaiting_confirm",
            "repair_applied", "verified_ok", "verified_fail", "aborted", "simulated_only",
        } else "diagnosed"
        rec = append_record(
            DEFAULT_RECORDS,
            failure_mode_id=str(fm.get("id")),
            phase=phase_rec,
            observed={
                "symptom_text": symptom,
                "offline_before": offline1,
                "offline_after": offline2,
                "match_reason": reason,
            },
            diagnosis=str(fm.get("title")),
            proposed_repair=result["proposed_recovery"],
            notes="ops_loop",
            operator="ops_loop",
        )
        result["record_id"] = rec.get("record_id")
        try:
            from experiences import append_experience

            append_experience(
                source="ops_loop",
                phase=result.get("phase") or phase_rec,
                offline=list(offline1),
                failure_mode_id=str(fm.get("id")),
                title=str(fm.get("title")),
                symptom=symptom or None,
                proposed_repair=list(result.get("proposed_recovery") or []),
                official_tools=list(result.get("official_tools") or []),
                verified=result.get("verified"),
                notes="ops_loop record",
                extra={"match_reason": reason, "record_id": result.get("record_id")},
            )
        except Exception:
            pass

    return result


def format_ops_report(result: dict[str, Any]) -> str:
    lines = ["══ AURA OPS LOOP (advisory) ══"]
    lines.append(f"Fase: {result.get('phase')}")
    before = result.get("snapshot_before") or {}
    off = before.get("offline") or []
    lines.append(f"Offline agora: {', '.join(off) if off else '(nenhum)'}")
    fm = result.get("failure_mode")
    if not fm:
        lines.append(result.get("message") or "Sem FM.")
        lines.append(result.get("human_gate", ""))
        return "\n".join(lines)

    lines.append(f"FM_ID: {fm.get('id')}  [{fm.get('severity')}]  serviço={fm.get('service')}")
    lines.append(f"Título: {fm.get('title')}")
    lines.append(f"Match: {result.get('match_reason')}")
    lines.append("PASSOS DE RECOVERY (oficiais / manuais):")
    for i, step in enumerate(result.get("proposed_recovery") or [], 1):
        lines.append(f"  {i}. {step}")
    tools = result.get("official_tools") or []
    if tools:
        lines.append("BAT/ferramentas: " + ", ".join(tools))
    lines.append("VERIFICAR depois de aplicar:")
    for v in result.get("verify_checklist") or []:
        lines.append(f"  - {v}")
    after = result.get("snapshot_after") or {}
    if after:
        lines.append(f"Offline pós-check: {', '.join(after.get('offline') or []) or '(nenhum)'}")
    if result.get("verified") is True:
        lines.append("Verificação: serviço do FM parece ONLINE no re-check.")
    elif result.get("verified") is False:
        lines.append("Verificação: serviço ainda OFF — aplique recovery oficial e rode de novo.")
    else:
        lines.append("Verificação: aguardando ação humana (nada foi executado pelo loop).")
    lines.append(result.get("human_gate", ""))
    if result.get("record_id"):
        lines.append(f"Registro: {result['record_id']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA operational loop (advisory)")
    parser.add_argument("--symptom", default="", help="sintoma livre opcional")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument("--wait", type=float, default=0.0, help="segundos antes do re-check")
    args = parser.parse_args()

    result = run_loop(args.symptom, record=not args.no_record, wait_verify_s=args.wait)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_ops_report(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
