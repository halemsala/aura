from __future__ import annotations
import threading
from typing import Any, Optional
from engine.core.ttl_cache import TTLCache

_SNAPSHOT_CACHE = TTLCache(default_ttl_seconds=60.0)
_ANALYSIS_CACHE = TTLCache(default_ttl_seconds=60.0)
_COOLDOWN_CACHE = TTLCache(default_ttl_seconds=60.0)
_BRAIN_STATE_CACHE = TTLCache(default_ttl_seconds=300.0)
_lock = threading.RLock()


def get_snapshot(key: str) -> Optional[Any]:
    return _SNAPSHOT_CACHE.get(key)


def set_snapshot(key: str, value: Any) -> None:
    with _lock:
        _SNAPSHOT_CACHE.set(key, value)


def get_analysis(key: str) -> Optional[Any]:
    return _ANALYSIS_CACHE.get(key)


def set_analysis(key: str, value: Any) -> None:
    with _lock:
        _ANALYSIS_CACHE.set(key, value)


_COOLDOWN_SENTINEL = object()


def is_cooldown_active(fixture_id: str) -> bool:
    return _COOLDOWN_CACHE.get(fixture_id, _COOLDOWN_SENTINEL) is not _COOLDOWN_SENTINEL


def set_cooldown(fixture_id: str) -> None:
    with _lock:
        _COOLDOWN_CACHE.set(fixture_id, True)


def get_brain_state(fixture_id: str) -> Optional[dict]:
    return _BRAIN_STATE_CACHE.get(fixture_id)


def set_brain_state(fixture_id: str, state: dict) -> None:
    with _lock:
        _BRAIN_STATE_CACHE.set(fixture_id, state)
