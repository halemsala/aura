# glm5_inference_bridge.py
# AURA QUANT-X v12.6.17 / v12.8.x — GLM5 Local Inference Bridge (Production)
from __future__ import annotations
import asyncio, gc, json, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional
import psutil
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
try:
    from transformers import AutoModel, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

GLM5_MODEL_PATH = "THUDM/chatglm3-6b"
MAX_CONTEXT_TOKENS = 512
SLIDING_WINDOW_INTERACTIONS = 3
MEMORY_USAGE_THRESHOLD = 0.85
INFERENCE_THREAD_POOL_WORKERS = 2
NDJSON_CHUNK_INTERVAL_S = 0.32

_SURVIVABILITY_CACHE = {
    "BUY_CORNER": "Alerta quant. Sinal de compra de escanteio detectado. Execute com disciplina de stake.",
    "WATCH_CORNER": "Mercado em observação. Velocidade de odds negativa. Aguardar confirmação de confluência.",
    "HOLD": "Sem edge claro. Manter posição neutra. Monitorar telemetria.",
    "BLOCKED_BY_MARKET": "Bloqueio de mercado por smart money ou velocidade excessiva. Abortar entrada.",
    "default": "Sistema em modo de sobrevivência. Resposta cacheada. Recursos de memória acima do limiar."
}

