# engine/agents/map_filter_agent.py
from __future__ import annotations
from typing import Any, Dict, List
import numpy as np

try:
    import xgboost as xgb
    XGB_OK = True
except ImportError:
    XGB_OK = False

class MapFilterAgent:
    """High-speed filter: discard 95% of matches with hard rules + optional XGB."""

    def __init__(self, min_minute: int = 50, require_corner_line: bool = True):
        self.min_minute = min_minute
        self.require_corner_line = require_corner_line
        self.model = None

    def hard_filter(self, match: Dict[str, Any]) -> bool:
        minute = int(match.get("minute", 0) or 0)
        if minute < self.min_minute:
            return False
        line = match.get("asian_corner_line")
        if self.require_corner_line and (line is None or float(line or 0) <= 0):
            return False
        if match.get("market_suspended"):
            return False
        return True

    def score(self, match: Dict[str, Any]) -> float:
        if not self.hard_filter(match):
            return 0.0
        # Lightweight heuristic score
        vel = abs(float(match.get("odds_velocity", 0) or 0))
        edge = float(match.get("calculated_edge", 0) or 0)
        return min(1.0, 0.4 * (vel / 10.0) + 0.6 * max(0, edge))

    def filter_batch(self, matches: List[Dict[str, Any]], top_k: float = 0.05) -> List[Dict[str, Any]]:
        scored = [(self.score(m), m) for m in matches]
        scored = [(s, m) for s, m in scored if s > 0]
        scored.sort(key=lambda x: -x[0])
        k = max(1, int(len(scored) * top_k))
        return [m for _, m in scored[:k]]
