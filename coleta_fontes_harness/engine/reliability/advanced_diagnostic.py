# advanced_diagnostic.py — Diagnóstico ponta a ponta (CPU/RAM/Disco/Rede/APIs locais/GPU)
from __future__ import annotations

import json
import logging
import platform
import socket
import statistics
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Portas típicas do ecossistema AURA / Ollama / LLM cache
DEFAULT_AI_PORTS = [8000, 8010, 5000, 11434, 8080]
DEFAULT_REDIS_PORT = 6379


class AdvancedSystemDiagnosticPro:
    """
    Diagnóstico e monitoramento contínuo para AURA QUANT-X / IA local.
    Score 0–100 + status STABLE | DEGRADED | CRITICAL.
    """

    def __init__(
        self,
        ai_ports: Optional[List[int]] = None,
        redis_port: int = DEFAULT_REDIS_PORT,
        disk_path: str = "/",
    ):
        self.os_info = platform.system()
        self.node_name = platform.node()
        self.ai_ports = ai_ports or list(DEFAULT_AI_PORTS)
        self.redis_port = redis_port
        self.disk_path = disk_path if Path(disk_path).exists() else str(Path.cwd())
        self.health_history: List[Dict[str, Any]] = []
        self._is_monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ CPU
    def _check_cpu(self) -> Dict[str, Any]:
        try:
            usage_percent = psutil.cpu_percent(interval=0.5)
            core_usages = psutil.cpu_percent(interval=None, percpu=True)
            freq = psutil.cpu_freq()
            load = None
            try:
                load = list(psutil.getloadavg())
            except (AttributeError, OSError):
                pass

            status = "HEALTHY"
            if usage_percent > 90.0:
                status = "CRITICAL"
            elif usage_percent > 75.0:
                status = "WARNING"

            return {
                "status": status,
                "usage_percent": usage_percent,
                "core_usages": core_usages,
                "freq_current_mhz": round(freq.current, 1) if freq else None,
                "cores_count": psutil.cpu_count(logical=True),
                "load_avg": load,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # ------------------------------------------------------------------ RAM
    def _check_memory(self) -> Dict[str, Any]:
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            status = "HEALTHY"
            if mem.percent > 92.0:
                status = "CRITICAL"
            elif mem.percent > 80.0:
                status = "WARNING"
            return {
                "status": status,
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent_used": mem.percent,
                "swap_percent": swap.percent,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # ------------------------------------------------------------------ Disk
    def _check_disk_io(self) -> Dict[str, Any]:
        try:
            usage = psutil.disk_usage(self.disk_path)
            write_time = read_time = None
            try:
                payload = b"A" * (2 * 1024 * 1024)  # 2MB (mais leve que 10MB)
                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    t0 = time.time()
                    tmp.write(payload)
                    tmp.flush()
                    write_time = time.time() - t0
                    tmp.seek(0)
                    t1 = time.time()
                    _ = tmp.read()
                    read_time = time.time() - t1
            except OSError as e:
                return {
                    "status": "WARNING",
                    "error_io": str(e),
                    "disk_usage_percent": usage.percent,
                    "free_gb": round(usage.free / (1024**3), 2),
                }

            status = "HEALTHY"
            if usage.percent > 95 or (write_time is not None and write_time > 2.0):
                status = "WARNING"
            if usage.percent > 98:
                status = "CRITICAL"

            return {
                "status": status,
                "write_2mb_sec": round(write_time, 4) if write_time is not None else None,
                "read_2mb_sec": round(read_time, 4) if read_time is not None else None,
                "disk_usage_percent": usage.percent,
                "free_gb": round(usage.free / (1024**3), 2),
                "path": self.disk_path,
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # ------------------------------------------------------------------ Network
    def _check_network_connectivity(
        self, endpoints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        endpoints = endpoints or ["1.1.1.1", "8.8.8.8"]
        results: Dict[str, Any] = {}
        total_latency: List[float] = []

        for host in endpoints:
            try:
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.5)
                result = sock.connect_ex((host, 53))
                latency = (time.time() - start) * 1000
                sock.close()
                if result == 0:
                    results[host] = {"status": "OK", "latency_ms": round(latency, 2)}
                    total_latency.append(latency)
                else:
                    results[host] = {"status": "FAILED", "latency_ms": None}
            except Exception as e:
                results[host] = {"status": "ERROR", "error": str(e)}

        if not total_latency:
            # offline pode ser ok para setup 100% local
            return {
                "status": "WARNING",
                "avg_latency_ms": None,
                "endpoints": results,
                "note": "sem conectividade externa (ok se só localhost)",
            }

        avg_lat = statistics.mean(total_latency)
        status = "HEALTHY"
        if avg_lat > 250:
            status = "WARNING"
        return {
            "status": status,
            "avg_latency_ms": round(avg_lat, 2),
            "endpoints": results,
        }

    # ------------------------------------------------------------------ Local ports
    def _probe_tcp(self, host: str, port: int, timeout: float = 0.8) -> Dict[str, Any]:
        try:
            t0 = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            code = sock.connect_ex((host, port))
            lat = (time.time() - t0) * 1000
            sock.close()
            if code == 0:
                return {"status": "HEALTHY", "latency_ms": round(lat, 2), "open": True}
            return {"status": "OFFLINE", "open": False}
        except Exception as e:
            return {"status": "ERROR", "error": str(e), "open": False}

    def _check_local_services(self) -> Dict[str, Any]:
        ports: Dict[str, Any] = {}
        any_ai = False
        for p in self.ai_ports:
            info = self._probe_tcp("127.0.0.1", p)
            ports[str(p)] = info
            if info.get("open"):
                any_ai = True
        redis = self._probe_tcp("127.0.0.1", self.redis_port)

        # HTTP opcional nas portas abertas (não falha o score se TCP ok)
        http_ok = []
        try:
            import requests
            for p in self.ai_ports:
                if ports[str(p)].get("open"):
                    try:
                        r = requests.get(f"http://127.0.0.1:{p}/health", timeout=1.0)
                        http_ok.append({"port": p, "code": r.status_code})
                    except Exception:
                        try:
                            r = requests.get(f"http://127.0.0.1:{p}/", timeout=1.0)
                            http_ok.append({"port": p, "code": r.status_code})
                        except Exception:
                            pass
        except ImportError:
            pass

        status = "HEALTHY" if any_ai else "WARNING"
        if not any_ai and redis.get("status") == "OFFLINE":
            status = "WARNING"  # sistema pode estar parado de propósito

        return {
            "status": status,
            "any_local_ai_port_open": any_ai,
            "ports": ports,
            "redis": redis,
            "http_probes": http_ok,
        }

    # ------------------------------------------------------------------ GPU
    def _check_gpu(self) -> Dict[str, Any]:
        # torch
        try:
            import torch
            if torch.cuda.is_available():
                idx = 0
                props = torch.cuda.get_device_properties(idx)
                used = torch.cuda.memory_allocated(idx) / (1024**2)
                total = props.total_memory / (1024**2)
                ratio = used / total if total else 0
                status = "HEALTHY"
                if ratio > 0.92:
                    status = "CRITICAL"
                elif ratio > 0.85:
                    status = "WARNING"
                return {
                    "status": status,
                    "backend": "torch",
                    "name": props.name,
                    "vram_used_mb": round(used, 1),
                    "vram_total_mb": round(total, 1),
                    "vram_ratio": round(ratio, 3),
                }
        except Exception:
            pass

        # pynvml
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            ratio = mem.used / mem.total
            status = "HEALTHY"
            if ratio > 0.92:
                status = "CRITICAL"
            elif ratio > 0.85:
                status = "WARNING"
            return {
                "status": status,
                "backend": "pynvml",
                "name": name,
                "vram_used_mb": round(mem.used / (1024**2), 1),
                "vram_total_mb": round(mem.total / (1024**2), 1),
                "vram_ratio": round(ratio, 3),
            }
        except Exception:
            pass

        return {"status": "HEALTHY", "backend": None, "message": "GPU não detectada (CPU only)"}

    # ------------------------------------------------------------------ Score
    def run_full_diagnostic(self, check_network: bool = True) -> Dict[str, Any]:
        logging.info("Diagnóstico completo AURA...")
        cpu = self._check_cpu()
        mem = self._check_memory()
        disk = self._check_disk_io()
        gpu = self._check_gpu()
        services = self._check_local_services()
        net = self._check_network_connectivity() if check_network else {"status": "SKIPPED"}

        penalties = {"CRITICAL": 25, "ERROR": 15, "OFFLINE": 8, "WARNING": 8}
        score = 100
        for data in (cpu, mem, disk, gpu, services, net):
            st = data.get("status")
            if st in penalties:
                # OFFLINE de AI local pesa menos (pode estar parado)
                if data is services and st == "WARNING":
                    score -= 5
                else:
                    score -= penalties.get(st, 0)
        score = max(0, min(100, score))

        if score >= 80:
            overall = "STABLE"
        elif score >= 50:
            overall = "DEGRADED"
        else:
            overall = "CRITICAL"

        report = {
            "timestamp": time.time(),
            "os": self.os_info,
            "node": self.node_name,
            "health_score": score,
            "overall_status": overall,
            "diagnostics": {
                "cpu": cpu,
                "memory": mem,
                "disk": disk,
                "gpu": gpu,
                "local_services": services,
                "network": net,
            },
        }
        self.health_history.append(report)
        if len(self.health_history) > 100:
            self.health_history.pop(0)
        return report

    def export_last_json(self, path: str = "diagnostic_report.json") -> str:
        if not self.health_history:
            self.run_full_diagnostic()
        Path(path).write_text(
            json.dumps(self.health_history[-1], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _monitor_loop(self, interval_seconds: int):
        while self._is_monitoring:
            report = self.run_full_diagnostic()
            if report["overall_status"] != "STABLE":
                logging.warning(
                    "Alerta sistema: %s score=%s",
                    report["overall_status"],
                    report["health_score"],
                )
            time.sleep(interval_seconds)

    def start_background_monitor(self, interval_seconds: int = 60):
        if self._is_monitoring:
            return
        self._is_monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(interval_seconds,), daemon=True
        )
        self._monitor_thread.start()

    def stop_background_monitor(self):
        self._is_monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None


# Integração opcional com health_score interno do reliability
def push_to_reliability_health(report: Dict[str, Any]) -> None:
    try:
        from .health_score import health_score
        diag = report.get("diagnostics", {})
        mem = diag.get("memory", {})
        cpu = diag.get("cpu", {})
        health_score.record(
            latency_ms=float((diag.get("network") or {}).get("avg_latency_ms") or 0),
            error=report.get("overall_status") == "CRITICAL",
            vram_ratio=float((diag.get("gpu") or {}).get("vram_ratio") or 0),
            confidence=report.get("health_score", 100) / 100.0,
            cache_hit=False,
        )
    except Exception:
        pass


if __name__ == "__main__":
    tool = AdvancedSystemDiagnosticPro()
    r = tool.run_full_diagnostic()
    print(json.dumps({
        "overall_status": r["overall_status"],
        "health_score": r["health_score"],
        "cpu": r["diagnostics"]["cpu"].get("usage_percent"),
        "ram": r["diagnostics"]["memory"].get("percent_used"),
        "gpu": r["diagnostics"]["gpu"].get("message") or r["diagnostics"]["gpu"].get("name"),
        "services": r["diagnostics"]["local_services"].get("any_local_ai_port_open"),
    }, indent=2))
    tool.export_last_json("/tmp/diagnostic_report.json")
    print("saved /tmp/diagnostic_report.json")
