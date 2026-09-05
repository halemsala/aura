# Item 69 — paper vs live
from __future__ import annotations
import os
from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    OBSERVE = "observe"  # só log, nunca stake


def get_mode() -> TradingMode:
    raw = (os.environ.get("TRADING_MODE") or "paper").strip().lower()
    if raw == "live":
        return TradingMode.PAPER
    try:
        mode = TradingMode(raw)
    except ValueError:
        return TradingMode.PAPER
    if mode == TradingMode.LIVE:
        return TradingMode.PAPER
    return mode


def allows_stake(mode: TradingMode | None = None) -> bool:
    m = mode or get_mode()
    return m in (TradingMode.PAPER, TradingMode.LIVE)


def requires_real_odds(mode: TradingMode | None = None) -> bool:
    """Item 64: em live, odds obrigatórias."""
    m = mode or get_mode()
    return m == TradingMode.LIVE
