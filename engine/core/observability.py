#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Observabilidade: metricas + /metrics + /statusz + alertas.
Local: engine/core/observability.py
Dependencias: NENHUMA (stdlib). Python 3.9+. Windows OK.
"""
from __future__ import annotations

import atexit
import bisect
import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("aura.metrics")

__version__ = "1.0.0"
__all__ = [
    "Registry", "Counter", "Gauge", "Histogram", "REG",
    "MetricsServer", "AlertRule", "default_alerts",
    "gather_metrics", "gather_status", "dig", "MetricsCollector", "METRICS",
]

LATENCY_BUCKETS_US: Tuple[float, ...] = (
    10.0, 25.0, 50.0, 100.0, 250.0, 500.0,
    1_000.0, 2_500.0, 5_000.0, 10_000.0, 25_000.0,
    50_000.0, 100_000.0, 250_000.0, 500_000.0,
)

_METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)
    return dt.isoformat(timespec="seconds")


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_labels(lk: Tuple[Tuple[str, str], ...]) -> str:
    if not lk:
        return ""
    return "{" + ",".join(f'{k}="{_esc(v)}"' for k, v in lk) + "}"


def _merge_le(lstr: str, le: str) -> str:
    if not lstr:
        return f'{{le="{le}"}}'
    return lstr[:-1] + f',le="{le}"' + "}"


def dig(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _flatten(prefix: str, obj: Any, out: Dict[str, float]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = re.sub(r"[^a-zA-Z0-9_]", "_", str(k)).strip("_") or "x"
            _flatten(f"{prefix}_{key}", v, out)
    elif isinstance(obj, bool):
        out[prefix] = 1.0 if obj else 0.0
    elif isinstance(obj, (int, float)):
        f = float(obj)
        if math.isfinite(f):
            out[prefix] = f


class _NullMetric:
    __slots__ = ()
    def inc(self, amount: float = 1.0) -> None:
        pass
    def dec(self, amount: float = 1.0) -> None:
        pass
    def set(self, value: float) -> None:
        pass
    def observe(self, value: float) -> None:
        pass


_NULL = _NullMetric()


class Counter:
    __slots__ = ("value", "_lock")
    def __init__(self) -> None:
        self.value = 0.0
        self._lock = threading.Lock()
    def inc(self, amount: float = 1.0) -> None:
        if amount:
            with self._lock:
                self.value += float(amount)
    def get(self) -> float:
        with self._lock:
            return self.value


class Gauge:
    __slots__ = ("value", "_lock")
    def __init__(self) -> None:
        self.value: Optional[float] = None
        self._lock = threading.Lock()
    def set(self, v: float) -> None:
        with self._lock:
            self.value = float(v)
    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            base = self.value if self.value is not None else 0.0
            self.value = base + float(amount)
    def dec(self, amount: float = 1.0) -> None:
        self.inc(-float(amount))
    def get(self) -> Optional[float]:
        with self._lock:
            return self.value


class Histogram:
    __slots__ = ("bounds", "counts", "sum", "count", "_lock")
    def __init__(self, buckets) -> None:
        b = sorted({float(x) for x in buckets if math.isfinite(float(x)) and float(x) > 0})
        if not b:
            b = [1.0]
        self.bounds: Tuple[float, ...] = tuple(b)
        self.counts: List[int] = [0] * (len(b) + 1)
        self.sum = 0.0
        self.count = 0
        self._lock = threading.Lock()
    def observe(self, v: float) -> None:
        v = float(v)
        if not math.isfinite(v):
            return
        with self._lock:
            self.sum += v
            self.count += 1
            self.counts[bisect.bisect_left(self.bounds, v)] += 1
    def quantile_est(self, q: float) -> Optional[float]:
        with self._lock:
            if self.count == 0:
                return None
            rank = max(0.0, min(1.0, float(q))) * self.count
            cum = 0
            for i in range(len(self.counts)):
                cum += self.counts[i]
                if cum >= rank:
                    if i >= len(self.bounds):
                        return self.bounds[-1]
                    hi = self.bounds[i]
                    lo = self.bounds[i - 1] if i > 0 else 0.0
                    before = cum - self.counts[i]
                    c = self.counts[i]
                    if c <= 0 or hi <= lo:
                        return hi
                    frac = min(1.0, (rank - before) / c)
                    return lo + (hi - lo) * frac
            return self.bounds[-1]


class _Timer:
    __slots__ = ("_h", "_scale", "_t0")
    def __init__(self, h: Histogram, scale: float) -> None:
        self._h = h
        self._scale = scale
        self._t0 = 0.0
    def __enter__(self) -> "_Timer":
        self._t0 = time.perf_counter()
        return self
    def __exit__(self, *exc) -> bool:
        self._h.observe((time.perf_counter() - self._t0) * self._scale)
        return False


class Registry:
    def __init__(self, max_series: int = 4096):
        self.max_series = int(max_series)
        self._lock = threading.RLock()
        self._series: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Any] = {}
        self._kinds: Dict[str, str] = {}
        self._helps: Dict[str, str] = {}
        self._hbuckets: Dict[str, Tuple[float, ...]] = {}
        self._dropped = 0
        self._created = time.time()

    def _canon_labels(self, labels: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
        out = []
        for k, v in (labels or {}).items():
            if not _LABEL_NAME_RE.match(str(k)):
                raise ValueError(f"nome de label invalido: {k!r}")
            out.append((str(k), str(v)[:120]))
        return tuple(sorted(out))

    def _get(self, kind: str, name: str, help: str,
             labels: Dict[str, Any], buckets: Optional[Tuple[float, ...]]) -> Any:
        if not _METRIC_NAME_RE.match(name):
            raise ValueError(f"nome de metrica invalido: {name!r}")
        lk = self._canon_labels(labels or {})
        key = (name, lk)
        with self._lock:
            if key in self._series:
                return self._series[key]
            prev = self._kinds.get(name)
            if prev is not None and prev != kind:
                raise ValueError(f"{name!r} ja registrado como {prev} (tentativa: {kind})")
            if len(self._series) >= self.max_series:
                # conta cada chave rejeitada uma vez (nao infla em re-get)
                if not hasattr(self, "_null_keys"):
                    self._null_keys = set()
                if key not in self._null_keys:
                    self._null_keys.add(key)
                    self._dropped += 1
                return _NULL
            self._kinds[name] = kind
            if help:
                self._helps.setdefault(name, str(help))
            if kind == "counter":
                m: Any = Counter()
            elif kind == "gauge":
                m = Gauge()
            else:
                bk = buckets or LATENCY_BUCKETS_US
                self._hbuckets.setdefault(name, bk)
                m = Histogram(self._hbuckets[name])
            self._series[key] = m
            return m

    def counter(self, name: str, help: str = "", **labels) -> Any:
        m = self._get("counter", name, help, labels, None)
        return m if isinstance(m, Counter) else _NULL

    def gauge(self, name: str, help: str = "", **labels) -> Any:
        m = self._get("gauge", name, help, labels, None)
        return m if isinstance(m, Gauge) else _NULL

    def histogram(self, name: str, buckets=None, help: str = "", **labels) -> Any:
        bk = tuple(sorted({float(b) for b in (buckets or LATENCY_BUCKETS_US)}))
        m = self._get("histogram", name, help, labels, bk)
        return m if isinstance(m, Histogram) else _NULL

    def timer_us(self, name: str, help: str = "", **labels) -> _Timer:
        return _Timer(self.histogram(name, LATENCY_BUCKETS_US, help, **labels), 1e6)

    def timer_s(self, name: str, help: str = "", **labels) -> _Timer:
        return _Timer(self.histogram(name, LATENCY_BUCKETS_US, help, **labels), 1e6)

    def get(self, name: str, **labels) -> Optional[Any]:
        key = (name, self._canon_labels(labels or {}))
        with self._lock:
            return self._series.get(key)

    def peek(self, name: str, **labels) -> Optional[float]:
        m = self.get(name, **labels)
        if isinstance(m, (Gauge, Counter)):
            return m.get()
        return None

    def collect(self) -> str:
        with self._lock:
            items = list(self._series.items())
            kinds = dict(self._kinds)
            helps = dict(self._helps)
        by_name: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], Any]]] = {}
        for (name, lk), m in items:
            by_name.setdefault(name, []).append((lk, m))
        lines: List[str] = []
        for name in sorted(by_name):
            kind = kinds[name]
            if name in helps:
                lines.append(f"# HELP {name} {_esc(helps[name])}")
            lines.append(f"# TYPE {name} {kind}")
            for lk, m in sorted(by_name[name], key=lambda x: x[0]):
                lstr = _render_labels(lk)
                if kind == "histogram":
                    lines.extend(_histogram_lines(name, lstr, m))
                else:
                    v = m.get()
                    if v is None or not math.isfinite(v):
                        continue
                    lines.append(f"{name}{lstr} {v!r}")
        return "\n".join(lines) + "\n"

    def summary(self) -> dict:
        with self._lock:
            return {
                "series": len(self._series),
                "max_series": self.max_series,
                "dropped_series": self._dropped,
                "metric_families": len(self._kinds),
                "uptime_sec": round(time.time() - self._created, 1),
            }


def _histogram_lines(name: str, lstr: str, h: Histogram) -> List[str]:
    lines: List[str] = []
    cum = 0
    for i, b in enumerate(h.bounds):
        cum += h.counts[i]
        lines.append(f"{name}_bucket{_merge_le(lstr, format(b, 'g'))} {cum}")
    cum += h.counts[-1]
    lines.append(f"{name}_bucket{_merge_le(lstr, '+Inf')} {cum}")
    lines.append(f"{name}_sum{lstr} {h.sum!r}")
    lines.append(f"{name}_count{lstr} {h.count}")
    return lines


REG = Registry()


class MetricsCollector:
    """Snapshot JSON local para o dashboard; não abre portas nem faz I/O externo."""
    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, metric_name: str, value: int = 1) -> None:
        key = str(metric_name).strip() or "unnamed"
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + int(value)

    def _system_usage(self) -> Tuple[Optional[float], Optional[float]]:
        try:
            import psutil  # type: ignore
            return float(psutil.cpu_percent(interval=None)), float(psutil.virtual_memory().percent)
        except Exception:
            return None, None

    def get_snapshot(self) -> dict:
        cpu_percent, ram_percent = self._system_usage()
        vram_used = 0.0
        try:
            from engine.gpu_resource_manager import GPU_GOVERNOR
            vram_used = float(GPU_GOVERNOR.get_current_vram_usage_gb())
        except Exception:
            try:
                from gpu_resource_manager import GPU_GOVERNOR
                vram_used = float(GPU_GOVERNOR.get_current_vram_usage_gb())
            except Exception:
                pass
        with self._lock:
            counters = dict(self._counters)
        return {
            "timestamp": time.time(),
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "vram_used_gb": round(vram_used, 2),
            "counters": counters,
        }


METRICS = MetricsCollector()


def gather_metrics(registry: Registry, components: Dict[str, Callable[[], dict]]) -> str:
    parts = [registry.collect()]
    comp_lines: List[str] = []
    for cname in sorted(components):
        try:
            data = components[cname]() or {}
        except Exception:
            log.exception("[metrics] componente %s falhou na coleta", cname)
            continue
        flat: Dict[str, float] = {}
        _flatten(f"aura_component_{cname}", data, flat)
        for gname in sorted(flat):
            comp_lines.append(f"# TYPE {gname} gauge")
            comp_lines.append(f"{gname} {flat[gname]!r}")
    if comp_lines:
        parts.append("\n".join(comp_lines) + "\n")
    return "".join(parts)


def gather_status(registry: Registry, components: Dict[str, Callable[[], dict]],
                  alerts: List["AlertRule"]) -> dict:
    comps: Dict[str, Any] = {}
    for cname, provider in components.items():
        try:
            comps[cname] = provider() or {}
        except Exception as e:
            comps[cname] = {"error": f"{type(e).__name__}: {e}"}
    now = time.time()
    active: List[dict] = []
    for rule in alerts:
        msg = rule.check({"components": comps, "now": now})
        if msg:
            active.append({
                "name": rule.name, "severity": rule.severity,
                "message": str(msg), "description": rule.description,
            })
    return {
        "ts": _iso(now),
        "components": comps,
        "alerts": active,
        "registry": registry.summary(),
    }


class AlertRule:
    def __init__(self, name: str, check: Callable[[dict], Optional[str]],
                 severity: str = "warn", description: str = ""):
        self.name = str(name)
        self.severity = str(severity)
        self.description = str(description)
        self._check = check

    def check(self, status: dict) -> Optional[str]:
        try:
            return self._check(status)
        except Exception:
            log.exception("[alerts] regra %s falhou (tratada como inativa)", self.name)
            return None


def default_alerts(reg: Registry, *, queue_warn: int = 512,
                   feed_silent_sec: float = 120.0,
                   coverage_min: float = 0.80, coverage_min_n: int = 50,
                   ) -> List[AlertRule]:
    rules: List[AlertRule] = []

    def bus_queue_high(st: dict):
        d = dig(st, "components", "feed_bus", "queue_depth")
        if d is not None and d > queue_warn:
            return f"queue_depth={d} (> {queue_warn}): writer nao acompanha"
        return None

    def bus_drops(st: dict):
        d = dig(st, "components", "feed_bus", "dropped_full")
        if d:
            return f"{d} registros descartados por backpressure acumulado"
        return None

    def feed_silent(st: dict):
        v = reg.peek("aura_heartbeat_feed")
        if v is None:
            return None
        age = float(st.get("now", time.time())) - v
        if age > feed_silent_sec:
            return f"sem frame valido ha {age:.0f}s (> {feed_silent_sec:.0f}s)"
        return None

    def coverage_low(st: dict):
        cov = dig(st, "components", "conformal", "coverage_recente")
        n = dig(st, "components", "conformal", "coverage_n") or 0
        if cov is None or n < coverage_min_n:
            return None
        if cov < coverage_min:
            return (f"cobertura conformal {cov:.3f} < {coverage_min} (n={n})")
        return None

    state = {"last_done": None, "hits": 0}

    def build_stalled(st: dict):
        b = dig(st, "components", "mc_grid", "builder")
        if not isinstance(b, dict) or not b.get("building"):
            state["last_done"], state["hits"] = None, 0
            return None
        done = dig(st, "components", "mc_grid", "cells_done")
        if done is None:
            return None
        if state["last_done"] is not None and done <= state["last_done"]:
            state["hits"] += 1
            if state["hits"] >= 2:
                return f"builder ativo mas cells_done estagnado em {done}"
        else:
            state["hits"] = 0
        state["last_done"] = done
        return None

    rules.append(AlertRule("feed_bus_queue_high", bus_queue_high, "warn",
                           "Fila do FeedBus alta"))
    rules.append(AlertRule("feed_bus_drops", bus_drops, "error",
                           "Backpressure descartou registros"))
    rules.append(AlertRule("feed_silent", feed_silent, "error",
                           "Feed sem frames validos"))
    rules.append(AlertRule("conformal_coverage_low", coverage_low, "warn",
                           "Cobertura conformal baixa"))
    rules.append(AlertRule("mcgrid_build_stalled", build_stalled, "warn",
                           "Build da grade travado"))
    return rules


class MetricsServer:
    def __init__(self, registry: Optional[Registry] = None,
                 host: str = "127.0.0.1", port: int = 9101,
                 watch_interval: float = 30.0):
        self.registry = registry or REG
        self.host = host
        self.port = int(port)
        self.watch_interval = float(watch_interval)
        self._components: Dict[str, Callable[[], dict]] = {}
        self._alerts: List[AlertRule] = []
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._watch_thread: Optional[threading.Thread] = None
        self._started_at: Optional[float] = None
        self._alert_since: Dict[str, float] = {}

    def register_component(self, name: str, provider: Callable[[], dict]) -> None:
        if not callable(provider):
            raise TypeError("provider precisa ser callable que retorna dict")
        with self._lock:
            self._components[str(name)] = provider

    def add_alert(self, rule: AlertRule) -> None:
        with self._lock:
            self._alerts.append(rule)

    def metrics_text(self) -> str:
        with self._lock:
            comps = dict(self._components)
        return gather_metrics(self.registry, comps)

    def status(self) -> dict:
        with self._lock:
            comps = dict(self._components)
            alerts = list(self._alerts)
        st = gather_status(self.registry, comps, alerts)
        if self._started_at:
            st["server_uptime_sec"] = round(time.time() - self._started_at, 1)
        now = time.time()
        active_names = {a["name"] for a in st["alerts"]}
        for a in st["alerts"]:
            first = self._alert_since.get(a["name"])
            if first is None:
                first = now
                self._alert_since[a["name"]] = now
            a["since_sec"] = round(now - first, 1)
        for name in list(self._alert_since):
            if name not in active_names:
                del self._alert_since[name]
        return st

    def start(self) -> "MetricsServer":
        if self._thread is not None and self._thread.is_alive():
            return self
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _send(self, code: int, body: str, ctype: str) -> None:
                data = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                try:
                    if path == "/metrics":
                        self._send(200, outer.metrics_text(),
                                   "text/plain; version=0.0.4; charset=utf-8")
                    elif path == "/healthz":
                        self._send(200, "ok\n", "text/plain; charset=utf-8")
                    elif path == "/statusz":
                        self._send(200, json.dumps(outer.status(), ensure_ascii=False,
                                                   default=str, indent=1),
                                   "application/json; charset=utf-8")
                    elif path == "/alerts":
                        st = outer.status()
                        self._send(200, json.dumps(st["alerts"], ensure_ascii=False, default=str),
                                   "application/json; charset=utf-8")
                    else:
                        self._send(404, "not found\n", "text/plain; charset=utf-8")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    log.exception("[metrics] erro no handler HTTP")

        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = self._httpd.server_address[1]
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="aura-metrics-http", daemon=True)
        self._thread.start()
        self._watch_thread = threading.Thread(target=self._watch_loop,
                                              name="aura-metrics-watch", daemon=True)
        self._watch_thread.start()
        atexit.register(self.stop)
        log.info("[metrics] http://%s:%d/ (metrics|healthz|statusz|alerts)", self.host, self.port)
        return self

    def _watch_loop(self) -> None:
        while True:
            time.sleep(self.watch_interval)
            try:
                self.status()
            except Exception:
                log.exception("[metrics] watch loop falhou")

    def stop(self) -> None:
        if self._httpd is None:
            return
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def _selftest() -> int:
    import urllib.request
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def http_get(url: str):
        with _opener.open(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    reg = Registry()
    c = reg.counter("aura_test_total", help="contador de teste", op="x")
    c.inc()
    c.inc(2)
    g = reg.gauge("aura_test_gauge")
    check("counter inc acumula", c.get() == 3.0)
    g.set(42)
    check("gauge set/get", g.get() == 42.0)

    h = reg.histogram("aura_test_hist_us", buckets=(10, 100, 1000))
    for v in (5, 15, 150, 1500):
        h.observe(v)
    check("histogram buckets corretos", h.counts == [1, 1, 1, 1])
    check("histogram count/sum", h.count == 4 and abs(h.sum - 1670.0) < 1e-9)
    p50 = h.quantile_est(0.5)
    check("quantile_est plausivel", p50 is not None and 10.0 <= p50 <= 100.0, f"p50~{p50:.1f}")

    with reg.timer_us("aura_stage_us", stage="t"):
        time.sleep(0.002)
    hh = reg.get("aura_stage_us", stage="t")
    check("timer registra observacao",
          hh is not None and hh.count == 1 and hh.sum >= 1500,
          f"sum={hh.sum:.0f}us" if hh else "")

    reg4 = Registry(max_series=4)
    for i in range(10):
        m = reg4.counter("aura_card_total", k=str(i))
        m.inc()
    nullm = reg4.counter("aura_card_total", k="excedente")
    nullm.inc(123)
    s4 = reg4.summary()
    check("cardinality cap: series limitadas",
          s4["series"] == 4 and s4["dropped_series"] >= 6,
          f"series={s4['series']} dropped={s4['dropped_series']}")

    text = reg.collect()
    data_lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    check("exposicao: toda linha tem nome + valor", all(len(l.split(" ", 1)) == 2 for l in data_lines))
    check("exposicao: TYPE por familia", "# TYPE aura_test_total counter" in text)
    check("exposicao: valor com label", 'aura_test_total{op="x"} 3.0' in text)
    inf = [l for l in text.splitlines() if l.startswith("aura_test_hist_us_bucket") and "+Inf" in l]
    cnt = [l for l in text.splitlines() if l.startswith("aura_test_hist_us_count")]
    check("histogram: bucket +Inf == count",
          bool(inf) and bool(cnt) and inf[0].split()[-1] == "4" and cnt[0].split()[-1] == "4")
    check("collect deterministico", reg.collect() == text)
    check("peek None se inexistente", reg.peek("aura_nunca_criada") is None)
    check("peek retorna valor", reg.peek("aura_test_gauge") == 42.0)

    flat: Dict[str, float] = {}
    _flatten("aura_c", {"a": 1, "b": {"c": True}, "d": "texto", "e": None, "f": [1, 2]}, flat)
    check("flatten: numerico e bool", flat.get("aura_c_a") == 1.0 and flat.get("aura_c_b_c") == 1.0)
    check("flatten: ignora str/None/list",
          not any(k.startswith(("aura_c_d", "aura_c_e", "aura_c_f")) for k in flat))

    srv = MetricsServer(reg, host="127.0.0.1", port=0, watch_interval=3600)
    srv.register_component("fake_bus", lambda: {"queue_depth": 3, "running": True, "pools": {"global": {"n": 10}}})
    srv.add_alert(AlertRule("sempre_fogo", lambda st: "sempre ativo", severity="info"))
    srv.start()
    base = f"http://127.0.0.1:{srv.port}"
    code, body = http_get(base + "/metrics")
    check("GET /metrics 200", code == 200)
    check("/metrics contem metrica do registry", "aura_test_total" in body)
    check("/metrics contem gauge de componente", "aura_component_fake_bus_queue_depth 3.0" in body)
    code, _ = http_get(base + "/healthz")
    check("GET /healthz 200", code == 200)
    code, body = http_get(base + "/statusz")
    stj = json.loads(body)
    check("/statusz JSON com componente e alerta",
          dig(stj, "components", "fake_bus", "queue_depth") == 3
          and any(a["name"] == "sempre_fogo" for a in stj["alerts"]))
    code, body = http_get(base + "/alerts")
    alerts = json.loads(body)
    check("/alerts com firing since", len(alerts) == 1 and "since_sec" in alerts[0])
    srv.stop()

    reg9 = Registry()
    rules = default_alerts(reg9, feed_silent_sec=60)
    hb = reg9.gauge("aura_heartbeat_feed")
    hb.set(time.time() - 300)
    st = {"components": {}, "now": time.time()}
    msgs = {r.name: r.check(st) for r in rules}
    check("feed_silent dispara com heartbeat velho", msgs.get("feed_silent") is not None)
    hb.set(time.time())
    msgs = {r.name: r.check({"components": {}, "now": time.time()}) for r in rules}
    check("feed_silent limpa com heartbeat fresco", msgs.get("feed_silent") is None)
    st_cov = {"components": {"conformal": {"coverage_recente": 0.70, "coverage_n": 200}}, "now": time.time()}
    msgs = {r.name: r.check(st_cov) for r in rules}
    check("cobertura baixa dispara", msgs.get("conformal_coverage_low") is not None)
    st_cov["components"]["conformal"]["coverage_recente"] = 0.92
    msgs = {r.name: r.check(st_cov) for r in rules}
    check("cobertura ok limpa", msgs.get("conformal_coverage_low") is None)

    rules_b = default_alerts(reg9)
    stalled = [r for r in rules_b if r.name == "mcgrid_build_stalled"][0]

    def mk(done, building):
        return {"components": {"mc_grid": {"cells_done": done, "builder": {"building": building}}},
                "now": time.time()}

    stalled.check(mk(100, True))
    stalled.check(mk(100, True))
    fired = stalled.check(mk(100, True))
    check("build_stalled dispara apos estagnar", fired is not None)
    check("build_stalled limpa ao progredir", stalled.check(mk(150, True)) is None)

    regp = Registry()
    t0 = time.perf_counter()
    N = 20000
    for _ in range(N):
        with regp.timer_us("aura_perf_us", stage="loop"):
            pass
    dt = time.perf_counter() - t0
    hp = regp.get("aura_perf_us", stage="loop")
    check("overhead de instrumentacao aceitavel",
          hp is not None and hp.count == N and dt < 5.0,
          f"{dt:.2f}s / {N} obs ({dt / N * 1e6:.2f} us por obs)")

    print(f"\nobservability selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
