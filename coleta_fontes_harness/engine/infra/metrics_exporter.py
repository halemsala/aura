# engine/infra/metrics_exporter.py
from __future__ import annotations
from prometheus_client import Counter, Gauge, Histogram, start_http_server, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

TELEMETRY_TOTAL = Counter("aura_telemetry_total", "Total telemetry packets", ["status"])
VOICE_LATENCY = Histogram("aura_voice_latency_seconds", "Voice stream TTFT")
VRAM_USAGE = Gauge("aura_vram_usage_ratio", "VRAM usage ratio 0-1")
ODDS_VELOCITY = Gauge("aura_odds_velocity", "Current odds velocity", ["match_id"])
RISK_REJECTS = Counter("aura_risk_rejects_total", "Risk manager rejects", ["error_code"])

def start_metrics_server(port: int = 9100):
    start_http_server(port)

def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
