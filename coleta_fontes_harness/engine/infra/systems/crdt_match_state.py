from __future__ import annotations
import json
import time
from typing import Any, Dict, Optional

class CRDTMatchState:
    def __init__(self, node_id: str = "engine") -> None:
        self.node_id = node_id
        self._doc = None
        self._map = None
        try:
            from pycrdt import Doc, Map
            self._doc = Doc()
            self._map = Map()
            self._doc["match"] = self._map
            self._backend = "pycrdt"
        except Exception:
            self._local: Dict[str, Any] = {}
            self._backend = "dict_fallback"

    def set_field(self, key: str, value: Any) -> None:
        if self._backend == "pycrdt" and self._map is not None:
            self._map[key] = value
        else:
            self._local[key] = value

    def get_field(self, key: str, default: Any = None) -> Any:
        if self._backend == "pycrdt" and self._map is not None:
            try:
                return self._map[key]
            except Exception:
                return default
        return self._local.get(key, default)

    def update_corner_tick(self, minute: float, corners: int, line: float) -> Dict[str, Any]:
        self.set_field("minute", float(minute))
        self.set_field("corners", int(corners))
        self.set_field("line", float(line))
        self.set_field("ts", time.time())
        self.set_field("node", self.node_id)
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        if self._backend == "pycrdt" and self._map is not None:
            out = {}
            for k in ("minute", "corners", "line", "ts", "node"):
                try:
                    out[k] = self._map[k]
                except Exception:
                    pass
            out["backend"] = self._backend
            return out
        snap = dict(self._local)
        snap["backend"] = self._backend
        return snap

    def merge_update(self, update_bytes: bytes) -> bool:
        if self._backend != "pycrdt" or self._doc is None:
            return False
        try:
            self._doc.apply_update(update_bytes)
            return True
        except Exception:
            return False

    def get_update(self) -> Optional[bytes]:
        if self._backend != "pycrdt" or self._doc is None:
            return None
        try:
            return bytes(self._doc.get_update())
        except Exception:
            return None
