# engine/routes/metrics.py — V23 Prometheus-style metrics
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

_metrics_data = {
    "api_requests_total": 0,
    "api_latency_seconds": [],
    "glm_veto_total": 0,
    "queue_depth": 0,
}


def record_request(latency: float) -> None:
    _metrics_data["api_requests_total"] += 1
    _metrics_data["api_latency_seconds"].append(float(latency))
    if len(_metrics_data["api_latency_seconds"]) > 1000:
        _metrics_data["api_latency_seconds"].pop(0)


def record_glm_veto() -> None:
    _metrics_data["glm_veto_total"] += 1


def set_queue_depth(depth: int) -> None:
    _metrics_data["queue_depth"] = int(depth)


@router.get("/metrics")
async def prometheus_metrics():
    lat = _metrics_data["api_latency_seconds"]
    avg_lat = sum(lat) / max(len(lat), 1)
    lines = [
        "# HELP aura_api_requests_total Total de requisicoes na API",
        "# TYPE aura_api_requests_total counter",
        f"aura_api_requests_total {_metrics_data['api_requests_total']}",
        "",
        "# HELP aura_api_latency_avg Latencia media da API",
        "# TYPE aura_api_latency_avg gauge",
        f"aura_api_latency_avg {avg_lat:.4f}",
        "",
        "# HELP aura_glm_veto_total Vezes que o Risk Gate vetou o GLM",
        "# TYPE aura_glm_veto_total counter",
        f"aura_glm_veto_total {_metrics_data['glm_veto_total']}",
        "",
        "# HELP aura_inference_queue_depth Profundidade da fila de IA",
        "# TYPE aura_inference_queue_depth gauge",
        f"aura_inference_queue_depth {_metrics_data['queue_depth']}",
        "",
    ]
    return PlainTextResponse("\n".join(lines), media_type="text/plain; version=0.0.4")
