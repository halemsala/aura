# ============================================================
# MELHORIAS V25Q — Injetar no topo de engine/agents/hermes_supervisor_agent.py
# ============================================================
import os

def detect_gpu_profile() -> dict:
    """Detecta GPU NVIDIA e retorna perfil recomendado."""
    try:
        import subprocess
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gpus = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            mem = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            vrams = [int(line.strip()) for line in mem.stdout.strip().split("\n") if line.strip().isdigit()] if mem.returncode == 0 else []
            total_vram = sum(vrams) if vrams else 0
            return {
                "detected": True,
                "gpu_count": len(gpus),
                "total_vram_mb": total_vram,
                "profile": "full" if total_vram >= 8192 else "limited" if total_vram >= 4096 else "cpu",
                "num_gpu": 99 if total_vram >= 8192 else 50 if total_vram >= 4096 else 0,
            }
    except Exception:
        pass
    return {"detected": False, "profile": "cpu", "num_gpu": 0, "reason": "nvidia-smi indisponivel"}


def health_check_with_retry(url: str, retries: int = 3, timeout: int = 5) -> dict:
    """Health check com retry exponencial."""
    import time
    for attempt in range(retries):
        try:
            import requests
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return {"healthy": True, "attempt": attempt + 1, "latency_ms": int(r.elapsed.total_seconds() * 1000)}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                return {"healthy": False, "attempt": attempt + 1, "error": str(e)}
    return {"healthy": False, "error": "max_retries_exceeded"}


def structured_log(level: str, component: str, message: str, extra: dict = None):
    import json
    from datetime import datetime
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "component": component,
        "message": message,
        "paper_trade": os.environ.get("PAPER_TRADE", "true"),
        "execution_allowed": os.environ.get("EXECUTION_ALLOWED", "false"),
    }
    if extra:
        entry.update(extra)
    print(json.dumps(entry, ensure_ascii=False))

# ============================================================
# USO: Cole estas funcoes no topo do arquivo hermes_supervisor_agent.py
# antes do bloco 'if __name__ == "__main__":'
# ============================================================
