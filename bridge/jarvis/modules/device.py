"""Hardware policy for local AURA voice/LLM.

The Windows Task Manager GPU numbering is not CUDA numbering. On hybrid
laptops GPU 0 can be Intel UHD while CUDA sees the NVIDIA RTX as cuda:0.
Select by CUDA capability/VRAM, never by Task Manager label.
"""
import os
import shutil
import subprocess
import time
try:
    import torch
except Exception:
    torch = None


def _nvidia_vram_gb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL, timeout=3
        ).strip().splitlines()
        vals = [float(x.strip()) for x in out if x.strip()]
        return max(vals) / 1024 if vals else 0.0
    except Exception:
        return 0.0

def resolve_device(mode: str = "auto") -> str:
    if mode == "cpu":
        return "cpu"
    cuda_ok = bool(torch is not None and torch.cuda.is_available()) or _nvidia_vram_gb() > 0
    if not cuda_ok:
        if mode == "cuda":
            print("[device] CUDA solicitado mas indisponível. Usando CPU.")
        return "cpu"
    if torch is not None and torch.cuda.is_available():
        count = torch.cuda.device_count()
        best_idx = max(range(count), key=lambda i: torch.cuda.get_device_properties(i).total_memory)
        name = torch.cuda.get_device_name(best_idx)
        os.environ.setdefault("AURA_CUDA_DEVICE", str(best_idx))
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(best_idx))
        print(f"[device] NVIDIA CUDA selecionada: cuda:{best_idx} | {name}")
    else:
        print("[device] NVIDIA CUDA detectada via nvidia-smi | usando cuda:0")
    # faster-whisper/CTranslate2 usa o backend 'cuda'; o índice é controlado pelo ambiente.
    return "cuda"

def get_vram_gb(device: str = "cuda") -> float:
    if not device.startswith("cuda"):
        return 0.0
    if torch is not None and torch.cuda.is_available():
        idx = int(device.split(":", 1)[1]) if ":" in device else 0
        props = torch.cuda.get_device_properties(idx)
        return round(props.total_memory / (1024 ** 3), 1)
    return round(_nvidia_vram_gb(), 1)


# Voice concurrency budget. RTX 4050 6 GB: prioriza quantização leve + latência.
# q4_0 / q4_K_M = melhor equilíbrio qualidade/VRAM; q8 só com folga.
_TARGET_GLM_MODEL = "glm4:9b-chat-q4_0"
_LLM_TIERS = [
    # (VRAM mínima GB, modelo Ollama com quant explícita quando possível)
    (24.0, "qwen2.5:14b-instruct-q4_K_M"),
    (16.0, "qwen2.5:14b-instruct-q4_0"),
    (12.0, "llama3.1:8b-instruct-q4_K_M"),
    (10.0, "llama3.1:8b-instruct-q4_0"),
    (8.0, "llama3.2:3b-instruct-q8_0"),
    # Perfil recomendado no anexo GLM-4 para RTX 4050 Laptop 6 GB.
    (5.5, _TARGET_GLM_MODEL),
    (0.0, "llama3.2:3b"),  # q4 implícito / tag padrão Ollama
]

# Opções de inferência por faixa de VRAM (passadas ao Ollama)
_LLM_RUNTIME = {
    "6gb": {"num_ctx": 2048, "num_batch": 256, "num_gpu": 99, "temperature": 0.25},
    "8gb": {"num_ctx": 3072, "num_batch": 512, "num_gpu": 99, "temperature": 0.25},
    "12gb": {"num_ctx": 4096, "num_batch": 512, "num_gpu": 99, "temperature": 0.22},
    "full": {"num_ctx": 8192, "num_batch": 512, "num_gpu": 99, "temperature": 0.2},
}


def recommend_llm_runtime(device: str) -> dict:
    """Retorna opções Ollama otimizadas por VRAM (quant + contexto + batch)."""
    if not str(device).startswith("cuda"):
        return dict(_LLM_RUNTIME["6gb"], num_gpu=0, profile="cpu")
    vram = get_vram_gb(device)
    if vram <= 7.0:
        return dict(_LLM_RUNTIME["6gb"], profile="voice_6gb_q4")
    if vram <= 9.0:
        return dict(_LLM_RUNTIME["8gb"], profile="voice_8gb_q4_q8")
    if vram <= 14.0:
        return dict(_LLM_RUNTIME["12gb"], profile="voice_12gb_q4km")
    return dict(_LLM_RUNTIME["full"], profile="full_gpu")


def recommend_llm_model(device: str) -> str:
    """Escolhe modelo+quant por VRAM; 6 GB usa GLM-4 quantizado como alvo."""
    if not str(device).startswith("cuda"):
        print("[device] CPU: usando llama3.2:3b.")
        return "llama3.2:3b"
    vram = get_vram_gb(device)
    if vram <= 7.0:
        print(f"[device] VRAM {vram}GB -> GLM-4 quantizado: {_TARGET_GLM_MODEL}")
        return _TARGET_GLM_MODEL
    for min_vram, model in _LLM_TIERS:
        if vram >= min_vram:
            print(f"[device] VRAM {vram}GB -> modelo/quant: {model}")
            return model
    return "llama3.2:3b"


