"""Eventos locais, redigidos e estruturados (JSONL) para diagnóstico do addon."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SENSITIVE = {
    "token", "secret", "password", "authorization", "api_key",
    "audio", "credential", "cpf", "email", "cookie", "session",
}


def redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[depth-limited]"
    if isinstance(value, Mapping):
        return {
            str(k): (
                "[redacted]"
                if any(s in str(k).lower() for s in _SENSITIVE)
                else redact(v, depth=depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v, depth=depth + 1) for v in list(value)[:32]]
    if isinstance(value, str):
        return value[:1000]
    return value


def make_event(event_type: str, payload: Mapping[str, Any], *, trace_id: str) -> dict[str, Any]:
    safe = redact(payload)
    body = json.dumps(safe, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event_type": event_type[:120],
        "trace_id": trace_id[:64],
        "payload": safe,
        "payload_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "paper_trade": True,
        "execution_allowed": False,
    }


class AuditLogger:
    """Logger estruturado offline em JSONL (SIEM-friendly)."""

    def __init__(self, filepath: str | Path = "aura_audit.jsonl") -> None:
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            self.filepath.write_text("", encoding="utf-8")

    def log(self, event_type: str, payload: Mapping[str, Any], trace_id: str) -> dict[str, Any]:
        event = make_event(event_type, payload, trace_id=trace_id)
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event
