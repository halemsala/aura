# engine/infra/network_bandwidth.py — monitoramento de largura de banda em tempo real
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

PROBE_URLS = [
    ("bridge", "http://127.0.0.1:8080/health"),
    ("engine", "http://127.0.0.1:8765/health"),
    ("voice", "http://127.0.0.1:8099/api/voice/health"),
    ("core", "http://127.0.0.1:8088/health"),
]

_HISTORY: Dict[str, Deque[float]] = {n: deque(maxlen=60) for n, _ in PROBE_URLS}
_IFACE_HIST: Deque[Tuple[float, int, int]] = deque(maxlen=120)  # ts, rx, tx
_LAST: Dict[str, Any] = {}
_LOCK = threading.Lock()
_MONITOR_THREAD: Optional[threading.Thread] = None
_MONITOR_STOP = threading.Event()
_INTERVAL_SEC = 2.0


def _read_proc_net_dev() -> Optional[Tuple[int, int]]:
    """Soma rx/tx bytes de todas as interfaces (Linux/WSL)."""
    path = "/proc/net/dev"
    if not os.path.exists(path):
        return None
    rx_total = 0
    tx_total = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[2:]
        for line in lines:
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            name = name.strip()
            if name == "lo":
                continue
            parts = rest.split()
            if len(parts) < 9:
                continue
            rx_total += int(parts[0])
            tx_total += int(parts[8])
        return rx_total, tx_total
    except Exception:
        return None


def _read_windows_net() -> Optional[Tuple[int, int]]:
    """Fallback Windows via typeperf / powershell (opcional, best-effort)."""
    try:
        import subprocess
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "(Get-Counter '\\Network Interface(*)\\Bytes Received/sec','\\Network Interface(*)\\Bytes Sent/sec' -ErrorAction SilentlyContinue).CounterSamples | "
            "Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum"
        ]
        # too heavy for tight loop; skip active windows sampling here
        return None
    except Exception:
        return None


def sample_iface_counters() -> Dict[str, Any]:
    now = time.time()
    counters = _read_proc_net_dev()
    if counters is None:
        counters = _read_windows_net()
    if counters is None:
        return {"ok": False, "error": "iface counters unavailable", "platform": os.name}

    rx, tx = counters
    with _LOCK:
        _IFACE_HIST.append((now, rx, tx))
        if len(_IFACE_HIST) < 2:
            return {
                "ok": True,
                "rx_bytes": rx,
                "tx_bytes": tx,
                "rx_bps": None,
                "tx_bps": None,
                "total_bps": None,
                "note": "warmup",
            }
        t0, rx0, tx0 = _IFACE_HIST[-2]
        t1, rx1, tx1 = _IFACE_HIST[-1]
        dt = max(t1 - t0, 1e-6)
        rx_bps = max(0.0, (rx1 - rx0) / dt)
        tx_bps = max(0.0, (tx1 - tx0) / dt)
        return {
            "ok": True,
            "rx_bytes": rx1,
            "tx_bytes": tx1,
            "rx_bps": round(rx_bps, 1),
            "tx_bps": round(tx_bps, 1),
            "total_bps": round(rx_bps + tx_bps, 1),
            "rx_kbps": round(rx_bps / 125.0, 2),  # bytes/s -> kbps (SI-ish: *8/1000)
            "tx_kbps": round(tx_bps / 125.0, 2),
            "total_kbps": round((rx_bps + tx_bps) / 125.0, 2),
            "rx_mbps": round(rx_bps * 8 / 1_000_000, 3),
            "tx_mbps": round(tx_bps * 8 / 1_000_000, 3),
            "total_mbps": round((rx_bps + tx_bps) * 8 / 1_000_000, 3),
        }