def _find_ollama_exe():
    """Localiza o Ollama no PATH e nos caminhos padrão do Windows."""
    candidates = [
        shutil.which("ollama"),
        os.path.expandvars(r"%LocalAppData%\\Programs\\Ollama\\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\\Ollama\\ollama.exe"),
        r"C:\\Windows\\System32\\ollama.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _ollama_api_models(host: str):
    import requests
    response = requests.get(f"{host.rstrip('/')}/api/tags", timeout=5)
    response.raise_for_status()
    return [m.get("name", "") for m in response.json().get("models", [])]


def get_available_glm_model(host: str = "http://localhost:11434"):
    """Retorna o tag exato do GLM-4 quando ele está instalado localmente.

    A função é não destrutiva: apenas consulta o CLI/API do Ollama e retorna
    ``None`` quando o serviço ou o modelo não estão disponíveis. Isso mantém o
    boot do Voice funcional antes do download opcional do modelo.
    """
    exe = _find_ollama_exe()
    if exe:
        try:
            result = subprocess.run(
                [exe, "list"], capture_output=True, text=True, timeout=20
            )
            for line in result.stdout.splitlines():
                fields = line.strip().split()
                if fields and fields[0] == _TARGET_GLM_MODEL:
                    return _TARGET_GLM_MODEL
        except Exception:
            pass
    try:
        if _TARGET_GLM_MODEL in _ollama_api_models(host):
            return _TARGET_GLM_MODEL
    except Exception:
        pass
    return None


def get_llm_model(
    model_name=None,
    device: str = "auto",
    host: str = "http://localhost:11434",
    require_glm: bool = False,
) -> str:
    """Resolve o modelo configurado sem remover os fallbacks existentes.

    Um nome explícito, inclusive ``glm4:9b-chat-q4_0``, é sempre respeitado. Para
    ``auto``, o GLM-4 instalado é preferido; se ainda não foi baixado, a função
    usa a recomendação de VRAM já existente, salvo quando ``require_glm=True``.
    """
    requested = str(model_name or "").strip()
    if requested and requested.lower() != "auto":
        return requested
    resolved_device = str(device or "auto").strip().lower()
    if resolved_device == "auto":
        resolved_device = resolve_device("auto")
    glm = get_available_glm_model(host)
    if glm:
        return glm
    if require_glm:
        raise RuntimeError(
            f"Modelo {_TARGET_GLM_MODEL} nao encontrado. "
            f"Execute: ollama pull {_TARGET_GLM_MODEL}"
        )
    return recommend_llm_model(resolved_device)


def get_torch_device():
    """Retorna ``torch.device`` quando Torch existe; caso contrário, ``cpu``."""
    if torch is None:
        return "cpu"
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def ensure_ollama_model(model: str, host: str = "http://localhost:11434", auto_pull: bool = False) -> bool:
    """Verifica um modelo local e só faz download quando `auto_pull=True`.

    O modo padrão é fail-closed: ausência do modelo não dispara download de
    gigabytes durante o boot. O LLM pode então selecionar um fallback já
    instalado e reportar o estado com clareza.
    """
    exe = _find_ollama_exe()
    if exe:
        try:
            listed = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=20)
            if model in listed.stdout:
                return True
        except Exception as e:
            print(f"[device] CLI do Ollama falhou; tentando API local: {e}")

    try:
        names = _ollama_api_models(host)
        if any(model == name or model.split(":")[0] == name.split(":")[0] for name in names):
            return True
        if not auto_pull:
            print(f"[device] Modelo '{model}' ausente; auto_pull_model=false, nenhum download iniciado.")
            return False
    except Exception as e:
        if not auto_pull:
            print(f"[device] Ollama indisponível e auto_pull_model=false: {e}")
            return False
        print(f"[device] API do Ollama indisponível; tentando pull quando possível: {e}")

    if not auto_pull:
        return False

    if exe:
        try:
            print(f"[device] Baixando modelo '{model}' via Ollama CLI...")
            result = subprocess.run([exe, "pull", model], timeout=3600)
            if result.returncode == 0:
                return True
        except Exception as e:
            print(f"[device] Pull via CLI falhou; tentando API local: {e}")

    for attempt in range(8):
        try:
            import requests
            response = requests.post(
                f"{host.rstrip('/')}/api/pull",
                json={"name": model, "stream": False},
                timeout=3600,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            if attempt == 7:
                print(f"[device] Pull do Ollama falhou após tentativas: {e}")
                return False
            time.sleep(2)
    return False


def warm_ollama_model(host: str, model: str) -> bool:
    """Keep the local LLM resident and compile its first inference at startup."""
    try:
        import requests
        r = requests.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Responda apenas: pronto."}],
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 2, "temperature": 0.0, "num_ctx": 512},
            },
            timeout=120,
        )
        r.raise_for_status()
        print(f"[device] Ollama aquecido e residente: {model}")
        return True
    except Exception as e:
        print(f"[device] Warmup Ollama não concluído: {e}")
        return False
