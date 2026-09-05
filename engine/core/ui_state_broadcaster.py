"""Broadcaster de UI em memória; servidor WebSocket deve ser habilitado separadamente."""
from __future__ import annotations

import json
from copy import deepcopy
from threading import RLock
from typing import Any, Dict


class UIBroadcaster:
    def __init__(self) -> None:
        self._latest_state: Dict[str, Any] = {}
        self._lock = RLock()

    def update_state(self, new_state: Dict[str, Any]) -> None:
        if not isinstance(new_state, dict):
            return
        with self._lock:
            self._latest_state = deepcopy(new_state)

    def latest_state(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._latest_state)

    def serialize(self) -> str:
        return json.dumps(self.latest_state(), ensure_ascii=False, separators=(",", ":"))

    def start_server(self, *args, **kwargs) -> bool:
        return False


BROADCASTER = UIBroadcaster()
__all__ = ["UIBroadcaster", "BROADCASTER"]
