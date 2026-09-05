#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Safe Activation v1.0
Ativa agentes e ferramentas de forma segura, com verificações obrigatórias.
PAPER-TRADE ONLY — nunca habilita execução real.
"""
import os, sys, json, requests
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)
REPORT_PATH = LOGDIR / "safe_activation_report.json"


def log(msg: str):
    ts = datetime.now().isoformat()
    print(f"[{ts}] {msg}")


def check_invariants() -> dict:
    env_checks = {
        "PAPER_TRADE": os.environ.get("PAPER_TRADE", "").lower() == "true",
        "EXECUTION_ALLOWED": os.environ.get("EXECUTION_ALLOWED", "").lower() == "false",
        "AURA_EXECUTION_ALLOWED": os.environ.get("AURA_EXECUTION_ALLOWED", "1") == "0",
        "AURA_UNLOCK_LIVE": os.environ.get("AURA_UNLOCK_LIVE", "1") == "0",
        "AURA_PAPER_ONLY": os.environ.get("AURA_PAPER_ONLY", "") == "1",
        "GLM_ADVISORY_ONLY": os.environ.get("GLM_ADVISORY_ONLY", "").lower() == "true",
    }
    all_safe = all(env_checks.values())
    return {"all_safe": all_safe, "checks": env_checks}


def activate_via_api() -> dict:
    try:
        r = requests.get("http://127.0.0.1:8765/api/health", timeout=5)
        if r.status_code != 200:
            return {"activated": False, "error": f"Engine health falhou: {r.status_code}"}
        payload = {"mode": "safe_activate", "paper_trade": True, "execution_allowed": False}
        r2 = requests.post(
            "http://127.0.0.1:8765/api/activation",
            json=payload, timeout=10,
            headers={"Content-Type": "application/json"}
        )
        if r2.status_code == 200:
            return {"activated": True, "response": r2.json()}
        return {"activated": False, "error": f"API retornou {r2.status_code}", "response": r2.text[:500]}
    except Exception as e:
        return {"activated": False, "error": str(e)}


def main():
    log("=" * 60)
    log("AURA Safe Activation v1.0")
    log("=" * 60)
    inv = check_invariants()
    log(f"[SEGURANCA] Invariantes: {'TODOS OK' if inv['all_safe'] else 'ALGUNS FALHARAM'}")
    for k, v in inv["checks"].items():
        log(f"  [{'OK' if v else 'FALHA'}] {k}")
    if not inv["all_safe"]:
        log("[ERRO] Invariantes de seguranca violados. Ativacao BLOQUEADA.")
        report = {"timestamp": datetime.now().isoformat(), "safe": False, "reason": "invariants_failed", "details": inv}
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return 1
    log("[ATIVACAO] Tentando ativar via Engine API...")
    result = activate_via_api()
    if result["activated"]:
        log("[ATIVACAO] SUCESSO — Agentes/ferramentas ativados em modo seguro")
    else:
        log(f"[ATIVACAO] API indisponivel: {result.get('error', 'unknown')}")
        log("[ATIVACAO] Fallback: installAndActivateMax() no SPA.")
    report = {"timestamp": datetime.now().isoformat(), "safe": True, "invariants": inv, "activation": result}
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(f"[RESUMO] Relatorio: {REPORT_PATH}")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
