# engine/infra/gradient_accumulator.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

class GradientAccumulator:
    """Accumulate losses during match; step optimizer only at full-time."""
    def __init__(self) -> None:
        self._losses: List[float] = []
        self._features: List[Dict[str, Any]] = []
        self._match_active = False

    def on_kickoff(self) -> None:
        self._losses.clear()
        self._features.clear()
        self._match_active = True

    def observe(self, features: Dict[str, Any], loss: float) -> None:
        if not self._match_active:
            return
        self._losses.append(float(loss))
        self._features.append(features)

    def on_fulltime(self, model: Any = None, optimizer: Any = None) -> Dict[str, Any]:
        self._match_active = False
        n = len(self._losses)
        if n == 0:
            return {"updated": False, "ticks": 0}
        mean_loss = sum(self._losses) / n
        # If real torch model provided, would call optimizer.step() once here
        stepped = False
        if model is not None and optimizer is not None and hasattr(optimizer, "step"):
            try:
                optimizer.step()
                if hasattr(optimizer, "zero_grad"):
                    optimizer.zero_grad()
                stepped = True
            except Exception:
                stepped = False
        summary = {"updated": True, "ticks": n, "mean_loss": mean_loss, "optimizer_stepped": stepped}
        self._losses.clear()
        self._features.clear()
        return summary

ACCUMULATOR = GradientAccumulator()
