# engine/core/pressure_features.py
"""AURA QUANT-X V25 — Rolling pressure / dangerous-attacks features (stdlib only).

Aditivo: nao substitui Poisson/Hawkes/MC. Alimenta QuantBrain e ExperienceDB.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional, Tuple

__all__ = ["RollingPressureTracker", "global_tracker"]


class RollingPressureTracker:
    """Janela rolante de pressao e ataques perigosos (~10 min)."""

    def __init__(self, window_min: float = 10.0, max_points: int = 200):
        self.window_min = float(window_min)
        self._pts: Deque[Tuple[float, float, float]] = deque(maxlen=int(max_points))
        # por fixture: evita misturar partidas
        self._by_fixture: Dict[str, Deque[Tuple[float, float, float]]] = {}

    def _buf(self, fixture_id: Optional[str]) -> Deque[Tuple[float, float, float]]:
        if not fixture_id:
            return self._pts
        key = str(fixture_id)
        if key not in self._by_fixture:
            self._by_fixture[key] = deque(maxlen=self._pts.maxlen)
        return self._by_fixture[key]

    def update(
        self,
        minute: float,
        pressure: float,
        dangerous: float,
        fixture_id: Optional[str] = None,
    ) -> Dict[str, float]:
        m = float(minute or 0.0)
        p = float(pressure or 0.0)
        d = float(dangerous or 0.0)
        buf = self._buf(fixture_id)
        buf.append((m, p, d))

        # descarta pontos fora da janela
        while buf and (m - buf[0][0]) > self.window_min:
            buf.popleft()

        if len(buf) < 2:
            return {
                "pressure_ma": p,
                "pressure_delta": 0.0,
                "dang_rate_10m": 0.0,
                "pressure_peak": p,
                "n_points": float(len(buf)),
                "is_noise": 0.0,
            }

        p0, p1 = buf[0][1], buf[-1][1]
        d0, d1 = buf[0][2], buf[-1][2]
        dt = max(m - buf[0][0], 1e-6)
        peak = max(x[1] for x in buf)
        ma = sum(x[1] for x in buf) / len(buf)
        delta = p1 - p0
        dang_rate = max(0.0, (d1 - d0) / dt)

        # ruido: pressao quase estavel E poucos ataques na janela
        is_noise = 1.0 if (abs(delta) < 5.0 and dang_rate < 0.05) else 0.0

        return {
            "pressure_ma": round(ma, 2),
            "pressure_delta": round(delta, 2),
            "dang_rate_10m": round(dang_rate, 4),
            "pressure_peak": round(peak, 2),
            "n_points": float(len(buf)),
            "is_noise": is_noise,
        }

    def reset(self, fixture_id: Optional[str] = None) -> None:
        if fixture_id:
            self._by_fixture.pop(str(fixture_id), None)
        else:
            self._pts.clear()
            self._by_fixture.clear()


# instancia compartilhada (hot path)
global_tracker = RollingPressureTracker(window_min=10.0)