def probe_http_throughput(url: str, timeout: float = 2.5) -> Dict[str, Any]:
    """Mede throughput efetivo de um GET (bytes baixados / tempo)."""
    t0 = time.perf_counter()
    try:
        req = Request(url, method="GET", headers={"Cache-Control": "no-cache"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            code = resp.getcode()
        elapsed = max(time.perf_counter() - t0, 1e-6)
        nbytes = len(data)
        bps = nbytes / elapsed
        return {
            "url": url,
            "ok": 200 <= code < 400,
            "status_code": code,
            "bytes": nbytes,
            "elapsed_ms": round(elapsed * 1000, 2),
            "bps": round(bps, 1),
            "kbps": round(bps / 125.0, 2),
            "mbps": round(bps * 8 / 1_000_000, 4),
        }
    except Exception as e:
        elapsed = max(time.perf_counter() - t0, 1e-6)
        return {
            "url": url,
            "ok": False,
            "error": str(e)[:120],
            "elapsed_ms": round(elapsed * 1000, 2),
            "bps": 0.0,
            "kbps": 0.0,
            "mbps": 0.0,
        }


def collect_bandwidth_report() -> Dict[str, Any]:
    now = time.time()
    http_results: List[Dict[str, Any]] = []
    with _LOCK:
        for name, url in PROBE_URLS:
            r = probe_http_throughput(url)
            r["name"] = name
            r["ts"] = now
            http_results.append(r)
            if r.get("ok") and r.get("bps", 0) > 0:
                _HISTORY[name].append(float(r["bps"]))
            _LAST[name] = r
        hist = {}
        for n, _ in PROBE_URLS:
            samples = list(_HISTORY[n])
            if samples:
                hist[n] = {
                    "n": len(samples),
                    "avg_bps": round(sum(samples) / len(samples), 1),
                    "max_bps": round(max(samples), 1),
                    "avg_kbps": round((sum(samples) / len(samples)) / 125.0, 2),
                }
            else:
                hist[n] = {"n": 0, "avg_bps": None, "max_bps": None, "avg_kbps": None}
        last = dict(_LAST)

    iface = sample_iface_counters()
    ok_n = sum(1 for r in http_results if r.get("ok"))
    return {
        "ok": True,
        "ts": now,
        "realtime": True,
        "http_probes": http_results,
        "interface": iface,
        "history": hist,
        "last": last,
        "summary": {
            "services_up": ok_n,
            "services_total": len(PROBE_URLS),
            "iface_total_mbps": iface.get("total_mbps"),
            "iface_rx_mbps": iface.get("rx_mbps"),
            "iface_tx_mbps": iface.get("tx_mbps"),
            "status": "healthy" if ok_n == len(PROBE_URLS) else ("degraded" if ok_n > 0 else "down"),
        },
        "interval_sec": _INTERVAL_SEC,
        "monitor_running": bool(_MONITOR_THREAD and _MONITOR_THREAD.is_alive()),
    }


def _monitor_loop() -> None:
    while not _MONITOR_STOP.is_set():
        try:
            collect_bandwidth_report()
        except Exception:
            pass
        _MONITOR_STOP.wait(_INTERVAL_SEC)


def start_realtime_monitor(interval_sec: float = 2.0) -> Dict[str, Any]:
    global _MONITOR_THREAD, _INTERVAL_SEC
    _INTERVAL_SEC = max(0.5, float(interval_sec))
    if _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
        return {"ok": True, "already": True, "interval_sec": _INTERVAL_SEC}
    _MONITOR_STOP.clear()
    _MONITOR_THREAD = threading.Thread(target=_monitor_loop, name="aura-bandwidth-monitor", daemon=True)
    _MONITOR_THREAD.start()
    return {"ok": True, "started": True, "interval_sec": _INTERVAL_SEC}


def stop_realtime_monitor() -> Dict[str, Any]:
    _MONITOR_STOP.set()
    return {"ok": True, "stopped": True}


if __name__ == "__main__":
    import json
    print(json.dumps(collect_bandwidth_report(), indent=2))
