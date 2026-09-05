from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

class SlidingWindowGraph:
    WINDOW_SEC = 900  # 15 minutes

    def __init__(self, archive_dir: str = "./graph_archive") -> None:
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: List[Dict[str, str]] = []
        self._g = nx.DiGraph() if HAS_NX else None
        self._current_time: float = 0.0

    def add_node_and_edge(self, time_min: float, data: Dict[str, Any], cause: str = "", effect: str = "") -> None:
        key = f"time_{int(time_min)}"
        self._current_time = max(self._current_time, float(time_min) * 60.0, time.time())
        node = {"minute": float(time_min), "ts": time.time(), **data}
        self._nodes[key] = node
        if self._g is not None:
            self._g.add_node(key, **node)
        if cause:
            e = {"from": cause, "to": key, "rel": "causa"}
            self._edges.append(e)
            if self._g is not None:
                self._g.add_edge(cause, key, rel="causa")
        if effect:
            e = {"from": key, "to": effect, "rel": "efeito"}
            self._edges.append(e)
            if self._g is not None:
                self._g.add_edge(key, effect, rel="efeito")
        self._gc()

    def _gc(self) -> None:
        cutoff_min = (self._current_time / 60.0) - (self.WINDOW_SEC / 60.0)
        # if current_time is wall clock, also accept minute-based window
        if self._current_time > 1e9:
            cutoff_min = (time.time() - self.WINDOW_SEC)  # not used as minute
            stale = [k for k, v in self._nodes.items() if float(v.get("ts", 0)) < time.time() - self.WINDOW_SEC]
        else:
            stale = [k for k, v in self._nodes.items() if float(v.get("minute", 0)) < float(self._current_time) / 60.0 - 15.0]
        if not stale:
            # minute window relative to max minute
            if self._nodes:
                max_m = max(float(v.get("minute", 0)) for v in self._nodes.values())
                stale = [k for k, v in self._nodes.items() if float(v.get("minute", 0)) < max_m - 15.0]
        if not stale:
            return
        archived = {"nodes": {}, "edges": []}
        for k in stale:
            archived["nodes"][k] = self._nodes.pop(k, {})
            if self._g is not None and self._g.has_node(k):
                self._g.remove_node(k)
        self._edges = [e for e in self._edges if e.get("from") not in stale and e.get("to") not in stale]
        path = self.archive_dir / f"graph_{int(time.time())}.json"
        path.write_text(json.dumps(archived, ensure_ascii=False), encoding="utf-8")

    def size(self) -> int:
        return len(self._nodes)
