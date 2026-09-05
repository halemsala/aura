#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA GPU Diagnostic v1.0
Diagnostico completo de GPU NVIDIA para Hermes, Ollama e PyTorch.
"""
import os, sys, json, subprocess, platform
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)
REPORT_PATH = LOGDIR / "gpu_diagnostic.json"
LOG_PATH = LOGDIR / "gpu_diagnostic.log"


def log(msg: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cmd(cmd: list, timeout: int = 15) -> dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "rc": result.returncode}
    except FileNotFoundError:
        return {"ok": False, "error": f"Comando nao encontrado: {cmd[0]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_nvidia_smi() -> dict:
    log("[GPU] Executando nvidia-smi -L...")
    r = run_cmd(["nvidia-smi", "-L"])
    if r["ok"]:
        gpus = [line.strip() for line in r["stdout"].strip().split("\n") if line.strip()]
        log(f"[GPU] GPUs detectadas: {len(gpus)}")
        return {"detected": True, "gpus": gpus, "raw": r["stdout"]}
    else:
        log(f"[GPU] nvidia-smi falhou: {r.get('error', r.get('stderr', 'unknown'))}")
        return {"detected": False, "error": r.get("error", r.get("stderr", "unknown"))}


def check_nvidia_memory() -> dict:
    log("[GPU] Consultando memoria VRAM...")
    r = run_cmd(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used,temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"])
    if r["ok"]:
        lines = [l.strip() for l in r["stdout"].strip().split("\n") if l.strip()]
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_free_mb": int(parts[2]),
                    "memory_used_mb": int(parts[3]),
                    "temperature_c": int(parts[4]),
                    "utilization_percent": int(parts[5])
                })
        log(f"[GPU] Memoria detalhada obtida para {len(gpus)} GPU(s)")
        return {"ok": True, "gpus": gpus}
    return {"ok": False, "error": r.get("error", "unknown")}


def check_cuda() -> dict:
    log("[GPU] Verificando nvcc...")
    r = run_cmd(["nvcc", "--version"])
    if r["ok"]:
        log("[GPU] nvcc encontrado")
        return {"cuda_available": True, "version_info": r["stdout"][:500]}
    log("[GPU] nvcc nao encontrado")
    return {"cuda_available": False, "error": r.get("error", "nvcc nao encontrado")}


def check_pytorch_cuda() -> dict:
    log("[GPU] Verificando PyTorch CUDA...")
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        count = torch.cuda.device_count() if has_cuda else 0
        names = [torch.cuda.get_device_name(i) for i in range(count)] if has_cuda else []
        log(f"[GPU] PyTorch CUDA available={has_cuda}, devices={count}")
        return {"pytorch_cuda": has_cuda, "device_count": count, "device_names": names}
    except ImportError:
        log("[GPU] PyTorch nao instalado")
        return {"pytorch_cuda": False, "error": "PyTorch nao instalado"}
    except Exception as e:
        log(f"[GPU] Erro PyTorch: {e}")
        return {"pytorch_cuda": False, "error": str(e)}


def check_ollama_gpu() -> dict:
    log("[GPU] Verificando Ollama GPU config...")
    return {
        "OLLAMA_NUM_GPU": os.environ.get("OLLAMA_NUM_GPU", "99"),
        "AURA_OLLAMA_KEEP_ALIVE": os.environ.get("AURA_OLLAMA_KEEP_ALIVE", "30m"),
        "AURA_CUDA_DEVICE": os.environ.get("AURA_CUDA_DEVICE", "0"),
        "AURA_HERMES_GPU": os.environ.get("AURA_HERMES_GPU", "1"),
        "recommendation": "num_gpu=99 forca GPU maxima; se VRAM < 8GB, reduza para 50"
    }


def main():
    log("=" * 60)
    log("AURA GPU Diagnostic v1.0")
    log(f"Plataforma: {platform.system()} {platform.release()}")
    log("=" * 60)
    report = {
        "timestamp": datetime.now().isoformat(),
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "nvidia_smi": check_nvidia_smi(),
        "nvidia_memory": check_nvidia_memory(),
        "cuda": check_cuda(),
        "pytorch": check_pytorch_cuda(),
        "ollama_config": check_ollama_gpu(),
        "environment": {
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "nao definido"),
            "AURA_CUDA_DEVICE": os.environ.get("AURA_CUDA_DEVICE", "nao definido"),
            "OLLAMA_NUM_GPU": os.environ.get("OLLAMA_NUM_GPU", "nao definido"),
        }
    }
    if report["nvidia_smi"]["detected"]:
        if report["nvidia_memory"].get("ok"):
            total_vram = sum(g["memory_total_mb"] for g in report["nvidia_memory"]["gpus"])
            if total_vram >= 8192:
                report["recommendation"] = "GPU_OK: Perfil completo (num_gpu=99, Hermes GPU=1)"
            elif total_vram >= 4096:
                report["recommendation"] = "GPU_LIMITED: Reduza OLLAMA_NUM_GPU para 50; Hermes GPU=1"
            else:
                report["recommendation"] = "GPU_LOW: Use CPU fallback (OLLAMA_NUM_GPU=0, AURA_HERMES_GPU=0)"
        else:
            report["recommendation"] = "GPU_DETECTADA: Memoria nao consultavel — use perfil conservador"
    else:
        report["recommendation"] = "GPU_AUSENTE: Fallback CPU obrigatorio (OLLAMA_NUM_GPU=0, AURA_HERMES_GPU=0)"
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(f"[RESUMO] {report['recommendation']}")
    log(f"[RESUMO] Relatorio JSON: {REPORT_PATH}")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
