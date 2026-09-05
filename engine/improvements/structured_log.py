# Item 97 — logging JSON estruturado
from __future__ import annotations
import json
import time
from typing import Any, Dict, Optional


def log_event(level: str, event: str, **fields: Any) -> None:
    row: Dict[str, Any] = {
        "ts": time.time(),
        "level": level,
        "event": event,
    }
    row.update(fields)
    print(json.dumps(row, ensure_ascii=False, default=str), flush=True)
