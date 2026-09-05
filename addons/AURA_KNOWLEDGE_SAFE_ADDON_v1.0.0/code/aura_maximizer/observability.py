"""Eventos locais, redigidos e encadeáveis para diagnóstico do addon."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

_SENSITIVE = {"token", "secret", "password", "authorization", "api_key", "audio", "credential"}


def redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[depth-limited]"
    if isinstance(value, Mapping):
        return {
            str(k): "[redacted]" if any(s in str(k).lower() for s in _SENSITIVE) else redact(v, depth=depth + 1)
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
