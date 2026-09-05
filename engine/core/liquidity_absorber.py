"""Classificação advisory de fluxo de liquidez, sem conexão a mercado."""
from __future__ import annotations


class LiquidityAbsorber:
    @staticmethod
    def classify_flow(odd_drop_percent: float, wom_volume_spike: float) -> str:
        drop = float(odd_drop_percent)
        spike = float(wom_volume_spike)
        if drop > 0.10 and spike > 0.5:
            return "SHARP"
        if drop > 0.05 and spike < 0.2:
            return "PUBLIC"
        return "NORMAL"


__all__ = ["LiquidityAbsorber"]
