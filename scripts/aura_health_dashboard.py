#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Health Dashboard v1.0
Endpoint consolidado de health com métricas, status e diagnóstico.
Pode ser exposto como endpoint FastAPI ou executado standalone.
"""
import os, sys, json, time, psutil, requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))


class HealthDashboard:
    """Dashboard de health consolidado do AURA."""

    SERVICES = {
        "Bridge": {"url": "http://127.0.0.1:8080/health", "critical": True},
        "Engine": {"url": "http://127.0.0.1:8765/api/health", "critical": True},
        "Voice": {"url": "http://127.0.0.1:8099/api/voice/health", "critical": False},
        "Ollama": {"url": "http://127.0.0.1:11434/api/tags", "critical": False},
    }

    def __init__(self):
        self._start_time = time.time()

    def check_service(self, name: str, config: dict) -> dict:
        start = time.time()
        try:
            r = requests.get(config["url"], timeout=5)
            latency = (time.time() - start) * 1000
            return {
                "name": name,
                "status": "UP" if r.status_code == 200 else "DEGRADED",
                "healthy": r.status_code == 200,
                "critical": config["critical"],
                "latency_ms": round(latency, 2),
                "status_code": r.status_code,
            }
        except requests.exceptions.ConnectionError:
            return {"name": name, "status": "DOWN", "healthy": False, "critical": config["critical"], "error": "connection_refused"}
        except requests.exceptions.Timeout:
            return {"name": name, "status": "TIMEOUT", "healthy": False, "critical": config["critical"], "error": "timeout"}
        except Exception as e:
            return {"name": name, "status": "ERROR", "healthy": False, "critical": config["critical"], "error": str(e)}

    def system_metrics(self) -> dict:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(AURA_ROOT))
        cpu_percent = psutil.cpu_percent(interval=0.5)

        return {
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "memory": {
                "total_mb": mem.total // (1024 * 1024),
                "available_mb": mem.available // (1024 * 1024),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": disk.total // (1024 ** 3),
                "free_gb": disk.free // (1024 ** 3),
                "percent": disk.percent,
            },
            "uptime_seconds": int(time.time() - self._start_time),
        }

    def gpu_status(self) -> dict:
        try:
            import subprocess
            result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                gpus = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
                return {"available": True, "count": len(gpus), "gpus": gpus}
            return {"available": False, "error": "nvidia-smi falhou"}
        except FileNotFoundError:
            return {"available": False, "error": "nvidia-smi não encontrado"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def security_status(self) -> dict:
        return {
            "paper_trade": os.environ.get("PAPER_TRADE", "true").lower() == "true",
            "execution_allowed": os.environ.get("EXECUTION_ALLOWED", "false").lower() == "false",
            "glm_advisory_only": os.environ.get("GLM_ADVISORY_ONLY", "true").lower() == "true",
            "aura_execution_allowed": os.environ.get("AURA_EXECUTION_ALLOWED", "0") == "0",
            "aura_unlock_live": os.environ.get("AURA_UNLOCK_LIVE", "0") == "0",
            "all_safe": all([
                os.environ.get("PAPER_TRADE", "true").lower() == "true",
                os.environ.get("EXECUTION_ALLOWED", "false").lower() == "false",
            ]),
        }

    def full_report(self) -> dict:
        services = [self.check_service(name, config) for name, config in self.SERVICES.items()]
        critical_down = any(s["critical"] and not s["healthy"] for s in services)

        return {
            "timestamp": datetime.now().isoformat(),
            "status": "CRITICAL" if critical_down else "HEALTHY" if all(s["healthy"] for s in services) else "DEGRADED",
            "version": "12.7.62-V25Q-OPERATOR-OS-FINAL",
            "services": services,
            "system": self.system_metrics(),
            "gpu": self.gpu_status(),
            "security": self.security_status(),
        }

    def to_json(self) -> str:
        return json.dumps(self.full_report(), indent=2, ensure_ascii=False)

    def to_prometheus(self) -> str:
        report = self.full_report()
        lines = []

        for svc in report["services"]:
            labels = f'service="{svc["name"]}"'
            lines.append(f'aura_service_up{{{labels}}} {1 if svc["healthy"] else 0}')
            if "latency_ms" in svc:
                lines.append(f'aura_service_latency_ms{{{labels}}} {svc["latency_ms"]}')

        sys_m = report["system"]
        lines.append(f'aura_cpu_percent {sys_m["cpu_percent"]}')
        lines.append(f'aura_memory_percent {sys_m["memory"]["percent"]}')
        lines.append(f'aura_disk_percent {sys_m["disk"]["percent"]}')
        lines.append(f'aura_security_all_safe {1 if report["security"]["all_safe"] else 0}')

        return "\n".join(lines)


def main():
    print("=" * 60)
    print("AURA Health Dashboard v1.0")
    print("=" * 60)

    dash = HealthDashboard()
    report = dash.full_report()

    print("\nStatus geral:", report["status"])
    print("\nServiços:")
    for svc in report["services"]:
        icon = "✅" if svc["healthy"] else "❌"
        print(f"  {icon} {svc['name']:12s} {svc['status']:10s} {svc.get('latency_ms', 'N/A')}ms")

    print("\nSistema:")
    print(f"  CPU: {report['system']['cpu_percent']}%")
    print(f"  Memória: {report['system']['memory']['percent']}%")
    print(f"  Disco: {report['system']['disk']['percent']}%")

    print("\nGPU:")
    if report["gpu"]["available"]:
        print(f"  ✅ {report['gpu']['count']} GPU(s) detectada(s)")
    else:
        print(f"  ❌ {report['gpu'].get('error', 'indisponível')}")

    print("\nSegurança:")
    print(f"  paper_trade={report['security']['paper_trade']}")
    print(f"  execution_allowed={report['security']['execution_allowed']}")
    print(f"  all_safe={report['security']['all_safe']}")

    # Salvar relatórios
    logdir = AURA_ROOT / "logs_supervisor"
    logdir.mkdir(exist_ok=True)

    (logdir / "health_dashboard.json").write_text(dash.to_json(), encoding="utf-8")
    (logdir / "health_dashboard.prom").write_text(dash.to_prometheus(), encoding="utf-8")

    print(f"\nRelatórios salvos em {logdir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
