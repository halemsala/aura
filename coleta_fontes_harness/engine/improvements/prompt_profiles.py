# Item 36 — perfis de sampling por tarefa
from __future__ import annotations
from typing import Dict


PROFILES: Dict[str, Dict[str, float]] = {
    "signal_structured": {"temperature": 0.1, "max_tokens": 256},
    "tactical_analysis": {"temperature": 0.4, "max_tokens": 512},
    "creative": {"temperature": 0.7, "max_tokens": 1024},
    "compaction": {"temperature": 0.0, "max_tokens": 400},
}


def sampling_for_task(task: str) -> Dict[str, float]:
    return dict(PROFILES.get(task, PROFILES["tactical_analysis"]))
