"""
Módulo 8 — Paper mode forçado até critérios OU unlock explícito completo.
"""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

from engine.core.policy_runtime import get_system_policy, is_unlock_requested

MIN_TRADES = 50
MIN_ROI = 0.0
MAX_BRIER = 0.22


def can_go_live(metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Neste pacote paper-only, métricas nunca promovem LIVE."""
    return {
        "can_live": False,
        "forced_paper": True,
        "reasons": ["paper_only_package"],
        "metrics_used": {},
        "via": "hard_lock",
    }


def enforce_mode() -> str:
    """Retorna o modo efetivo — sempre paper neste pacote."""
    return "paper"
