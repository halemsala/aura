# Item 98 — SLOs locais
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SLO:
    quant_p95_ms: float = 100.0
    llm_p95_ms: float = 8000.0
    engine_availability_daily: float = 0.99
    min_cache_hit_l1: float = 0.20
    max_brier_alert: float = 0.35
