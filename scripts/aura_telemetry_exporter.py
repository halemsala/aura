#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Telemetry Exporter v1.0
Exporta métricas no formato Prometheus, JSON e OTLP para observabilidade.
"""
import os, sys, json, time, psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import threading

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)
METRICS_PATH = LOGDIR / "metrics.json"
PROMETHEUS_PATH = LOGDIR / "metrics.prom"


class MetricsRegistry:
    """Registro de métricas com labels e agregação."""

    def __init__(self):
        self._gauges = {}
        self._counters = {}
        self._histograms = {}
        self._lock = threading.RLock()

    def gauge(self, name: str, value: float, labels: dict = None):
        with self._lock:
            self._gauges[name] = {"value": value, "labels": labels or {}, "timestamp": time.time()}

    def counter(self, name: str, increment: float = 1, labels: dict = None):
        with self._lock:
            key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
            if key not in self._counters:
                self._counters[key] = {"name": name, "value": 0, "labels": labels or {}}
            self._counters[key]["value"] += increment

    def histogram(self, name: str, value: float, buckets: List[float] = None, labels: dict = None):
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {"values": [], "labels": labels or {}, "buckets": buckets or [0.1, 0.5, 1, 2, 5, 10]}
            self._histograms[name]["values"].append(value)

    def to_prometheus(self) -> str:
        lines = []
        with self._lock:
            for name, data in self._gauges.items():
                labels = ",".join(f'{k}="{v}"' for k, v in data["labels"].items())
                label_str = "{" + labels + "}" if labels else ""
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {data['value']}")

            for key, data in self._counters.items():
                labels = ",".join(f'{k}="{v}"' for k, v in data["labels"].items())
                label_str = "{" + labels + "}" if labels else ""
                lines.append(f"# TYPE {data['name']} counter")
                lines.append(f"{data['name']}{label_str} {data['value']}")

            for name, data in self._histograms.items():
                labels = ",".join(f'{k}="{v}"' for k, v in data["labels"].items())
                label_str = "{" + labels + "}" if labels else ""
                values = sorted(data["values"])
                total = len(values)

                for bucket in data["buckets"]:
                    count = sum(1 for v in values if v <= bucket)
                    lines.append(f'{name}_bucket{label_str}le="{bucket}" {count}')
                lines.append(f"{name}_bucket{label_str}le=\"+Inf\" {total}")
                lines.append(f"{name}_sum{label_str} {sum(values)}")
                lines.append(f"{name}_count{label_str} {total}")

        return "\n".join(lines)

    def to_json(self) -> dict:
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "gauges": self._gauges,
                "counters": self._counters,
                "histograms": {k: {**v, "values": v["values"][-100:]} for k, v in self._histograms.items()}
            }

    def export(self):
        with open(PROMETHEUS_PATH, "w", encoding="utf-8") as f:
            f.write(self.to_prometheus())
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)


class SystemCollector:
    """Coletor de métricas do sistema operacional."""

    def __init__(self, registry: MetricsRegistry):
        self.registry = registry

    def collect(self):
        # CPU
        self.registry.gauge("aura_cpu_percent", psutil.cpu_percent(interval=1))
        self.registry.gauge("aura_cpu_count", psutil.cpu_count())

        # Memória
        mem = psutil.virtual_memory()
        self.registry.gauge("aura_memory_total_bytes", mem.total)
        self.registry.gauge("aura_memory_available_bytes", mem.available)
        self.registry.gauge("aura_memory_percent", mem.percent)

        # Disco
        disk = psutil.disk_usage(str(AURA_ROOT))
        self.registry.gauge("aura_disk_total_bytes", disk.total)
        self.registry.gauge("aura_disk_free_bytes", disk.free)
        self.registry.gauge("aura_disk_percent", disk.percent)

        # Rede
        net = psutil.net_io_counters()
        self.registry.counter("aura_network_bytes_sent", net.bytes_sent)
        self.registry.counter("aura_network_bytes_recv", net.bytes_recv)

        # Processos AURA
        aura_procs = [p for p in psutil.process_iter(["pid", "name", "memory_info"]) 
                      if "aura" in p.info["name"].lower() or "python" in p.info["name"].lower()]
        self.registry.gauge("aura_process_count", len(aura_procs))
        total_mem = sum(p.info["memory_info"].rss for p in aura_procs if p.info.get("memory_info"))
        self.registry.gauge("aura_process_memory_bytes", total_mem)


def collect_service_metrics(registry: MetricsRegistry):
    """Coleta métricas dos serviços AURA."""
    import requests

    endpoints = {
        "bridge": "http://127.0.0.1:8080/health",
        "engine": "http://127.0.0.1:8765/api/health",
        "voice": "http://127.0.0.1:8099/api/voice/health",
    }

    for service, url in endpoints.items():
        start = time.time()
        try:
            r = requests.get(url, timeout=5)
            latency = (time.time() - start) * 1000
            registry.gauge("aura_service_up", 1 if r.status_code == 200 else 0, {"service": service})
            registry.histogram("aura_service_latency_ms", latency, labels={"service": service})
        except Exception:
            registry.gauge("aura_service_up", 0, {"service": service})


def main():
    registry = MetricsRegistry()
    collector = SystemCollector(registry)

    print("=" * 60)
    print("AURA Telemetry Exporter v1.0")
    print("Coletando métricas...")
    print("=" * 60)

    collector.collect()
    collect_service_metrics(registry)
    registry.export()

    print(f"Métricas Prometheus: {PROMETHEUS_PATH}")
    print(f"Métricas JSON: {METRICS_PATH}")
    print("\nPreview (Prometheus):")
    print(registry.to_prometheus()[:2000])


if __name__ == "__main__":
    main()
