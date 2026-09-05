# watchdog.py — orquestra predição: VRAM + latência + anomalia + health + cascade
from __future__ import annotations
from typing import Any, Dict, Optional

from .predictive_engine import vram_monitor, HallucinationDetector
from .health_score import health_score
from .anomaly import latency_anomaly, vram_anomaly
from .cascade_guard import cascade_guard
from .latency_forecast import latency_forecaster


def observe_request(
    latency_ms: float,
    error: bool = False,
    confidence: float = 1.0,
    cache_hit: bool = False,
    component: str = "engine",
    logits: Optional[list] = None,
) -> Dict[str, Any]:
    """Chamar após cada inferência/telemetria."""
    vram_monitor.record_from_torch()
    vram_pred = vram_monitor.predict_vram_overflow(5.0)
    vram_ratio = 0.0
    if vram_pred.get("current_vram_mb") and vram_monitor.capacity_mb:
        vram_ratio = float(vram_pred["current_vram_mb"]) / max(vram_monitor.capacity_mb, 1.0)

    latency_forecaster.record(latency_ms)
    lat_fc = latency_forecaster.forecast(60.0)
    lat_anom = latency_anomaly.add(latency_ms)
    vram_anom = vram_anomaly.add(vram_ratio * 100)

    if error:
        cascade_guard.report_failure(component)

    conf = confidence
    hall = None
    if logits is not None:
        hall = HallucinationDetector.evaluate_confidence(logits)
        conf = float(hall.get("confidence", conf))

    health_score.record(
        latency_ms=latency_ms,
        error=error,
        vram_ratio=vram_ratio,
        confidence=conf,
        cache_hit=cache_hit,
    )
    hs = health_score.score()

    alerts = []
    if vram_pred.get("warning"):
        alerts.append("vram_overflow_risk")
    if lat_fc.get("warning"):
        alerts.append("latency_degradation_risk")
    if lat_anom.get("anomaly"):
        alerts.append("latency_anomaly")
    if hall and hall.get("high_risk"):
        alerts.append("hallucination_risk")
    if cascade_guard.is_degraded():
        alerts.append("cascade_degraded")
    if hs["level"] == "red":
        alerts.append("health_red")

    return {
        "health": hs,
        "vram": vram_pred,
        "latency_forecast": lat_fc,
        "latency_anomaly": lat_anom,
        "hallucination": hall,
        "cascade": cascade_guard.status(),
        "alerts": alerts,
        "safe_to_continue": "cascade_degraded" not in alerts and hs["level"] != "red",
    }
