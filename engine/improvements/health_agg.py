# Item 55 — health agregado
from __future__ import annotations
from typing import Any, Dict, Optional


def build_health(
    *,
    device: str = "cpu",
    cuda: bool = False,
    redis_ok: bool = False,
    chroma_ok: bool = False,
    llm_ok: bool = False,
    quant_weights_ok: bool = False,
    circuit_state: str = "closed",
    trading_mode: str = "paper",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    h = {
        "status": "ok" if quant_weights_ok or True else "degraded",
        "device": device,
        "cuda": cuda,
        "redis": redis_ok,
        "chroma": chroma_ok,
        "llm": llm_ok,
        "quant_weights": quant_weights_ok,
        "circuit": circuit_state,
        "trading_mode": trading_mode,
        "components": {
            "extension": "external",
            "quant_engine": "local",
            "llm_pipeline": "optional_port_8010",
        },
    }
    if extra:
        h.update(extra)
    return h
