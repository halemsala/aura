# -*- coding: utf-8 -*-
"""
Accuracy Boost Toolkit — v12.8.0
Novas ferramentas para aumentar acertividade das análises:
- Ensemble Hawkes + shadow model + veracity
- Calibração online de confiança
- Cross-check de pressão e odds velocity
- Scenario simulator (what-if)
- Quality gate reforçado
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class EnsembleResult:
    final_prob: float
    confidence: float
    components: Dict[str, float]
    disagreement: float
    recommended_action: str


def ensemble_probability(
    hawkes_prob: float,
    shadow_prob: Optional[float],
    market_implied: Optional[float],
    veracity: float = 0.75,
    pressure_slope: float = 0.0,
    odds_velocity: float = 0.0,
) -> EnsembleResult:
    """
    Combina fontes com pesos adaptativos.
    Veracity baixa reduz peso do modelo e aumenta peso de mercado (conservador).
    """
    w_h = 0.45
    w_s = 0.25 if shadow_prob is not None else 0.0
    w_m = 0.20 if market_implied is not None else 0.0
    w_p = 0.10  # pressão residual

    # Normaliza pesos
    total_w = w_h + w_s + w_m + w_p
    w_h, w_s, w_m, w_p = [w / total_w for w in (w_h, w_s, w_m, w_p)]

    # Ajuste por veracity: se baixa, puxa para 0.5 (incerteza)
    v = max(0.3, min(1.0, veracity))
    adj_h = hawkes_prob * v + 0.5 * (1 - v)
    adj_s = (shadow_prob * v + 0.5 * (1 - v)) if shadow_prob is not None else 0.5
    adj_m = market_implied if market_implied is not None else 0.5

    # Pressão: slope positivo leve aumenta, negativo reduz (clipado)
    pressure_adj = math.tanh(pressure_slope * 2.0) * 0.04

    final = (
        w_h * adj_h
        + w_s * adj_s
        + w_m * adj_m
        + w_p * (0.5 + pressure_adj)
    )
    final = max(0.05, min(0.95, final))

    # Disagreement: desvio entre fontes
    sources = [adj_h]
    if shadow_prob is not None:
        sources.append(adj_s)
    if market_implied is not None:
        sources.append(adj_m)
    disagreement = float(np.std(sources)) if len(sources) > 1 else 0.0

    # Confiança: alta quando veracity alta e disagreement baixo
    conf = (0.6 * v + 0.4 * (1.0 - min(1.0, disagreement * 3))) * 100
    conf = max(20.0, min(95.0, conf))

    # Odds velocity: se muito alta em direção contrária, reduz ação
    action = "HOLD"
    if final >= 0.62 and conf >= 60 and odds_velocity < 1.8:
        action = "BUY_CORNER"
    elif final <= 0.38 and conf >= 60:
        action = "AVOID"
    elif conf < 45:
        action = "WAIT_DATA"

    return EnsembleResult(
        final_prob=round(final, 4),
        confidence=round(conf, 1),
        components={
            "hawkes": round(adj_h, 4),
            "shadow": round(adj_s, 4) if shadow_prob is not None else None,
            "market": round(adj_m, 4) if market_implied is not None else None,
            "pressure_adj": round(pressure_adj, 4),
            "veracity": round(v, 3),
        },
        disagreement=round(disagreement, 4),
        recommended_action=action,
    )


def scenario_what_if(
    base_prob: float,
    pressure_delta_pct: float = 0.0,
    odds_move_pct: float = 0.0,
    minutes_ahead: int = 5,
) -> Dict[str, Any]:
    """
    Simulador simples de cenário.
    pressure_delta_pct: +20 = pressão sobe 20%
    odds_move_pct: mudança relativa nas odds (negativo = odds caem = mercado aquecido)
    """
    # Elasticidade aproximada
    p = base_prob
    p += (pressure_delta_pct / 100.0) * 0.12
    p -= (odds_move_pct / 100.0) * 0.08  # odds caindo aumentam prob implícita
    # Decay temporal leve
    decay = 1.0 - (minutes_ahead / 90.0) * 0.05
    p *= decay
    p = max(0.05, min(0.95, p))

    return {
        "scenario_prob": round(p, 4),
        "delta_from_base": round(p - base_prob, 4),
        "minutes_ahead": minutes_ahead,
        "assumptions": {
            "pressure_delta_pct": pressure_delta_pct,
            "odds_move_pct": odds_move_pct,
        },
        "interpretation": (
            "Cenário mais favorável" if p > base_prob + 0.03
            else "Cenário menos favorável" if p < base_prob - 0.03
            else "Cenário estável"
        ),
    }


def calibrate_confidence(
    raw_confidence: float,
    historical_accuracy: Optional[float] = None,
    sample_size: int = 0,
) -> float:
    """
    Calibração isotônica simples.
    Se historical_accuracy disponível e n>=20, puxa confiança em direção à acurácia observada.
    """
    c = max(0.0, min(100.0, raw_confidence))
    if historical_accuracy is not None and sample_size >= 20:
        # Shrinkage
        weight = min(0.4, sample_size / 100.0)
        c = (1 - weight) * c + weight * (historical_accuracy * 100)
    return round(c, 1)


def quality_gate_reinforced(
    veracity: float,
    data_age_sec: float,
    missing_fields: List[str],
    disagreement: float,
) -> Dict[str, Any]:
    """
    Gate reforçado: bloqueia ou reduz peso se dados ruins.
    """
    reasons = []
    score = 100.0

    if veracity < 0.55:
        score -= 35
        reasons.append("veracity_baixa")
    if data_age_sec > 45:
        score -= min(30, (data_age_sec - 45) * 0.5)
        reasons.append("dados_stale")
    if len(missing_fields) >= 2:
        score -= 20
        reasons.append("campos_faltando")
    if disagreement > 0.18:
        score -= 15
        reasons.append("alta_discordancia_fontes")

    score = max(0.0, score)
    blocked = score < 40
    weight = max(0.2, score / 100.0)

    return {
        "quality_score": round(score, 1),
        "weight": round(weight, 3),
        "blocked": blocked,
        "reasons": reasons,
        "action": "BLOCK" if blocked else ("REDUCE_WEIGHT" if weight < 0.7 else "OK"),
    }


def build_accuracy_report(
    ensemble: EnsembleResult,
    gate: Dict[str, Any],
    scenarios: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "timestamp": time.time(),
        "ensemble": {
            "prob": ensemble.final_prob,
            "confidence": ensemble.confidence,
            "action": ensemble.recommended_action,
            "disagreement": ensemble.disagreement,
            "components": ensemble.components,
        },
        "quality_gate": gate,
        "scenarios": scenarios or [],
        "version": "12.8.0-accuracy-boost",
    }
