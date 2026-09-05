#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Incident Router V9
=========================
Classifica o ciclo numa classe de incidente para o planner não misturar
captura SokkerPRO com restart de Engine.

Classes:
  CORE_SAFETY   — invariante ou syntax
  CORE_DOWN     — bridge/engine/venv
  CODE_DRIFT    — árvore ≠ baseline CLEAN (não auto-patch)
  CAPTURE_ONLY  — feed/extensão/stale/ui view (não mexer em processos)
  OPTIONAL      — ollama/dashboard
  HEALTHY
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

CORE_DOWN_CODES = {
    "VENV_MISSING", "DEPS_MISSING",
    "ENGINE_DOWN", "BRIDGE_DOWN", "ENGINE_ZOMBIE", "BRIDGE_ZOMBIE",
    "PORT_8080_OFF", "PORT_8765_OFF",
}
CAPTURE_CODES = {
    "LIVE_STALE", "LIVE_LATEST_EMPTY", "LIVE_DATA_PARTIAL", "LIVE_JSON_INVALID",
    "UI_STATE_NO_VIEW", "UI_STATE_HTTP", "UI_STATE_UNREACHABLE",
    "EXTENSION_MISSING", "EXTENSION_NO_MANIFEST",
    "GROUNDING_MISSING", "CORNER_EVENTS_EMPTY", "LIVE_DATA_STALE_TEAMS",
}


def classify(findings: Sequence[Dict[str, Any]]) -> Tuple[str, List[str]]:
    open_ = [
        str(f.get("code", ""))
        for f in findings
        if not f.get("fixed") and f.get("severity") not in ("OK", "INFO")
    ]
    reasons: List[str] = []
    if any(c.startswith("SYNTAX_") or c in ("PAPER_TRADE_VIOLATION", "EXECUTION_ALLOWED_VIOLATION") for c in open_):
        reasons = [c for c in open_ if c.startswith("SYNTAX_") or "VIOLATION" in c]
        return "CORE_SAFETY", reasons
    if any(c in CORE_DOWN_CODES for c in open_):
        reasons = [c for c in open_ if c in CORE_DOWN_CODES]
        return "CORE_DOWN", reasons
    if any(c.startswith("CODE_DRIFT_") for c in open_):
        reasons = [c for c in open_ if c.startswith("CODE_DRIFT_")]
        return "CODE_DRIFT", reasons
    if any(c in CAPTURE_CODES for c in open_):
        reasons = [c for c in open_ if c in CAPTURE_CODES]
        return "CAPTURE_ONLY", reasons
    optional = [c for c in open_ if "OLLAMA" in c or "3000" in c or "VOICE" in c]
    if optional and len(optional) == len(open_):
        return "OPTIONAL", optional
    if not open_:
        return "HEALTHY", []
    return "DEGRADED", open_[:8]


def human(cls: str) -> str:
    return {
        "CORE_SAFETY": "Parar e corrigir syntax/safety. Não subir serviços.",
        "CORE_DOWN": "Reparar venv/portas Bridge+Engine.",
        "CODE_DRIFT": "Árvore ≠ CLEAN 12.7 — não reinstalar; comparar ficheiros.",
        "CAPTURE_ONLY": "Core OK. Abrir SokkerPRO live + extensão + F5. Não restart.",
        "OPTIONAL": "Ollama/Voice/Dashboard opcionais.",
        "HEALTHY": "Sem acção urgente.",
        "DEGRADED": "Rever findings HIGH/MEDIUM.",
    }.get(cls, cls)
