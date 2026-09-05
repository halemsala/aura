#!/usr/bin/env python3
"""VRAM report + recommendations (read-only)."""
from __future__ import annotations
import subprocess, json, sys

def nvidia():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        rows = []
        for line in r.stdout.strip().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 6:
                used, total = float(p[2]), float(p[3])
                rows.append({
                    "index": int(p[0]), "name": p[1],
                    "mem_used_mb": used, "mem_total_mb": total,
                    "mem_pct": round(100*used/total,1) if total else 0,
                    "util_pct": float(p[4]), "temp_c": float(p[5]),
                })
        return rows
    except Exception:
        return []

def tips(gpus):
    out = []
    if not gpus:
        out.append("nvidia-smi indisponivel — report so com driver NVIDIA.")
        return out
    for g in gpus:
        if g["mem_pct"] >= 85:
            out.append(f"GPU{g['index']}: VRAM critica ({g['mem_pct']}%). Use AURA_GROK_GPU_LIVRE.bat; evite XTTS+Ollama juntos.")
        elif g["mem_pct"] >= 70:
            out.append(f"GPU{g['index']}: VRAM alta ({g['mem_pct']}%). Prefira Voice on-demand ou fallback FAST.")
        else:
            out.append(f"GPU{g['index']}: VRAM OK ({g['mem_pct']}%).")
    out.append("Ollama nao e terminado pelos BATs de limpeza AURA (por desenho).")
    return out

def main():
    gpus = nvidia()
    report = {"gpus": gpus, "recommendations": tips(gpus), "paper_trade": True}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
