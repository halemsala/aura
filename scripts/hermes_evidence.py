#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lê o último ciclo Hermes e diz o próximo passo concreto. Não altera o engine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOTS = [Path(r"C:\aura"), Path.cwd(), Path(__file__).resolve().parents[1]]


def find_root() -> Path:
    for c in ROOTS:
        if (c / "logs_supervisor" / "HERMES_AUTONOMOUS_LATEST.json").exists():
            return c.resolve()
        if (c / "engine" / "server.py").exists():
            return c.resolve()
    return Path.cwd().resolve()


def main() -> int:
    root = find_root()
    latest = root / "logs_supervisor" / "HERMES_AUTONOMOUS_LATEST.json"
    print(f"ROOT={root}")
    if not latest.exists():
        print("SEM_CICLO")
        print("Ainda nao existe HERMES_AUTONOMOUS_LATEST.json")
        print("1) Instalar AURA_HERMES_V10.zip com INSTALAR_HERMES_NO_AURA.bat")
        print("2) Correr AURA_HERMES_PAINEL.bat → 1 CICLO")
        print("3) Voltar a correr este script")
        return 2
    data = json.loads(latest.read_text(encoding="utf-8", errors="replace"))
    findings = data.get("findings") or []
    codes = [f.get("code") for f in findings]
    status = data.get("status")
    score = data.get("health_score")
    print(f"STATUS={status} SCORE={score}")

    sys.path.insert(0, str(root / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    incident, reasons = "UNKNOWN", []
    try:
        from hermes_incident import classify, human
        incident, reasons = classify(findings)
        why = human(incident)
    except Exception:
        why = "classificador V10 ausente — usa STATUS/SCORE"
        if any(str(c).startswith("PORT_8080") or c in ("ENGINE_DOWN", "BRIDGE_DOWN") for c in codes):
            incident = "CORE_DOWN"
        elif any(str(c).startswith("CODE_DRIFT") for c in codes):
            incident = "CODE_DRIFT"
        elif any(c in ("LIVE_STALE", "UI_STATE_NO_VIEW", "EXTENSION_MISSING") for c in codes):
            incident = "CAPTURE_ONLY"

    print(f"INCIDENT={incident}")
    print(f"WHY={why}")
    if reasons:
        print("REASONS=" + ",".join(reasons[:8]))

    audit_ok = any(str(c).startswith("AUDIT_OK_") for c in codes)
    drift = [c for c in codes if str(c).startswith("CODE_DRIFT_")]
    print(f"AUDIT_OK={audit_ok} DRIFT={len(drift)}")

    print("--- VEREDICTO ---")
    if incident == "CAPTURE_ONLY" and not drift:
        print("NAO instalar mais overlay.")
        print("Abrir SokkerPRO live + extensao unpacked (pasta extensao) + F5 na aba.")
    elif incident == "CORE_DOWN":
        print("Correr AURA_TUDO_HERMES_AUTONOMO.bat uma vez. Depois 1 CICLO no painel.")
    elif incident == "CODE_DRIFT":
        print("C:\\aura nao e o CLEAN 12.7. Enviar HERMES_AUTONOMOUS_LATEST.json para diff minimo.")
    elif incident == "HEALTHY":
        print("Core fechado. Manter captura viva. Nao reinstalar.")
    else:
        print("Enviar logs_supervisor\\HERMES_AUTONOMOUS_LATEST.json + hermes_events.jsonl")
    print(f"FICHEIRO={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
