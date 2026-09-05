#!/usr/bin/env python3
"""
AURA QUANT-X — Omnipotent Health Profiler (SRE L1 + Predictive Observability)
Physiological system diagnostics: metrics, memory topology, behavioral drift,
VRAM fragmentation, TTF prediction, phase-space chaos indicators.
No log-string grepping. Async-safe. Graceful fallbacks when optional deps missing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import statistics
import time
import tracemalloc
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

# Optional deps — never hard-fail
try:
    import zmq  # type: ignore
    ZMQ_OK = True
except Exception:
    zmq = None  # type: ignore
    ZMQ_OK = False

try:
    import pynvml  # type: ignore
    NVML_OK = True
except Exception:
    pynvml = None  # type: ignore
    NVML_OK = False

try:
    import urllib.request
except Exception:
    urllib = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants / healthy baselines
# ---------------------------------------------------------------------------
HEALTH_ENDPOINTS = (
    ("bridge", "http://127.0.0.1:8080/health"),
    ("engine", "http://127.0.0.1:8765/health"),
    ("voice", "http://127.0.0.1:8099/api/voice/health"),
)
ZMQ_PORT = 5555
ZMQ_HWM_ALERT_STATIC = 50  # only used if EMA not warm yet
EMA_WINDOW = 500
EMA_SIGMA = 3.0
CLOCK_SKEW_CRITICAL_MS = 500.0
MEM_BLOCK_ALERT_MB = 100.0
SCHEMA_HASH_HEALTHY = os.getenv("AURA_SCHEMA_HASH_HEALTHY", "").strip()
DEFAULT_DB_CANDIDATES = (
    Path("logs/telemetry.db"),
    Path("bridge/logs/telemetry.db"),
    Path("engine/logs/telemetry.db"),
    Path("data/logs_telemetria.sqlite"),
    Path("logs_telemetria.db"),
)


@dataclass
class DiagnosticReport:
    memory_frag: Dict[str, Any]
    clock_skew_ms: Dict[str, Any]
    zmq_depth: Dict[str, Any]
    schema_drift: Dict[str, Any]
    vram_frag: Dict[str, Any]
    ttf: Dict[str, Any]
    phase_space: Dict[str, Any]
    distributed_trace: Dict[str, Any]
    health_score: float
    alerts: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OmnipotentHealthProfiler:
    """
    Systemic physiology agent.
    - CPU RAM fragmentation via tracemalloc
    - Distributed clock skew across Bridge/Engine/Voice
    - ZMQ queue depth with EMA dynamic baseline (behavioral drift)
    - SQLite schema drift (MD5 of PRAGMA table_info)
    - VRAM pool fragmentation via pynvml (optional)
    - Time-to-failure predictor from queue derivative
    - Phase-space Lyapunov-ish chaos indicator
    - Distributed tracing span aggregation (in-memory)
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        zmq_endpoint: str = f"tcp://127.0.0.1:{ZMQ_PORT}",
        trace_frames: int = 25,
    ) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start(trace_frames)
        self.zmq_endpoint = zmq_endpoint
        self.db_path = db_path or self._discover_db()
        self._zmq_depth_hist: Deque[float] = deque(maxlen=EMA_WINDOW)
        self._skew_hist: Deque[float] = deque(maxlen=EMA_WINDOW)
        self._vram_free_hist: Deque[float] = deque(maxlen=EMA_WINDOW)
        self._spans: Dict[str, List[Dict[str, Any]]] = {}
        self._nvml_ready = False
        if NVML_OK:
            try:
                pynvml.nvmlInit()
                self._nvml_ready = True
            except Exception:
                self._nvml_ready = False

    # ------------------------------------------------------------------
    # 1) Memory fragmentation (tracemalloc)
    # ------------------------------------------------------------------
    def check_memory_fragmentation(self) -> Dict[str, Any]:
        snap = tracemalloc.take_snapshot()
        stats = snap.statistics("traceback")
        top: List[Dict[str, Any]] = []
        alert = False
        for st in stats[:10]:
            size_mb = st.size / (1024 * 1024)
            frames = []
            for fr in st.traceback:
                frames.append(f"{fr.filename}:{fr.lineno}")
            entry = {
                "size_mb": round(size_mb, 3),
                "count": st.count,
                "traceback": frames[:8],
                "origin": frames[0] if frames else "unknown",
            }
            if size_mb > MEM_BLOCK_ALERT_MB:
                alert = True
                entry["alert"] = f"block>{MEM_BLOCK_ALERT_MB}MB"
            top.append(entry)
        current, peak = tracemalloc.get_traced_memory()
        return {
            "top_blocks": top,
            "traced_current_mb": round(current / (1024 * 1024), 3),
            "traced_peak_mb": round(peak / (1024 * 1024), 3),
            "alert": alert,
            "severity": "critical" if alert else "ok",
        }

    # ------------------------------------------------------------------
    # 2) Clock skew detector (asyncio concurrent health pings)
    # ------------------------------------------------------------------
    async def _fetch_health_ts(self, name: str, url: str) -> Dict[str, Any]:
        t0 = time.time()

        def _sync_get() -> Tuple[int, float, Optional[str]]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AURA-SRE/1.0"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    body = resp.read(256).decode("utf-8", errors="replace")
                    # Prefer server Date header if present
                    date_hdr = resp.headers.get("Date")
                    server_ts = None
                    if date_hdr:
                        try:
                            from email.utils import parsedate_to_datetime

                            server_ts = parsedate_to_datetime(date_hdr).timestamp()
                        except Exception:
                            server_ts = None
                    return resp.status, server_ts if server_ts is not None else time.time(), body[:80]
            except Exception as e:
                return 0, time.time(), str(e)

        status, ts, meta = await asyncio.to_thread(_sync_get)
        latency_ms = (time.time() - t0) * 1000.0
        return {
            "name": name,
            "url": url,
            "status": status,
            "ts": ts,
            "latency_ms": round(latency_ms, 2),
            "ok": status == 200,
            "meta": meta,
        }

    async def check_clock_skew(self) -> Dict[str, Any]:
        results = await asyncio.gather(
            *[self._fetch_health_ts(n, u) for n, u in HEALTH_ENDPOINTS]
        )
        online = [r for r in results if r["ok"]]
        skew_ms = 0.0
        critical = False
        pairs: List[Dict[str, Any]] = []
        if len(online) >= 2:
            timestamps = [r["ts"] for r in online]
            skew_ms = (max(timestamps) - min(timestamps)) * 1000.0
            self._skew_hist.append(skew_ms)
            critical = skew_ms > CLOCK_SKEW_CRITICAL_MS
            for i in range(len(online)):
                for j in range(i + 1, len(online)):
                    d = abs(online[i]["ts"] - online[j]["ts"]) * 1000.0
                    pairs.append(
                        {
                            "a": online[i]["name"],
                            "b": online[j]["name"],
                            "delta_ms": round(d, 2),
                        }
                    )
        return {
            "services": results,
            "online_count": len(online),
            "max_skew_ms": round(skew_ms, 2),
            "pairs": pairs,
            "critical": critical,
            "alert": "Distributed Clock Drift" if critical else None,
            "severity": "critical" if critical else ("degraded" if len(online) < 3 else "ok"),
        }

    # ------------------------------------------------------------------
    # 3) ZMQ queue depth + EMA behavioral drift
    # ------------------------------------------------------------------
    def _probe_zmq_depth_sync(self) -> Dict[str, Any]:
        if not ZMQ_OK:
            return {
                "available": False,
                "depth": None,
                "alert": None,
                "note": "pyzmq not installed",
                "severity": "unknown",
            }
        depth = 0
        try:
            ctx = zmq.Context.instance()
            sock = ctx.socket(zmq.PULL)
            sock.setsockopt(zmq.RCVHWM, 1000)
            sock.setsockopt(zmq.LINGER, 0)
            sock.setsockopt(zmq.RCVTIMEO, 50)
            # Probe: connect and drain non-blocking count estimate
            try:
                sock.connect(self.zmq_endpoint)
            except Exception:
                sock.bind(self.zmq_endpoint.replace("5555", "5559"))  # probe alt
            # High-water / events approximation: try non-blocking recv count
            for _ in range(200):
                try:
                    sock.recv(zmq.NOBLOCK)
                    depth += 1
                except zmq.Again:
                    break
                except Exception:
                    break
            sock.close(linger=0)
        except Exception as e:
            return {
                "available": False,
                "depth": None,
                "error": str(e),
                "severity": "unknown",
            }
        return {"available": True, "depth": depth, "severity": "ok"}

    def check_zmq_depth(self) -> Dict[str, Any]:
        raw = self._probe_zmq_depth_sync()
        depth = float(raw.get("depth") or 0)
        if raw.get("available"):
            self._zmq_depth_hist.append(depth)

        # Dynamic baseline (EMA / rolling mean + std)
        hist = list(self._zmq_depth_hist)
        alert = None
        severity = "ok"
        baseline = None
        if len(hist) >= 30:
            mean = statistics.fmean(hist)
            std = statistics.pstdev(hist) if len(hist) > 1 else 0.0
            threshold = mean + EMA_SIGMA * std
            baseline = {"mean": round(mean, 2), "std": round(std, 2), "threshold": round(threshold, 2), "n": len(hist)}
            if depth > threshold and depth > 5:
                alert = "Throughput Bottleneck Detected (behavioral drift)"
                severity = "critical"
        else:
            # cold start: static safety net
            if depth > ZMQ_HWM_ALERT_STATIC:
                alert = "Throughput Bottleneck Detected"
                severity = "critical"
            baseline = {"mean": None, "std": None, "threshold": ZMQ_HWM_ALERT_STATIC, "n": len(hist), "mode": "static_cold"}

        out = dict(raw)
        out.update(
            {
                "depth": depth if raw.get("available") else raw.get("depth"),
                "baseline": baseline,
                "alert": alert,
                "severity": severity if alert else raw.get("severity", "ok"),
            }
        )
        return out

    # ------------------------------------------------------------------
    # 4) Schema drift (SQLite PRAGMA hash)
    # ------------------------------------------------------------------
    def _discover_db(self) -> Optional[Path]:
        for p in DEFAULT_DB_CANDIDATES:
            if p.exists():
                return p
        # search shallow
        for root in (Path("."), Path("logs"), Path("bridge"), Path("engine")):
            if not root.exists():
                continue
            for p in root.rglob("*.db"):
                return p
            for p in root.rglob("*.sqlite"):
                return p
        return None

    def check_schema_drift(self) -> Dict[str, Any]:
        db = self.db_path
        if db is None or not Path(db).exists():
            return {
                "available": False,
                "path": str(db) if db else None,
                "hash": None,
                "expected": SCHEMA_HASH_HEALTHY,
                "drift": False,
                "alert": None,
                "note": "telemetry db not found — skip",
                "severity": "unknown",
            }

        def _read_schema() -> str:
            con = sqlite3.connect(str(db), timeout=1.0)
            try:
                cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                target = None
                for cand in ("logs_telemetria", "telemetry", "logs", "events"):
                    if cand in tables:
                        target = cand
                        break
                if target is None and tables:
                    target = tables[0]
                if target is None:
                    return "EMPTY"
                cols = con.execute(f"PRAGMA table_info({target})").fetchall()
                # col tuple: cid, name, type, notnull, dflt, pk
                sig = "|".join(f"{c[1]}:{c[2]}:{c[3]}:{c[5]}" for c in cols)
                return hashlib.md5(sig.encode("utf-8")).hexdigest()
            finally:
                con.close()

        try:
            h = _read_schema()
        except Exception as e:
            return {
                "available": False,
                "path": str(db),
                "error": str(e),
                "drift": False,
                "severity": "unknown",
            }
        env_hash = os.getenv("AURA_SCHEMA_HASH_HEALTHY", "").strip() or SCHEMA_HASH_HEALTHY
        if env_hash:
            drift = h != env_hash
            expected = env_hash
            baseline_mode = "pinned"
        else:
            expected = h
            drift = False
            baseline_mode = "observed"
        return {
            "available": True,
            "path": str(db),
            "table_hash": h,
            "expected": expected,
            "baseline_mode": baseline_mode,
            "drift": drift,
            "alert": "Database Schema Drift" if drift else None,
            "severity": "critical" if drift else "ok",
        }

    # ------------------------------------------------------------------
    # MAX 3: VRAM fragmentation (pynvml)
    # ------------------------------------------------------------------
    def check_vram_fragmentation(self) -> Dict[str, Any]:
        if not self._nvml_ready:
            return {
                "available": False,
                "note": "pynvml unavailable or no GPU",
                "severity": "unknown",
                "alert": None,
            }
        try:
            count = pynvml.nvmlDeviceGetCount()
            gpus = []
            critical = False
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                used_mb = mem.used / (1024 * 1024)
                free_mb = mem.free / (1024 * 1024)
                total_mb = mem.total / (1024 * 1024)
                self._vram_free_hist.append(free_mb)
                # Heuristic fragmentation risk: high utilization + free fragmented
                util = used_mb / total_mb if total_mb else 0
                # Without CUDA allocator stats, approximate risk when free is small
                # relative to typical large tensor (~512MB)
                risk = free_mb < 512 and util > 0.7
                if risk:
                    critical = True
                gpus.append(
                    {
                        "index": i,
                        "used_mb": round(used_mb, 1),
                        "free_mb": round(free_mb, 1),
                        "total_mb": round(total_mb, 1),
                        "util": round(util, 3),
                        "frag_risk": risk,
                    }
                )
            alert = None
            if critical:
                alert = "Fragmentação de VRAM Crítica"
                # best-effort selective cache clear
                try:
                    import torch  # type: ignore

                    torch.cuda.empty_cache()
                    action = "torch.cuda.empty_cache()"
                except Exception:
                    action = None
            else:
                action = None
            return {
                "available": True,
                "gpus": gpus,
                "alert": alert,
                "action": action,
                "severity": "critical" if critical else "ok",
            }
        except Exception as e:
            return {"available": False, "error": str(e), "severity": "unknown"}

    # ------------------------------------------------------------------
    # MAX 4: Time-to-failure predictor
    # ------------------------------------------------------------------
    def predict_time_to_failure(self) -> Dict[str, Any]:
        hist = list(self._zmq_depth_hist)
        if len(hist) < 5:
            return {
                "ready": False,
                "ttf_s": None,
                "rate_per_s": None,
                "note": "insufficient history",
                "severity": "unknown",
            }
        # derivative over last ~2s assuming ~1 sample per diagnostic tick;
        # use last 5 samples as window
        window = hist[-5:]
        # assume inter-sample ~1s if called periodically; scale if denser
        dt = 1.0
        rate = (window[-1] - window[0]) / max(dt * (len(window) - 1), 1e-6)
        # avg processing capacity heuristic: 20 msg/s baseline
        capacity = 20.0
        headroom = max(0.0, capacity - rate)
        # collapse when depth reaches hard limit 500
        hard_limit = 500.0
        current = window[-1]
        if rate <= 0:
            ttf = None
            severity = "ok"
            alert = None
        else:
            remaining = max(0.0, hard_limit - current)
            ttf = remaining / rate if rate > 0 else None
            if ttf is not None and ttf < 30:
                severity = "critical"
                alert = f"Estimativa de colapso do barramento em {ttf:.1f}s"
            elif ttf is not None and ttf < 120:
                severity = "warning"
                alert = f"TTF ~{ttf:.0f}s"
            else:
                severity = "ok"
                alert = None
        return {
            "ready": True,
            "depth": current,
            "rate_per_s": round(rate, 3),
            "ttf_s": round(ttf, 2) if ttf is not None else None,
            "alert": alert,
            "severity": severity,
            "backpressure_hint": "drop P10 learning msgs" if severity == "critical" else None,
        }

    # ------------------------------------------------------------------
    # Phase-space / Lyapunov-ish indicator (lightweight)
    # ------------------------------------------------------------------
    def check_phase_space(self) -> Dict[str, Any]:
        z = list(self._zmq_depth_hist)
        s = list(self._skew_hist)
        v = list(self._vram_free_hist)
        n = min(len(z), max(len(s), 1), max(len(v), 1), 100)
        if n < 10:
            return {"ready": False, "lyapunov_est": None, "severity": "unknown"}
        # Normalize series and estimate divergence of successive differences
        def _norm(series: List[float]) -> List[float]:
            if not series:
                return []
            m = statistics.fmean(series)
            sd = statistics.pstdev(series) or 1.0
            return [(x - m) / sd for x in series]

        zn = _norm(z[-n:])
        sn = _norm(s[-n:] if s else [0.0] * n)
        vn = _norm(v[-n:] if v else [0.0] * n)
        # trajectory distance growth
        divergences = []
        for i in range(1, min(len(zn), len(sn), len(vn))):
            d0 = math.sqrt(zn[i - 1] ** 2 + sn[i - 1] ** 2 + vn[i - 1] ** 2) + 1e-9
            d1 = math.sqrt(zn[i] ** 2 + sn[i] ** 2 + vn[i] ** 2) + 1e-9
            divergences.append(math.log(d1 / d0))
        lyap = statistics.fmean(divergences) if divergences else 0.0
        thermal_death = lyap > 0.15 and (z[-1] if z else 0) > 100
        return {
            "ready": True,
            "lyapunov_est": round(lyap, 5),
            "thermal_death_imminent": thermal_death,
            "alert": "Morte Térmica Iminente" if thermal_death else None,
            "severity": "critical" if thermal_death else ("warning" if lyap > 0.08 else "ok"),
        }

    # ------------------------------------------------------------------
    # Distributed tracing (in-process span registry)
    # ------------------------------------------------------------------
    def new_trace_id(self) -> str:
        return str(uuid.uuid4())

    def record_span(
        self,
        trace_id: str,
        service: str,
        op: str,
        t_in: float,
        t_out: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        span = {
            "service": service,
            "op": op,
            "t_in": t_in,
            "t_out": t_out,
            "duration_ms": round((t_out - t_in) * 1000.0, 3),
            "extra": extra or {},
        }
        self._spans.setdefault(trace_id, []).append(span)

    def analyze_traces(self, limit: int = 20) -> Dict[str, Any]:
        heat: Dict[str, List[float]] = {}
        for tid, spans in list(self._spans.items())[-limit:]:
            for sp in spans:
                key = f"{sp['service']}:{sp['op']}"
                heat.setdefault(key, []).append(sp["duration_ms"])
        summary = []
        bottleneck = None
        max_mean = 0.0
        for k, vals in heat.items():
            mean = statistics.fmean(vals)
            summary.append({"span": k, "mean_ms": round(mean, 2), "n": len(vals), "max_ms": round(max(vals), 2)})
            if mean > max_mean:
                max_mean = mean
                bottleneck = k
        summary.sort(key=lambda x: -x["mean_ms"])
        return {
            "traces_kept": len(self._spans),
            "heatmap_top": summary[:10],
            "bottleneck": bottleneck,
            "alert": f"latency hotspot: {bottleneck}" if bottleneck and max_mean > 200 else None,
            "severity": "warning" if bottleneck and max_mean > 200 else "ok",
        }

    # ------------------------------------------------------------------
    # Full diagnostic
    # ------------------------------------------------------------------
    async def run_full_diagnostic(self) -> Dict[str, Any]:
        mem = await asyncio.to_thread(self.check_memory_fragmentation)
        skew = await self.check_clock_skew()
        zmq_d = await asyncio.to_thread(self.check_zmq_depth)
        schema = await asyncio.to_thread(self.check_schema_drift)
        vram = await asyncio.to_thread(self.check_vram_fragmentation)
        ttf = await asyncio.to_thread(self.predict_time_to_failure)
        phase = await asyncio.to_thread(self.check_phase_space)
        traces = await asyncio.to_thread(self.analyze_traces)

        alerts: List[str] = []
        for block in (mem, skew, zmq_d, schema, vram, ttf, phase, traces):
            a = block.get("alert")
            if a:
                alerts.append(a)

        # Health score 0-100
        score = 100.0
        penalties = 0.0
        if mem.get("alert"):
            penalties += 20
        if skew.get("critical"):
            penalties += 25
        elif skew.get("online_count", 0) < 3:
            penalties += 10
        if zmq_d.get("severity") == "critical":
            penalties += 20
        if schema.get("drift"):
            penalties += 15
        if vram.get("severity") == "critical":
            penalties += 20
        if ttf.get("severity") == "critical":
            penalties += 15
        if phase.get("thermal_death_imminent"):
            penalties += 30
        score = max(0.0, min(100.0, score - penalties))

        report = DiagnosticReport(
            memory_frag=mem,
            clock_skew_ms=skew,
            zmq_depth=zmq_d,
            schema_drift=schema,
            vram_frag=vram,
            ttf=ttf,
            phase_space=phase,
            distributed_trace=traces,
            health_score=round(score, 1),
            alerts=alerts,
        )
        return report.to_dict()


# ---------------------------------------------------------------------------
# CLI / orchestration
# ---------------------------------------------------------------------------
_profiler_singleton: Optional[OmnipotentHealthProfiler] = None


def get_profiler() -> OmnipotentHealthProfiler:
    global _profiler_singleton
    if _profiler_singleton is None:
        _profiler_singleton = OmnipotentHealthProfiler()
    return _profiler_singleton


async def main_async() -> int:
    prof = get_profiler()
    result = await prof.run_full_diagnostic()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    score = result.get("health_score", 0)
    print(f"\n=== HEALTH SCORE: {score}/100 ===")
    if result.get("alerts"):
        print("ALERTS:")
        for a in result["alerts"]:
            print(f"  - {a}")
    return 0 if score >= 70 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
