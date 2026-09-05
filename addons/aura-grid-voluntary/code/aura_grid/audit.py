"""Structured JSONL audit logger for AURA Grid."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: str | Path, *, also_print: bool = True) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a", encoding="utf-8")
        self._lock = threading.Lock()
        self.also_print = also_print

    def log(self, event: str, **kwargs: Any) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            self._fp.write(line + "\n")
            self._fp.flush()
        if self.also_print:
            print(f"[{event}] {kwargs}")

    def close(self) -> None:
        with self._lock:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                pass
