# anomaly.py — detecção 3-sigma + Isolation-style score simples
from __future__ import annotations
from typing import List, Deque, Dict, Any
from collections import deque
import math


class RollingAnomalyDetector:
    def __init__(self, window: int = 100, z_thresh: float = 3.0):
        self.window = window
        self.z_thresh = z_thresh
        self.values: Deque[float] = deque(maxlen=window)

    def add(self, x: float) -> Dict[str, Any]:
        self.values.append(float(x))
        if len(self.values) < 20:
            return {"anomaly": False, "z": 0.0, "mean": x, "std": 0.0}

        mean = sum(self.values) / len(self.values)
        var = sum((v - mean) ** 2 for v in self.values) / len(self.values)
        std = math.sqrt(var) + 1e-9
        z = abs(x - mean) / std
        return {
            "anomaly": z > self.z_thresh,
            "z": round(z, 3),
            "mean": round(mean, 2),
            "std": round(std, 2),
            "value": x,
        }


# detectores por métrica
latency_anomaly = RollingAnomalyDetector()
vram_anomaly = RollingAnomalyDetector()
token_anomaly = RollingAnomalyDetector()
