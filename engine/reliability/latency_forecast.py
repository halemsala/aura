# latency_forecast.py — previsão linear de latência (early warning)
from __future__ import annotations
import time
from typing import List, Dict, Any


class LatencyForecaster:
    def __init__(self, max_points: int = 30, warn_ms: float = 2000.0):
        self.max_points = max_points
        self.warn_ms = warn_ms
        self.ts: List[float] = []
        self.vals: List[float] = []

    def record(self, latency_ms: float):
        self.ts.append(time.time())
        self.vals.append(float(latency_ms))
        if len(self.vals) > self.max_points:
            self.ts.pop(0)
            self.vals.pop(0)

    def forecast(self, horizon_sec: float = 60.0) -> Dict[str, Any]:
        if len(self.vals) < 5:
            return {"warning": False, "projected_ms": self.vals[-1] if self.vals else 0.0}

        t0 = self.ts[0]
        xs = [t - t0 for t in self.ts]
        ys = self.vals
        n = len(xs)
        sx = sum(xs)
        sy = sum(ys)
        sxy = sum(a * b for a, b in zip(xs, ys))
        sxx = sum(a * a for a in xs)
        slope = (n * sxy - sx * sy) / (n * sxx - sx * sx + 1e-9)
        elapsed = xs[-1]
        projected = ys[-1] + slope * horizon_sec
        return {
            "warning": projected >= self.warn_ms or (slope > 5 and ys[-1] > self.warn_ms * 0.5),
            "current_ms": round(ys[-1], 1),
            "projected_ms": round(projected, 1),
            "slope_ms_per_sec": round(slope, 3),
            "horizon_sec": horizon_sec,
        }


latency_forecaster = LatencyForecaster()
