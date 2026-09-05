#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model routing by sovereignty, complexity, cost (Ollama first)."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

@dataclass
class ModelSpec:
    name: str
    backend: str
    cost_per_1k: float
    latency_ms: int
    context_window: int
    sovereign: bool
    tool_calling_strength: float

REGISTRY: Dict[str, ModelSpec] = {
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),
    "qwen2.5:3b-instruct": ModelSpec("qwen2.5:3b-instruct", "ollama", 0.0, 700, 32_768, True, 0.75),
    "qwen2.5:3b": ModelSpec("qwen2.5:3b", "ollama", 0.0, 700, 32_768, True, 0.75),
    "llama3.2:3b": ModelSpec("llama3.2:3b", "ollama", 0.0, 800, 128_000, True, 0.5),
    "llama3.2:1b": ModelSpec("llama3.2:1b", "ollama", 0.0, 400, 128_000, True, 0.4),
    "gpt-4o-mini": ModelSpec("gpt-4o-mini", "openai", 0.00015, 900, 128_000, False, 0.8),
    "gpt-4o": ModelSpec("gpt-4o", "openai", 0.005, 1200, 128_000, False, 0.95),
}

class ModelRouter:
    def __init__(self, require_sovereign_for: Optional[List[str]] = None):
        self.require_sovereign_for = set(require_sovereign_for or [
            "read_secrets", "apply_fix", "domain_lock", "constitution_check"
        ])

    def select(self, task: dict) -> ModelSpec:
        action = task.get("action", "")
        complexity = float(task.get("complexity", 0.5))
        needs_tools = bool(task.get("needs_tool_calling", False))
        sovereign_required = action in self.require_sovereign_for
        candidates = list(REGISTRY.values())
        if sovereign_required:
            candidates = [m for m in candidates if m.sovereign]
            if not candidates:
                raise RuntimeError(f"no sovereign model for {action}")
        if needs_tools:
            strong = [m for m in candidates if m.tool_calling_strength >= 0.8]
            if strong:
                candidates = strong
        if complexity > 0.7:
            wide = [m for m in candidates if m.context_window >= 128_000]
            if wide:
                candidates = wide
        candidates.sort(key=lambda m: (m.cost_per_1k / max(m.tool_calling_strength, 0.1), m.latency_ms))
        return candidates[0]

if __name__ == "__main__":
    r = ModelRouter()
    print(asdict(r.select({"action": "domain_lock", "complexity": 0.3})))
    print(asdict(r.select({"action": "diagnose", "complexity": 0.9, "needs_tool_calling": True})))
