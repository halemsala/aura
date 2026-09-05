"""Circuit breaker com backoff. Impede reinícios indefinidos do mesmo serviço."""
import threading
import time
from . import paths, util

STATE_PATH = paths.DATA_ROOT / "circuit_breaker.json"
_lock = threading.Lock()

DEFAULTS = {
    "max_failures": 3,
    "open_s": 300,
    "window_s": 900,
}


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        import json
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict) -> None:
    util.atomic_write_json(STATE_PATH, data)


def allow(name: str, max_failures: int = None, open_s: int = None, window_s: int = None) -> dict:
    """Devolve {allowed, reason, failures, opened_until}."""
    max_failures = int(max_failures if max_failures is not None else DEFAULTS["max_failures"])
    open_s = int(open_s if open_s is not None else DEFAULTS["open_s"])
    window_s = int(window_s if window_s is not None else DEFAULTS["window_s"])
    now = time.time()
    with _lock:
        data = _load()
        st = data.get(name) or {"failures": [], "opened_until": 0}
        opened_until = float(st.get("opened_until") or 0)
        if opened_until > now:
            return {"allowed": False, "reason": "circuit_open",
                    "failures": len(st.get("failures") or []),
                    "opened_until": opened_until, "retry_in_s": int(opened_until - now)}
        st["failures"] = [t for t in (st.get("failures") or []) if now - float(t) <= window_s]
        data[name] = st
        _save(data)
        return {"allowed": True, "reason": "closed",
                "failures": len(st["failures"]), "opened_until": 0, "retry_in_s": 0}


def record_failure(name: str, max_failures: int = None, open_s: int = None, window_s: int = None) -> dict:
    max_failures = int(max_failures if max_failures is not None else DEFAULTS["max_failures"])
    open_s = int(open_s if open_s is not None else DEFAULTS["open_s"])
    window_s = int(window_s if window_s is not None else DEFAULTS["window_s"])
    now = time.time()
    with _lock:
        data = _load()
        st = data.get(name) or {"failures": [], "opened_until": 0}
        fails = [t for t in (st.get("failures") or []) if now - float(t) <= window_s]
        fails.append(now)
        st["failures"] = fails
        if len(fails) >= max_failures:
            st["opened_until"] = now + open_s
        data[name] = st
        _save(data)
        return {"failures": len(fails), "opened": len(fails) >= max_failures,
                "opened_until": st.get("opened_until") or 0}


def record_success(name: str) -> None:
    with _lock:
        data = _load()
        st = data.get(name) or {}
        st["failures"] = []
        st["opened_until"] = 0
        data[name] = st
        _save(data)
