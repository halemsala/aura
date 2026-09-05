from __future__ import annotations
import math
from typing import Dict

def kelly_fraction(edge: float, odds: float, max_frac: float = 0.05) -> float:
    if odds <= 1.0 or edge <= 0:
        return 0.0
    b = odds - 1.0
    p = min(0.99, max(0.01, 0.5 + edge))
    q = 1.0 - p
    f = (b * p - q) / b
    return float(max(0.0, min(max_frac, f)))

def risk_score(odds_velocity: float, pressure: float, edge: float) -> float:
    v = abs(float(odds_velocity))
    p = max(0.0, min(1.0, float(pressure)))
    e = float(edge)
    return float(max(0.0, min(1.0, 0.4 * p + 0.3 * min(v / 5.0, 1.0) + 0.3 * max(e, 0.0))))

def orderbook_imbalance(bids_vol: float, asks_vol: float) -> float:
    t = bids_vol + asks_vol
    if t <= 0:
        return 0.0
    return float((bids_vol - asks_vol) / t)
