"""Persistência atômica de snapshot local para recuperação após crash."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


class StateSnapshot:
    def __init__(self, path: str | Path = "data/aura_state_snapshot.json") -> None:
        self.path = Path(path)

    def save(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("state deve ser dict")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}


__all__ = ["StateSnapshot"]
