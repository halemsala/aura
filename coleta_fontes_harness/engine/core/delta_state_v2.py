# engine/core/delta_state_v2.py — Auditoria Radical 2.1
from __future__ import annotations
import hashlib
import json
from typing import Any


class SemanticDeltaCompactor:
    """Delta semântico com hash de estado — skip LLM se inalterado."""

    __slots__ = ("_last_hash", "_last_payload", "_whitelist")

    def __init__(self, whitelist: set[str] | None = None):
        self._last_hash: str = ""
        self._last_payload: dict[str, Any] = {}
        self._whitelist = whitelist or {
            "fixture_id", "minute", "score", "pressure", "xG", "corners",
            "decision", "risk", "odds_velocity", "dual_pressure", "data_quality",
        }

    def compact(self, payload: dict[str, Any]) -> dict[str, Any]:
        filtered = {k: v for k, v in payload.items() if k in self._whitelist}
        h = hashlib.blake2b(
            json.dumps(filtered, sort_keys=True, default=str).encode(),
            digest_size=8,
        ).hexdigest()
        if h == self._last_hash:
            return {"delta": "no_change", "hash": h}
        delta = {}
        for k, v in filtered.items():
            if self._last_payload.get(k) != v:
                delta[k] = v
        self._last_hash = h
        self._last_payload = filtered
        return {"delta": delta, "hash": h, "timestamp": payload.get("ts")}
