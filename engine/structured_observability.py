# -*- coding: utf-8 -*-
"""
PILAR 8 - Observabilidade Estruturada
AURA QUANT-X v12.7.0-RECONSOLIDADO

Logger JSONL com correlação, buffer circular, mascaramento e APIs compatíveis
com os anexos. O servidor do Engine usa `emit()`; as APIs `log_*` permanecem
para diagnóstico e testes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("aura.pilar8.observability")
MAX_FILE_SIZE_MB = 10
MAX_FILES = 3
BUFFER_SIZE = 128
FLUSH_INTERVAL_S = 5.0


class EventLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventType(Enum):
    CUSTOM = "custom"
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    SIGNAL_GENERATED = "signal_generated"
    SYSTEM_ERROR = "system_error"
    DATA_INTEGRITY = "data_integrity"


_SECRET_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*["\']?([^\s"\']+)["\']?'), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)([a-zA-Z0-9\-._~+/]+=*)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbot\d{8,}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED]"),
]


def mask_secrets(text: str) -> str:
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class DataMasker:
    @staticmethod
    def mask_field(value: Any, field_name: str = "") -> Any:
        if value is None or not isinstance(value, str):
            return value
        sensitive = any(token in str(field_name).lower() for token in ("token", "secret", "password", "api_key", "apikey", "authorization"))
        return "[REDACTED]" if sensitive else mask_secrets(value)

    @classmethod
    def mask_dict(cls, data: Any, exclude_keys: Optional[set] = None) -> Any:
        excluded = exclude_keys or set()
        if isinstance(data, dict):
            return {str(k): (v if str(k) in excluded else cls.mask_dict(v, excluded) if isinstance(v, (dict, list)) else cls.mask_field(v, str(k))) for k, v in data.items()}
        if isinstance(data, list):
            return [cls.mask_dict(v, excluded) for v in data]
        return cls.mask_field(data)


@dataclass
class StructuredEvent:
    correlation_id: str = ""
    ts: float = 0.0
    level: str = "INFO"
    method: str = ""
    route: str = ""
    duration_ms: float = 0.0
    data_integrity: str = "ok"
    message: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    timestamp: Any = None
    event_type: str = EventType.CUSTOM.value

    def __post_init__(self) -> None:
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())
        if not self.ts:
            self.ts = time.time()
        if isinstance(self.level, EventLevel):
            self.level = self.level.value
        if isinstance(self.event_type, EventType):
            self.event_type = self.event_type.value
        if self.timestamp is None:
            self.timestamp = self.ts

    @property
    def type(self) -> str:
        return self.event_type

    def to_dict(self) -> Dict[str, Any]:
        metadata = DataMasker.mask_dict(self.extra)
        return {
            "id": self.correlation_id,
            "event_id": self.correlation_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "ts": self.ts,
            "type": self.event_type,
            "event_type": self.event_type,
            "level": self.level,
            "method": self.method,
            "route": self.route,
            "duration_ms": self.duration_ms,
            "data_integrity": self.data_integrity,
            "message": mask_secrets(str(self.message)),
            "metadata": metadata,
            "extra": metadata,
            **({"http_status": self.extra.get("http_status")} if "http_status" in self.extra else {}),
        }

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), default=str)


class CircularEventBuffer:
    def __init__(self, capacity: int = BUFFER_SIZE):
        if int(capacity) <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self._items: List[StructuredEvent] = []
        self._lock = threading.RLock()
        self._total_inserted = 0
        self._total_overwritten = 0

    def push(self, event: StructuredEvent) -> None:
        with self._lock:
            self._total_inserted += 1
            if len(self._items) >= self.capacity:
                self._items.pop(0)
                self._total_overwritten += 1
            self._items.append(event)

    def get_recent(self, count: Optional[int] = None) -> List[StructuredEvent]:
        with self._lock:
            return list(self._items[-int(count):]) if count else list(self._items)

    def clear(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"capacity": self.capacity, "count": len(self._items), "total_inserted": self._total_inserted, "total_overwritten": self._total_overwritten}


class StructuredObservability:
    def __init__(self, log_dir: Optional[str] = None, buffer_size: int = BUFFER_SIZE):
        self.log_dir = str(log_dir or Path(__file__).resolve().parent / "artifacts" / "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self._buffer = CircularEventBuffer(buffer_size)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._started = False
        self._flush_count = 0
        self._error_count = 0
        self._correlation = str(uuid.uuid4())
        self._daemon = threading.Thread(target=self._flush_loop, name="AuraObsFlush", daemon=True)
        self._daemon.start()
        self._started = True
        logger.info("Observabilidade estruturada ativa | dir=%s", self.log_dir)

    def start(self) -> "StructuredObservability":
        return self

    def stop(self) -> None:
        self.shutdown()

    def new_correlation(self) -> str:
        self._correlation = str(uuid.uuid4())
        return self._correlation

    @property
    def correlation_id(self) -> str:
        return self._correlation

    def _append(self, event: StructuredEvent) -> str:
        self._buffer.push(event)
        if self._buffer.get_stats()["count"] >= self._buffer.capacity:
            self._force_flush()
        return event.correlation_id

    def emit(self, level: EventLevel, method: str, route: str, duration_ms: float, message: str, data_integrity: str = "ok", extra: Optional[Dict[str, Any]] = None) -> None:
        self._append(StructuredEvent(correlation_id=self._correlation, ts=time.time(), level=level, method=method, route=route, duration_ms=duration_ms, data_integrity=data_integrity, message=message, extra=extra or {}, event_type=EventType.CUSTOM.value))

    def log_event(self, event_type: Any = EventType.CUSTOM, message: str = "", correlation_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, level: Any = EventLevel.INFO, **kwargs: Any) -> str:
        event_name = event_type.value if isinstance(event_type, EventType) else str(event_type or EventType.CUSTOM.value)
        level_name = level.value if isinstance(level, EventLevel) else str(level or "INFO")
        cid = correlation_id or uuid.uuid4().hex[:8]
        event = StructuredEvent(correlation_id=cid, ts=time.time(), level=level_name, method=str(kwargs.get("method") or ""), route=str(kwargs.get("route") or ""), duration_ms=float(kwargs.get("duration_ms") or 0.0), data_integrity=str(kwargs.get("data_integrity") or "ok"), message=message, extra=metadata or kwargs, event_type=event_name)
        return self._append(event)

    def log_api_request(self, method: str, route: str, correlation_id: Optional[str] = None, **metadata: Any) -> str:
        return self.log_event(EventType.API_REQUEST, f"{method} {route}", correlation_id, metadata, method=method, route=route)

    def log_api_response(self, method: str, route: str, http_status: int, duration_ms: float, correlation_id: Optional[str] = None, **metadata: Any) -> str:
        cid = correlation_id or self._correlation
        return self.log_event(EventType.API_RESPONSE, f"{method} {route} -> {http_status}", cid, {**metadata, "http_status": int(http_status)}, method=method, route=route, duration_ms=duration_ms)

    def log_signal(self, signal: str, fixture_id: str = "", corner_prob: Optional[float] = None, edge: Optional[float] = None, **metadata: Any) -> str:
        return self.log_event(EventType.SIGNAL_GENERATED, f"{signal} fixture={fixture_id}", metadata={**metadata, "fixture_id": fixture_id, "corner_prob": corner_prob, "edge": edge})

    def log_error(self, error: Exception, context: str = "", **metadata: Any) -> str:
        return self.log_event(EventType.SYSTEM_ERROR, f"{context}: {error}".strip(": "), level=EventLevel.ERROR, metadata=metadata)

    def log_data_integrity(self, issues: Iterable[str], severity: str = "warning", **metadata: Any) -> str:
        issues_list = list(issues or [])
        return self.log_event(EventType.DATA_INTEGRITY, f"{len(issues_list)} issues ({severity})", metadata={**metadata, "issues": issues_list})

    def _flush_unlocked(self) -> int:
        events = self._buffer.get_recent()
        if not events:
            return 0
        self._buffer.clear()
        path = Path(self.log_dir) / "runtime_events.jsonl"
        try:
            with path.open("a", encoding="utf-8") as handle:
                for event in events:
                    handle.write(event.to_jsonl() + "\n")
            self._flush_count += 1
            self._rotate_if_needed(path)
            return len(events)
        except Exception as exc:
            self._error_count += 1
            logger.error("Falha no flush de observabilidade: %s", exc)
            return 0

    def _force_flush(self) -> int:
        with self._lock:
            return self._flush_unlocked()

    def force_flush(self) -> int:
        return self._force_flush()

    def _flush_loop(self) -> None:
        while not self._stop.wait(FLUSH_INTERVAL_S):
            self._force_flush()

    def _rotate_if_needed(self, path: Path) -> None:
        try:
            if path.stat().st_size / (1024 * 1024) < MAX_FILE_SIZE_MB:
                return
            for index in range(MAX_FILES - 1, 0, -1):
                src = path.with_name(f"runtime_events.{index}.jsonl")
                dst = path.with_name(f"runtime_events.{index + 1}.jsonl")
                if src.exists():
                    src.replace(dst)
            path.replace(path.with_name("runtime_events.1.jsonl"))
        except Exception as exc:
            logger.error("Erro na rotação de log: %s", exc)

    def _events_from_disk(self) -> List[Dict[str, Any]]:
        path = Path(self.log_dir) / "runtime_events.jsonl"
        if not path.exists():
            return []
        result = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                result.append(json.loads(line))
            except ValueError:
                continue
        return result

    def get_events_by_correlation(self, correlation_id: str) -> List[Dict[str, Any]]:
        self._force_flush()
        return [item for item in self._events_from_disk() if item.get("correlation_id") == correlation_id]

    def get_events_by_type(self, event_type: Any, limit: int = 100) -> List[Dict[str, Any]]:
        self._force_flush()
        name = event_type.value if isinstance(event_type, EventType) else str(event_type)
        return [item for item in self._events_from_disk() if item.get("type") == name][-limit:]

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        self._force_flush()
        return self._events_from_disk()[-max(1, int(limit)):]

    def get_stats(self) -> Dict[str, Any]:
        stats = self._buffer.get_stats()
        stats["flush_count"] = self._flush_count
        stats["error_count"] = self._error_count
        stats["current_file"] = str(Path(self.log_dir) / "runtime_events.jsonl")
        stats["buffer"] = stats.copy()
        return stats

    def shutdown(self) -> None:
        if self._stop.is_set():
            self._force_flush()
            return
        self._stop.set()
        if self._daemon and self._daemon.is_alive():
            self._daemon.join(timeout=3.0)
        self._force_flush()


_obs: Optional[StructuredObservability] = None
_obs_lock = threading.Lock()


def get_observability() -> StructuredObservability:
    global _obs
    with _obs_lock:
        if _obs is None:
            _obs = StructuredObservability()
        return _obs
