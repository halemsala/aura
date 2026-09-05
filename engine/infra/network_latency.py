# engine/infra/network_latency.py — monitoramento de latência em tempo real
from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
import socket

TARGETS = [
    ("bridge", "http://127.0.0.1:8080/health", 8080),
    ("engine", "http://127.0.0.1:8765/health", 8765),
    ("voice", "http://127.0.0.1:8099/api/voice/health", 8099),
    ("core", "http://127.0.0.1:8088/health", 8088),
]

_HISTORY: Dict[str, Deque[float]] = {n: deque(maxlen=60) for n, _, _ in TARGETS}
_LAST: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
_MONITOR_THREAD: Optional[threading.Thread] = None
_MONITOR_STOP = threading.Event()
_INTERVAL_SEC = 2.0


def ping_http(url: str, timeout: float = 2.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        req = Request(url, method="GET", headers={"Cache-Control": "no-cache"})
        with urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            _ = resp.read(512)
        ms = (time.perf_counter() - t0) * 1000.0
        return {"url": url, "ok": 200 <= code < 400, "status_code": code, "latency_ms": round(ms, 2)}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000.0
        return {"url": url, "ok": False, "error": str(e)[:120], "latency_ms": round(ms, 2)}


def tcp_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ms = (time.perf_counter() - t0) * 1000.0
            return {"host": host, "port": port, "ok": True, "latency_ms": round(ms, 2)}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000.0
        return {"host": host, "port": port, "ok": False, "error": str(e)[:80], "latency_ms": round(ms, 2)}


def _stats(samples: Deque[float]) -> Dict[str, Any]:
    if not samples:
        return {"n": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
    arr = list(samples)
    arr_sorted = sorted(arr)
    n = len(arr_sorted)
    p95 = arr_sorted[min(n - 1, int(n * 0.95))]
    return {
        "n": n,
        "avg_ms": round(statistics.fmean(arr), 2),
        "p50_ms": round(statistics.median(arr), 2),
        "p95_ms": round(p95, 2),
        "min_ms": round(min(arr), 2),
        "max_ms": round(max(arr), 2),
    }


def collect_latency_report() -> Dict[str, Any]:
    http_results: List[Dict[str, Any]] = []
    tcp_results: List[Dict[str, Any]] = []
    now = time.time()
    with _LOCK:
        for name, url, port in TARGETS:
            r = ping_http(url)
            r["name"] = name
            r["ts"] = now
            http_results.append(r)
            if r.get("ok"):
                _HISTORY[name].append(float(r["latency_ms"]))
            _LAST[name] = r
            tcp_results.append(tcp_probe("127.0.0.1", port))
        hist = {n: _stats(_HISTORY[n]) for n, _, _ in TARGETS}
        last = dict(_LAST)
    ok_http = sum(1 for r in http_results if r.get("ok"))
    ok_lat = [r["latency_ms"] for r in http_results if r.get("ok")]
    return {
        "ok": True,
        "ts": now,
        "realtime": True,
        "http": http_results,
        "tcp": tcp_results,
        "history": hist,
        "last": last,
        "summary": {
            "http_up": ok_http,
            "http_total": len(http_results),
            "avg_latency_ms": round(sum(ok_lat) / max(len(ok_lat), 1), 2) if ok_lat else None,
            "worst_ms": round(max(ok_lat), 2) if ok_lat else None,
            "status": "healthy" if ok_http == len(TARGETS) else ("degraded" if ok_http > 0 else "down"),
        },
        "interval_sec": _INTERVAL_SEC,
        "monitor_running": bool(_MONITOR_THREAD and _MONITOR_THREAD.is_alive()),
    }


def _monitor_loop() -> None:
    while not _MONITOR_STOP.is_set():
        try:
            collect_latency_report()
        except Exception:
            pass
        _MONITOR_STOP.wait(_INTERVAL_SEC)


def start_realtime_monitor(interval_sec: float = 2.0) -> Dict[str, Any]:
    global _MONITOR_THREAD, _INTERVAL_SEC
    _INTERVAL_SEC = max(0.5, float(interval_sec))
    if _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
        return {"ok": True, "already": True, "interval_sec": _INTERVAL_SEC}
    _MONITOR_STOP.clear()
    _MONITOR_THREAD = threading.Thread(target=_monitor_loop, name="aura-latency-monitor", daemon=True)
    _MONITOR_THREAD.start()
    return {"ok": True, "started": True, "interval_sec": _INTERVAL_SEC}


def stop_realtime_monitor() -> Dict[str, Any]:
    _MONITOR_STOP.set()
    return {"ok": True, "stopped": True}


if __name__ == "__main__":
    import json
    print(json.dumps(collect_latency_report(), indent=2))
