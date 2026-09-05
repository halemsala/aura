from __future__ import annotations
"""Native risk core: tries compiled Rust extension, falls back to pure Python."""
from typing import Any
try:
    from engine.native import risk_core_rs as _rs  # type: ignore
    HAS_RUST = True
except Exception:
    from engine.native import risk_core_fallback as _rs
    HAS_RUST = False

def kelly_fraction(edge: float, odds: float, max_frac: float = 0.05) -> float:
    return float(_rs.kelly_fraction(edge, odds, max_frac))

def risk_score(odds_velocity: float, pressure: float, edge: float) -> float:
    return float(_rs.risk_score(odds_velocity, pressure, edge))

def orderbook_imbalance(bids_vol: float, asks_vol: float) -> float:
    return float(_rs.orderbook_imbalance(bids_vol, asks_vol))

def backend() -> str:
    return "rust" if HAS_RUST else "python_fallback"
