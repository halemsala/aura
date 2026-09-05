# engine/uncertainty_gate.py — V23 conformal-style gate por minuto
from __future__ import annotations
from typing import Dict, Iterable, Tuple


class ConformalUncertaintyGate:
    def __init__(self):
        # (start_min_inclusive, end_min_exclusive) -> max uncertainty
        self._buckets: Tuple[Tuple[int, int, float], ...] = (
            (0, 15, 0.75),
            (15, 30, 0.60),
            (30, 45, 0.50),
            (45, 60, 0.55),
            (60, 75, 0.45),
            (75, 95, 0.35),
        )

    def _get_max_uncertainty(self, minute: int) -> float:
        m = int(minute or 0)
        for a, b, u in self._buckets:
            if a <= m < b:
                return u
        return 0.50

    def should_block(self, current_minute: int, model_confidence: float) -> bool:
        max_u = self._get_max_uncertainty(current_minute)
        current_u = 1.0 - float(model_confidence or 0.0)
        return current_u > max_u

    def evaluate(self, current_minute: int, model_confidence: float) -> dict:
        max_u = self._get_max_uncertainty(current_minute)
        current_u = 1.0 - float(model_confidence or 0.0)
        blocked = current_u > max_u
        return {
            "blocked": blocked,
            "minute": int(current_minute or 0),
            "uncertainty": current_u,
            "max_allowed": max_u,
            "reason": "UNCERTAINTY_GATE" if blocked else "OK",
            "paper_trade": True,
            "execution_allowed": False,
        }


uncertainty_gate = ConformalUncertaintyGate()
