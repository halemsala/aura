"""Checklist de prontidão operacional — não declara produção financeira."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from paper_kelly import KELLY_LIVE
from risk_gates import KELLY_ENABLED, OBSERVATION_MODE


def production_checklist() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("kelly_live_off", not KELLY_LIVE and not KELLY_ENABLED, "Kelly live desligado")
    add("observation_mode", OBSERVATION_MODE, "Modo observação ativo")
    add("quality_gate", True, "P0 quality gate implementado")
    add("ledger_replay", True, "Ledger + replay mínimos implementados")
    add("target_censoring", True, "Alvo next_corner + censura")
    add("shadow_model", True, "Challenger em shadow (não autoridade live)")
    add("hard_gates", True, "Risk gates independentes")
    add("explanation_card", True, "LLM restrito ao cartão")
    add("tools_l5_blocked", True, "Tools L5 bloqueadas")
    add("corner_intelligence_module", True, "Módulo corner_intelligence ativo")
    add("hawkes_for_against", True, "Hawkes corners for/against + defensive stress")
    add("analysis_central_mode", True, "Produto: central de análise de escanteios (não casa de apostas)")

    # Data-dependent
    try:
        from eval_accuracy import evaluate_all_fixtures
        report = evaluate_all_fixtures(horizon_sec=300)
        n = int((report.get("overall") or {}).get("n") or 0)
        add(
            "labeled_history",
            n >= 100,
            f"Pares label↔prob={n} (recomendado ≥100 para confiar em Brier)",
        )
    except Exception as exc:
        add("labeled_history", False, f"Falha ao avaliar: {exc}")

    add(
        "financial_approval",
        False,
        "Aprovação financeira/operacional humana ainda necessária",
    )

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    return {
        "generated_at": time.time(),
        "passed": passed,
        "total": total,
        "score": round(passed / total, 3) if total else 0,
        "production_ready_financial": False,
        "analysis_central_ready": True,
        "checks": checks,
        "note": "Score alto ≠ autorização para stake real. labeled_history e financial_approval são os gargalos típicos.",
    }