def sanitize_context_for_glm5(context_string: str, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    if not context_string or not context_string.strip():
        return ""
    parts = [p.strip() for p in context_string.replace("\r\n", "\n").split("\n") if p.strip()]
    if not parts:
        return ""
    recent = parts[-SLIDING_WINDOW_INTERACTIONS:] if len(parts) > SLIDING_WINDOW_INTERACTIONS else parts
    sanitized = " | ".join(recent)
    tokens = sanitized.split()
    if len(tokens) > max_tokens:
        sanitized = " ".join(tokens[-max_tokens:])
    return sanitized.strip()

GLM5_SYSTEM_PROMPT = """Você é o motor de voz Kanteiro do AURA QUANT-X.
Responda exclusivamente em português técnico, conciso e acionável.
Separe rigorosamente dados numéricos de raciocínio usando os marcadores XML abaixo.
Nunca invente números. Use apenas os valores fornecidos dentro das tags.

<template>
<market_data>
{market_data}
</market_data>
<risk_state>
{risk_state}
</risk_state>
<action_required>
{action_required}
</action_required>
</template>

Regras:
1. Extraia floats e estados somente das tags XML.
2. Gere no máximo 3 frases curtas.
3. Se action_required indicar HOLD ou BLOCKED, recomende cautela.
4. Nunca calcule edge, stake ou probabilidade por conta própria.
"""

def build_glm5_prompt(market_data: str, risk_state: str, action_required: str, sanitized_context: str = "") -> str:
    prompt = GLM5_SYSTEM_PROMPT.format(
        market_data=market_data or "N/A",
        risk_state=risk_state or "N/A",
        action_required=action_required or "HOLD"
    )
    if sanitized_context:
        prompt += f"\n\n<contexto_recente>\n{sanitized_context}\n</contexto_recente>"
    return prompt

class GLM5Bridge:
    def __init__(self, model_path: str = GLM5_MODEL_PATH, max_workers: int = INFERENCE_THREAD_POOL_WORKERS, device: Optional[str] = None):
        self.model_path = model_path
        self.device = device or ("cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="glm5_inf")
        self._model = None
        self._tokenizer = None
        self._interaction_history: Deque[str] = deque(maxlen=SLIDING_WINDOW_INTERACTIONS)
        self._loaded = False
        self._survivability_mode = False

    def _check_memory_pressure(self) -> bool:
        try:
            mem = psutil.virtual_memory()
            if mem.percent / 100.0 >= MEMORY_USAGE_THRESHOLD:
                return True
            if TORCH_AVAILABLE and torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated()
                total = torch.cuda.get_device_properties(0).total_memory
                if total > 0 and (allocated / total) >= MEMORY_USAGE_THRESHOLD:
                    return True
        except Exception:
            pass
        return False

    def _force_memory_cleanup(self) -> None:
        gc.collect()
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            except Exception:
                pass

    def _load_model_sync(self) -> None:
        if self._loaded or not TRANSFORMERS_AVAILABLE:
            return
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
            self._model = AutoModel.from_pretrained(self.model_path, trust_remote_code=True, device_map="auto" if self.device == "cuda" else None)
            if self.device == "cpu":
                self._model = self._model.float()
            self._model.eval()
            self._loaded = True
        except Exception:
            self._loaded = False
            self._survivability_mode = True

    def _generate_sync(self, prompt: str, max_new_tokens: int = 128, temperature: float = 0.3) -> str:
        if self._check_memory_pressure():
            self._survivability_mode = True
            return _SURVIVABILITY_CACHE["default"]
        if not self._loaded:
            self._load_model_sync()
            if not self._loaded:
                return _SURVIVABILITY_CACHE["default"]
        try:
            inputs = self._tokenizer([prompt], return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self._model.generate(**inputs, max_new_tokens=max_new_tokens, temperature=temperature, do_sample=temperature > 0, top_p=0.85, repetition_penalty=1.1, pad_token_id=self._tokenizer.eos_token_id)
            response = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
            if prompt in response:
                response = response[len(prompt):].strip()
            return response.strip() or _SURVIVABILITY_CACHE["default"]
        except Exception:
            self._survivability_mode = True
            return _SURVIVABILITY_CACHE["default"]
        finally:
            self._force_memory_cleanup()

    async def generate(self, market_data: str, risk_state: str, action_required: str, raw_context: str = "", max_new_tokens: int = 128) -> str:
        if self._check_memory_pressure() or self._survivability_mode:
            key = action_required if action_required in _SURVIVABILITY_CACHE else "default"
            return _SURVIVABILITY_CACHE[key]
        sanitized = sanitize_context_for_glm5(raw_context)
        self._interaction_history.append(sanitized)
        window_ctx = " || ".join(list(self._interaction_history))
        prompt = build_glm5_prompt(market_data, risk_state, action_required, window_ctx)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._generate_sync, prompt, max_new_tokens)

    async def stream_generate(self, market_data: str, risk_state: str, action_required: str, raw_context: str = "", max_new_tokens: int = 128) -> AsyncGenerator[str, None]:
        text = await self.generate(market_data=market_data, risk_state=risk_state, action_required=action_required, raw_context=raw_context, max_new_tokens=max_new_tokens)
        words = text.split()
        buffer: List[str] = []
        for w in words:
            buffer.append(w)
            if len(buffer) >= 3:
                yield " ".join(buffer)
                buffer = []
                await asyncio.sleep(0.05)
        if buffer:
            yield " ".join(buffer)

    async def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._force_memory_cleanup()
        self._model = None
        self._tokenizer = None
        self._loaded = False

_glm5_bridge_instance: Optional[GLM5Bridge] = None

def get_glm5_bridge() -> GLM5Bridge:
    global _glm5_bridge_instance
    if _glm5_bridge_instance is None:
        _glm5_bridge_instance = GLM5Bridge()
    return _glm5_bridge_instance

async def glm5_voice_stream_handler(odds: float, linha: float, estado: str, raw_context: str = "") -> AsyncGenerator[str, None]:
    bridge = get_glm5_bridge()
    market_data = f"asian_corner_odds={odds:.4f}; asian_corner_line={linha:.2f}"
    risk_state = f"signal_state={estado}"
    action_required = estado if estado in _SURVIVABILITY_CACHE else "HOLD"
    yield json.dumps({"type": "context", "data": f"[CONTEXTO] Odds em {odds}, Linha Asiática {linha}. Estado atual: {estado}."}) + "\n"
    await asyncio.sleep(0.05)
    async for chunk in bridge.stream_generate(market_data=market_data, risk_state=risk_state, action_required=action_required, raw_context=raw_context):
        yield json.dumps({"type": "audio_chunk", "text": chunk}) + "\n"
        await asyncio.sleep(NDJSON_CHUNK_INTERVAL_S)

__all__ = ["GLM5Bridge", "get_glm5_bridge", "sanitize_context_for_glm5", "build_glm5_prompt", "glm5_voice_stream_handler", "GLM5_SYSTEM_PROMPT"]
