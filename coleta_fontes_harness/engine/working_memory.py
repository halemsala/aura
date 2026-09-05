"""Memória de trabalho em RAM, limitada e somente contextual.

A memória guarda um recorte sanitizado dos eventos recentes por partida. Ela
não chama o GLM, não grava no SQLite e não substitui o ledger canônico; apenas
reduz a repetição de contexto durante a sessão do Engine.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict, deque
from typing import Any


def _bounded_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        return max(lower, min(int(os.getenv(name, str(default))), upper))
    except (TypeError, ValueError):
        return default


MAX_MATCHES = _bounded_int("AURA_MEMORY_MAX_MATCHES", 16, 1, 64)
MAX_EVENTS_PER_MATCH = _bounded_int("AURA_MEMORY_MAX_EVENTS", 30, 1, 120)
MAX_EVENT_CHARS = _bounded_int("AURA_MEMORY_EVENT_CHARS", 1200, 256, 4000)
MAX_TOTAL_CHARS = _bounded_int("AURA_MEMORY_TOTAL_CHARS", 64_000, 8_000, 256_000)

_ALLOWED_KEYS = {
    "match_id", "fixture_id", "fixtureId", "minute", "score", "home", "away",
    "corners", "xg", "stats", "events", "asian_corner_odds", "asian_corner_line",
    "calculated_edge", "signal", "decision", "corner_prob", "goal_prob", "pressure",
    "momentum", "regime", "data_integrity", "capturedAt", "timestamp_unix",
}


def _compact(value: Any, limit: int = MAX_EVENT_CHARS) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v, limit) for k, v in value.items() if str(k) in _ALLOWED_KEYS}
    if isinstance(value, list):
        return [_compact(item, limit) for item in value[-16:]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:160]


class WorkingMemory:
    def __init__(self) -> None:
        self._matches: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
        self._lock = threading.RLock()
        self._total_chars = 0

    def add_event(self, fixture_id: str, snapshot: dict[str, Any], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
        key = str(fixture_id or snapshot.get("fixture_id") or snapshot.get("match_id") or "").strip()[:160]
        if not key:
            return {"ok": False, "error": "fixture_id_missing"}
        merged = dict(snapshot or {})
        if isinstance(analysis, dict):
            merged.update({key: value for key, value in analysis.items() if key in _ALLOWED_KEYS})
        event = _compact(merged)
        serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)[:MAX_EVENT_CHARS]
        event = json.loads(serialized)
        event["_memory_ts"] = time.time()
        with self._lock:
            bucket = self._matches.get(key)
            if bucket is None:
                bucket = deque(maxlen=MAX_EVENTS_PER_MATCH)
                self._matches[key] = bucket
            else:
                self._matches.move_to_end(key)
            if bucket:
                self._total_chars -= len(json.dumps(bucket[0], ensure_ascii=False, default=str)) if len(bucket) == bucket.maxlen else 0
            # V23: delta char accounting (O(1) no caminho quente; evita O(N*M) a cada evento)
            event_size = len(json.dumps(event, ensure_ascii=False, default=str))
            if bucket.maxlen is not None and len(bucket) == bucket.maxlen:
                # deque vai descartar o mais antigo no append
                try:
                    evicted = bucket[0]
                    self._total_chars -= len(json.dumps(evicted, ensure_ascii=False, default=str))
                except Exception:
                    pass
            bucket.append(event)
            self._total_chars += event_size
            while len(self._matches) > MAX_MATCHES:
                _, removed = self._matches.popitem(last=False)
                for item in removed:
                    try:
                        self._total_chars -= len(json.dumps(item, ensure_ascii=False, default=str))
                    except Exception:
                        pass
            # trim por teto de chars sem recontar tudo
            while self._total_chars > MAX_TOTAL_CHARS and self._matches:
                oldest_key, oldest_bucket = next(iter(self._matches.items()))
                if oldest_bucket:
                    try:
                        removed_ev = oldest_bucket.popleft()
                        self._total_chars -= len(json.dumps(removed_ev, ensure_ascii=False, default=str))
                    except Exception:
                        break
                if not oldest_bucket:
                    self._matches.pop(oldest_key, None)
            if self._total_chars < 0:
                self._total_chars = 0
            return {"ok": True, "fixture_id": key, "event_count": len(self._matches.get(key, ())), "total_chars": self._total_chars}

    def summary(self, fixture_id: str, max_chars: int = 1600) -> dict[str, Any]:
        key = str(fixture_id or "").strip()[:160]
        with self._lock:
            bucket = self._matches.get(key)
            if not bucket:
                return {"fixture_id": key, "event_count": 0, "events": []}
            self._matches.move_to_end(key)
            events = list(bucket)[-4:]
            result = {"fixture_id": key, "event_count": len(bucket), "events": events}
            raw = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            if len(raw) > max_chars:
                result["events"] = events[-1:]
                raw = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
                if len(raw) > max_chars:
                    result["events"] = []
            return result

    def prompt_fragment(self, fixture_id: str, max_chars: int = 1600) -> str:
        return json.dumps(self.summary(fixture_id, max_chars), ensure_ascii=False, separators=(",", ":"), default=str)[:max_chars]

    def clear(self, fixture_id: str) -> bool:
        key = str(fixture_id or "").strip()[:160]
        with self._lock:
            return self._matches.pop(key, None) is not None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"active": True, "matches": len(self._matches), "max_matches": MAX_MATCHES, "max_events_per_match": MAX_EVENTS_PER_MATCH, "total_chars": self._total_chars, "max_total_chars": MAX_TOTAL_CHARS, "persistence": "RAM_ONLY", "glm_calls": 0, "execution_allowed": False}


MEMORY = WorkingMemory()

__all__ = ["WorkingMemory", "MEMORY"]

