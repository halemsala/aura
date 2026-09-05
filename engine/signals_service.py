# signals_service.py — Camada única: features → risco → log → paper trade
from __future__ import annotations
from typing import Any, Dict, Optional

from features import frame_from_stats, engineer_sequence, baseline_signal
from risk_manager import RiskManager
from data_store import log_signal, open_paper_trade, init_schema

# singleton de risco (banca paper)
risk = RiskManager(bankroll=1000.0)
init_schema()


def process_live_signal(
    fixture_id: str,
    stats: Dict[str, Any],
    history: list,
    model_corner_prob: float,
    model_goal_prob: float,
    odds: float = 1.85,
    use_baseline_if_weak: bool = True,
) -> Dict[str, Any]:
    """
    Consolida probabilidade do modelo + baseline, aplica RiskManager,
    grava log e abre paper trade se aprovado.
    """
    feats = engineer_sequence(history)
    base_sig = baseline_signal(feats)

    # Escolha de sinal: modelo tem prioridade se prob alta; senão baseline
    signal = "HOLD"
    prob = 0.0
    if model_corner_prob >= 0.72:
        signal = "BUY_CORNER"
        prob = model_corner_prob
    elif model_goal_prob >= 0.75:
        signal = "BUY_GOAL"
        prob = model_goal_prob
    elif use_baseline_if_weak and base_sig != "HOLD":
        signal = base_sig
        prob = 0.65  # baseline não calibrada — stake só se risk permitir (min_prob pode bloquear)

    decision = risk.approve(fixture_id, signal, prob, odds=odds)

    final_signal = decision["signal"] if decision["approved"] else "HOLD"
    stake_pct = decision["stake_pct"] if decision["approved"] else 0.0

    log_signal(
        fixture_id=fixture_id,
        signal=final_signal,
        corner_prob=model_corner_prob,
        goal_prob=model_goal_prob,
        stake=stake_pct,
        payload={"features": feats, "risk_reason": decision["reason"], "baseline": base_sig},
    )

    trade_id = None
    if decision["approved"]:
        trade_id = open_paper_trade(
            fixture_id=fixture_id,
            signal=final_signal,
            prob=prob,
            odds=odds,
            stake_pct=stake_pct,
            bankroll=risk.state.bankroll,
        )

    return {
        "signal": final_signal,
        "prob": prob,
        "stake_pct": stake_pct,
        "approved": decision["approved"],
        "risk_reason": decision["reason"],
        "features": feats,
        "baseline_signal": base_sig,
        "paper_trade_id": trade_id,
        "bankroll": risk.state.bankroll,
        "daily_pnl": risk.state.daily_pnl,
        "halted": risk.state.halted,
    }
