"""Best-effort NVIDIA sensors via pynvml (optional)."""
from __future__ import annotations

from typing import Any


def read_gpu0() -> dict[str, Any]:
    out: dict[str, Any] = {
        "usage": 0.0,
        "temp": 0.0,
        "mem_temp": 0.0,
        "hotspot": 0.0,
        "power_w": 0.0,
        "power_limit_w": 0.0,
        "mem_used_mb": 0.0,
        "mem_total_mb": 0.0,
        "ok": False,
        "name": None,
    }
    try:
        import pynvml
    except ImportError:
        return out
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        try:
            name = pynvml.nvmlDeviceGetName(handle)
            out["name"] = name.decode() if isinstance(name, bytes) else str(name)
        except Exception:
            pass
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        out["usage"] = float(util.gpu)
        out["temp"] = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
        try:
            mem_enum = getattr(pynvml, "NVML_TEMPERATURE_MEMORY", None)
            if mem_enum is not None:
                out["mem_temp"] = float(pynvml.nvmlDeviceGetTemperature(handle, mem_enum))
        except Exception:
            pass
        try:
            # milliwatts
            out["power_w"] = float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0
        except Exception:
            pass
        try:
            out["power_limit_w"] = float(pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)) / 1000.0
        except Exception:
            try:
                out["power_limit_w"] = float(pynvml.nvmlDeviceGetPowerManagementLimit(handle)) / 1000.0
            except Exception:
                pass
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            out["mem_used_mb"] = float(mem.used) / (1024 * 1024)
            out["mem_total_mb"] = float(mem.total) / (1024 * 1024)
        except Exception:
            pass
        out["ok"] = True
    except Exception:
        out["ok"] = False
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return out


def read_host_snapshot() -> dict[str, Any]:
    """CPU + GPU snapshot for telemetry."""
    import os
    snap: dict[str, Any] = {
        "cpu_pct": 0.0,
        "ram_pct": 0.0,
        "cpu_cores": os.cpu_count() or 1,
        "gpu": read_gpu0(),
    }
    try:
        import psutil
        snap["cpu_pct"] = float(psutil.cpu_percent(interval=0.1))
        snap["ram_pct"] = float(psutil.virtual_memory().percent)
    except Exception:
        pass
    return snap
