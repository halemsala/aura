"""Adaptador offline e advisory para a ideia Soup/layer streaming no AURA.

Não executa Soup, não chama subprocessos, rede, GPU, pip ou modelos.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Mapping
import hashlib
import json


@dataclass(frozen=True)
class SoupPlan:
    base: str
    task: str
    stream_layers: bool
    quantization: str
    stream_source: str
    batch_size: int
    max_length: int
    lora_enabled: bool
    execution_allowed: bool = False
    paper_trade: bool = True
    status: str = "ADVISORY_ONLY"


SUPPORTED_TASKS = {"sft", "dpo", "orpo", "simpo", "kto"}
SUPPORTED_QUANT = {"none", "4bit", "8bit"}


def build_plan(config: Mapping[str, Any]) -> SoupPlan:
    if not isinstance(config, Mapping):
        raise TypeError("config deve ser um mapping")
    base = str(config.get("base", "")).strip()
    task = str(config.get("task", "sft")).lower().strip()
    training = config.get("training", {})
    data = config.get("data", {})
    lora = training.get("lora", {}) if isinstance(training, Mapping) else {}
    if not base:
        raise ValueError("base do modelo é obrigatória para um plano")
    if task not in SUPPORTED_TASKS:
        raise ValueError(f"task não suportada pelo plano offline: {task}")
    quant = str(training.get("quantization", "none")).lower()
    if quant not in SUPPORTED_QUANT:
        raise ValueError(f"quantization inválida: {quant}")
    batch = int(training.get("batch_size", 1))
    length = int(data.get("max_length", 512))
    if batch < 1 or length < 1 or length > 32768:
        raise ValueError("batch_size/max_length fora dos limites")
    stream = bool(training.get("stream_layers", False))
    source = str(training.get("stream_source", "auto")).lower()
    if source not in {"auto", "ram", "nvme"}:
        raise ValueError("stream_source deve ser auto, ram ou nvme")
    return SoupPlan(
        base=base, task=task, stream_layers=stream,
        quantization=quant, stream_source=source, batch_size=batch,
        max_length=length, lora_enabled=bool(lora),
    )


def audit_plan(plan: SoupPlan) -> dict[str, Any]:
    warnings = []
    if plan.stream_layers:
        warnings.append("layer streaming é beta e deve ser validado por benchmark local")
    if plan.max_length > 2048:
        warnings.append("max_length alto pode exceder VRAM apesar do streaming")
    if plan.batch_size > 1:
        warnings.append("batch_size maior aumenta memória de logits e ativação")
    return {"plan": asdict(plan), "warnings": warnings,
            "recommendation": "staging_offline_then_human_approval",
            "execution_allowed": False}


def fingerprint(plan: SoupPlan) -> str:
    raw = json.dumps(asdict(plan), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()
