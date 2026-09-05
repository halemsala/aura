#!/usr/bin/env python3
"""AURA System Metrics — CPU, RAM, GPU (read-only). Cross-platform best-effort."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List


def _cpu_ram() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "ok": False,
        "cpu_percent": None,
        "cpu_count": os.cpu_count() or 0,
        "ram_used_mb": None,
        "ram_total_mb": None,
        "ram_percent": None,
        "platform": platform.system(),
        "hint": "",
    }
    try:
        import psutil  # type: ignore

        info["cpu_percent"] = round(psutil.cpu_percent(interval=0.3), 1)
        mem = psutil.virtual_memory()
        info["ram_used_mb"] = round(mem.used / (1024 * 1024), 1)
        info["ram_total_mb"] = round(mem.total / (1024 * 1024), 1)
        info["ram_percent"] = round(mem.percent, 1)
        info["ok"] = True
        return info
    except Exception:
        pass

    # Fallback Windows via PowerShell / wmic
    if platform.system() == "Windows":
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "$c=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                "$m=Get-CimInstance Win32_OperatingSystem; "
                "$used=[math]::Round(($m.TotalVisibleMemorySize-$m.FreePhysicalMemory)/1024,1); "
                "$total=[math]::Round($m.TotalVisibleMemorySize/1024,1); "
                "$pct=[math]::Round(100*($m.TotalVisibleMemorySize-$m.FreePhysicalMemory)/$m.TotalVisibleMemorySize,1); "
                "@{cpu=$c; ram_used=$used; ram_total=$total; ram_pct=$pct} | ConvertTo-Json -Compress"
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                info["cpu_percent"] = round(float(data.get("cpu") or 0), 1)
                info["ram_used_mb"] = float(data.get("ram_used") or 0)
                info["ram_total_mb"] = float(data.get("ram_total") or 0)
                info["ram_percent"] = float(data.get("ram_pct") or 0)
                info["ok"] = True
                return info
        except Exception as e:
            info["hint"] = str(e)
    else:
        # Linux /proc
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            kv = {}
            for ln in lines:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    kv[k.strip()] = v.strip().split()[0]
            total = int(kv.get("MemTotal", 0)) / 1024
            avail = int(kv.get("MemAvailable", kv.get("MemFree", 0))) / 1024
            used = total - avail
            info["ram_total_mb"] = round(total, 1)
            info["ram_used_mb"] = round(used, 1)
            info["ram_percent"] = round(100 * used / total, 1) if total else 0
            # cpu rough
            info["cpu_percent"] = None
            info["ok"] = True
            info["hint"] = "linux /proc (cpu_percent needs psutil)"
            return info
        except Exception as e:
            info["hint"] = str(e)
    return info


def _gpu() -> Dict[str, Any]:
    info: Dict[str, Any] = {"ok": False, "gpus": [], "recommendations": [], "hint": "nvidia-smi indisponivel"}
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return info
        gpus: List[Dict[str, Any]] = []
        tips: List[str] = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                used, total = float(parts[2]), float(parts[3])
                pct = round(100.0 * used / total, 1) if total else 0.0
                g = {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "mem_used_mb": used,
                    "mem_total_mb": total,
                    "mem_pct": pct,
                    "util_pct": float(parts[4]),
                    "temp_c": float(parts[5]),
                }
                gpus.append(g)
                if pct >= 85:
                    tips.append(f"GPU{g['index']}: VRAM CRÍTICA ({pct}%). AURA_GROK_GPU_LIVRE.bat")
                elif pct >= 70:
                    tips.append(f"GPU{g['index']}: VRAM alta ({pct}%).")
                if g["temp_c"] >= 80:
                    tips.append(f"GPU{g['index']}: temp elevada ({g['temp_c']}°C)")
        info = {"ok": True, "gpus": gpus, "recommendations": tips or ["GPU OK"], "hint": "ok"}
    except Exception as e:
        info["hint"] = str(e)
    return info


def services_ports() -> Dict[str, Any]:
    """Check known AURA ports (Windows netstat / Linux ss)."""
    ports = {
        8080: "bridge",
        8765: "engine",
        8766: "matriz",
        8777: "hermes_chat",
        8778: "hermes_dash",
        8099: "voice",
        8790: "tools_control",
        11434: "ollama",
    }
    listening: Dict[str, bool] = {name: False for name in ports.values()}
    try:
        if platform.system() == "Windows":
            r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=8)
            text = r.stdout or ""
            for port, name in ports.items():
                if f":{port}" in text and "LISTENING" in text:
                    # rough but effective
                    for line in text.splitlines():
                        if f":{port}" in line and "LISTENING" in line.upper():
                            listening[name] = True
                            break
        else:
            r = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=5)
            text = r.stdout or ""
            for port, name in ports.items():
                if f":{port} " in text or f":{port}\n" in text:
                    listening[name] = True
    except Exception:
        pass
    return {"ports": listening, "summary": {k: ("UP" if v else "DOWN") for k, v in listening.items()}}


def collect() -> Dict[str, Any]:
    cpu_ram = _cpu_ram()
    gpu = _gpu()
    svc = services_ports()
    tips = list(gpu.get("recommendations") or [])
    if cpu_ram.get("ok") and cpu_ram.get("ram_percent") is not None:
        if cpu_ram["ram_percent"] >= 90:
            tips.append(f"RAM crítica ({cpu_ram['ram_percent']}%). Feche apps pesadas.")
        elif cpu_ram["ram_percent"] >= 80:
            tips.append(f"RAM alta ({cpu_ram['ram_percent']}%).")
    if cpu_ram.get("ok") and cpu_ram.get("cpu_percent") is not None:
        if cpu_ram["cpu_percent"] >= 90:
            tips.append(f"CPU alta ({cpu_ram['cpu_percent']}%).")
    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paper_trade": True,
        "execution_allowed": False,
        "cpu_ram": cpu_ram,
        "vram": gpu,
        "services": svc,
        "recommendations": tips,
    }


def main() -> int:
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
