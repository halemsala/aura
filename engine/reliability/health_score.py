# health_score.py — Health score composto 0-100 + early warning verde/amarelo/vermelho
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time


@dataclass
class MetricSample:
    latency_ms: float = 0.0
    error: bool = False
    vram_ratio: float = 0.0
    confidence: float = 1.0
    cache_hit: bool = False
    ts: float = field(default_factory=time.time)


class SystemHealthScore:
    """
    Score 0-100 a partir de latência, erros, VRAM, confiança e cache.
    Níveis: green >= 80, yellow >= 55, red < 55
    """

    def __init__(self, window: int = 50):
        self.window = window
        self.samples: List[MetricSample] = []

    def record(self, **kwargs):
        self.samples.append(MetricSample(**kwargs))
        if len(self.samples) > self.window:
            self.samples.pop(0)

    def score(self) -> Dict[str, Any]:
        if not self.samples:
            return {"score": 100, "level": "green", "n": 0}

        n = len(self.samples)
        err_rate = sum(1 for s in self.samples if s.error) / n
        avg_lat = sum(s.latency_ms for s in self.samples) / n
        avg_vram = sum(s.vram_ratio for s in self.samples) / n
        avg_conf = sum(s.confidence for s in self.samples) / n
        cache_rate = sum(1 for s in self.samples if s.cache_hit) / n

        # penalidades (pesos calibráveis)
        score = 100.0
        score -= min(40.0, err_rate * 100)           # erros
        score -= min(25.0, max(0, avg_lat - 200) / 80)  # latência acima de 200ms
        score -= min(20.0, max(0, avg_vram - 0.75) * 80)  # VRAM alta
        score -= min(15.0, max(0, 0.7 - avg_conf) * 50)   # baixa confiança
        score += min(5.0, cache_rate * 5)                 # bônus cache
        score = max(0.0, min(100.0, score))

        if score >= 80:
            level = "green"
        elif score >= 55:
            level = "yellow"
        else:
            level = "red"

        return {
            "score": round(score, 1),
            "level": level,
            "n": n,
            "error_rate": round(err_rate, 3),
            "avg_latency_ms": round(avg_lat, 1),
            "avg_vram_ratio": round(avg_vram, 3),
            "avg_confidence": round(avg_conf, 3),
            "cache_hit_rate": round(cache_rate, 3),
        }


health_score = SystemHealthScore()
