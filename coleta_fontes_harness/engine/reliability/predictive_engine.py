# predictive_engine.py — Motor preditivo de falhas & reliability
import time
import math
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class HealthMetrics:
    vram_usage_mb: float
    vram_total_mb: float
    latency_ms: float
    token_rate: float
    error_count: int
    confidence_score: float


class EarlyWarningVRAMMonitor:
    """Monitora VRAM e prevê OOM com regressão linear simples."""

    def __init__(self, capacity_mb: float = 8192.0, safety_threshold: float = 0.88):
        self.capacity_mb = capacity_mb
        self.safety_threshold = safety_threshold
        self.history: List[float] = []
        self.timestamps: List[float] = []

    def record_usage(self, usage_mb: float):
        now = time.time()
        self.history.append(float(usage_mb))
        self.timestamps.append(now)
        if len(self.history) > 20:
            self.history.pop(0)
            self.timestamps.pop(0)

    def record_from_torch(self) -> Optional[float]:
        try:
            import torch
            if not torch.cuda.is_available():
                return None
            used = torch.cuda.memory_allocated() / (1024 * 1024)
            total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
            self.capacity_mb = total
            self.record_usage(used)
            return used
        except Exception:
            return None

    def predict_vram_overflow(self, horizon_seconds: float = 5.0) -> Dict[str, Any]:
        if len(self.history) < 5:
            return {
                "warning": False,
                "projected_vram_mb": self.history[-1] if self.history else 0.0,
                "samples": len(self.history),
            }

        dt = [t - self.timestamps[0] for t in self.timestamps]
        n = len(self.history)
        sum_x = sum(dt)
        sum_y = sum(self.history)
        sum_xy = sum(x * y for x, y in zip(dt, self.history))
        sum_xx = sum(x * x for x in dt)
        denom = n * sum_xx - (sum_x ** 2) + 1e-9
        slope = (n * sum_xy - sum_x * sum_y) / denom
        current_vram = self.history[-1]
        projected_vram = current_vram + (slope * horizon_seconds)
        usage_ratio = projected_vram / max(self.capacity_mb, 1.0)

        return {
            "warning": usage_ratio >= self.safety_threshold,
            "current_vram_mb": round(current_vram, 2),
            "projected_vram_mb": round(projected_vram, 2),
            "usage_ratio": round(usage_ratio, 3),
            "slope_mb_per_sec": round(slope, 2),
        }


class PredictiveCircuitBreaker:
    """Circuit breaker preditivo por taxa de falha e latência média."""

    def __init__(self, failure_threshold: float = 0.3, latency_threshold_ms: float = 4000.0):
        self.failure_threshold = failure_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.state = "CLOSED"  # CLOSED | OPEN | HALF-OPEN
        self.recent_latencies: List[float] = []
        self.recent_failures: List[bool] = []
        self.opened_at: Optional[float] = None
        self.recovery_seconds = 60.0

    def execute(self, func: Callable, fallback_func: Callable, *args, **kwargs) -> Any:
        if self.state == "OPEN":
            if self.opened_at and (time.time() - self.opened_at) >= self.recovery_seconds:
                self.state = "HALF-OPEN"
            else:
                logging.warning("[Circuit Breaker] OPEN → fallback")
                return fallback_func(*args, **kwargs)

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            latency = (time.time() - start_time) * 1000
            self._update_stats(latency=latency, failed=False)
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.opened_at = None
            return result
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            self._update_stats(latency=latency, failed=True)
            logging.error(f"[Circuit Breaker] falha: {e}")
            return fallback_func(*args, **kwargs)

    def _update_stats(self, latency: float, failed: bool):
        self.recent_latencies.append(latency)
        self.recent_failures.append(failed)
        if len(self.recent_latencies) > 10:
            self.recent_latencies.pop(0)
            self.recent_failures.pop(0)

        fail_rate = sum(self.recent_failures) / len(self.recent_failures)
        avg_latency = sum(self.recent_latencies) / len(self.recent_latencies)

        if fail_rate >= self.failure_threshold or avg_latency >= self.latency_threshold_ms:
            self.state = "OPEN"
            self.opened_at = time.time()
            logging.warning(
                f"[Circuit Breaker] preditivo OPEN fail_rate={fail_rate:.2f} avg_lat={avg_latency:.0f}ms"
            )


class HallucinationDetector:
    """Entropia / confiança a partir de logits (ou scores)."""

    @staticmethod
    def evaluate_confidence(logits: List[float]) -> Dict[str, Any]:
        if not logits:
            return {"confidence": 1.0, "entropy": 0.0, "high_risk": False}

        max_logit = max(logits)
        exp_logits = [math.exp(x - max_logit) for x in logits]
        sum_exp = sum(exp_logits) + 1e-12
        probs = [p / sum_exp for p in exp_logits]
        entropy = -sum(p * math.log2(p + 1e-12) for p in probs)
        max_prob = max(probs)
        high_risk = entropy > 2.5 or max_prob < 0.45

        return {
            "confidence": round(max_prob, 3),
            "entropy": round(entropy, 3),
            "high_risk": high_risk,
        }


# singletons úteis
vram_monitor = EarlyWarningVRAMMonitor()
tool_breaker = PredictiveCircuitBreaker()


if __name__ == "__main__":
    vram_mon = EarlyWarningVRAMMonitor(capacity_mb=16384.0, safety_threshold=0.85)
    for usage in [10000, 11500, 12800, 13900, 14800]:
        vram_mon.record_usage(usage)
        print(vram_mon.predict_vram_overflow(horizon_seconds=3.0))
    print(HallucinationDetector.evaluate_confidence([2.1, 1.9, 2.0, 1.8]))
