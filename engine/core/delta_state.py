from __future__ import annotations
import hashlib
import json
from typing import Any, Dict


class DeltaStateEncoder:
    """Codifica apenas mudancas desde a ultima interacao (~50-150 tokens)."""

    def __init__(self) -> None:
        self._last_state_hash: str = ""
        self._last_compressed: str = ""

    def encode(self, snapshot: dict) -> str:
        if not isinstance(snapshot, dict):
            return "[CTX:invalid]"
        core = {
            "m": snapshot.get("minute"),
            "c": snapshot.get("corners"),
            "s": snapshot.get("score"),
            "e": snapshot.get("edge") or snapshot.get("calculated_edge"),
            "d": snapshot.get("decision"),
            "p": snapshot.get("pressure"),
        }
        core = {k: v for k, v in core.items() if v is not None}
        state_hash = hashlib.blake2b(
            json.dumps(core, sort_keys=True, default=str).encode(),
            digest_size=8,
        ).hexdigest()
        if state_hash == self._last_state_hash:
            return "[D: unchanged]"
        self._last_state_hash = state_hash
        dense = "|".join(f"{k}:{v}" for k, v in core.items())
        self._last_compressed = dense
        return dense

    @property
    def last_hash(self) -> str:
        return self._last_state_hash


delta_state_encoder = DeltaStateEncoder()
