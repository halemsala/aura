# bridge/jarvis/core/llm_router.py
"""
Roteador de modelos — arquitetura AURA (RTX 4050 6GB) + DeepSeek Harness

  LOCAL (sempre no notebook):
    qwen2.5:3b-instruct  → cérebro principal (chat, tool calls, PT-BR, skills)
    llama3.2:3b          → especialista (docs gigantes, instruções compostas)
    hermes-aura          → modo trading / análise

  NUVEM (opcional via DeepSeek Harness):
    deepseek-chat / deepseek-reasoner  → quando explicitamente solicitado
                                         ou AURA_DEEPSEEK_HARNESS_ENABLED=1

Regras de seleção (ordem de prioridade):
  1) force_model explícito
  2) Pedido explícito de DeepSeek / Harness no texto
  3) Contexto longo (>24k tokens estimados) → llama3.2:3b
  4) Agente / tool call / JSON               → qwen2.5:3b-instruct
  5) Instrução composta (2+ passos)         → llama3.2:3b
  6) Modo trading                           → hermes / primary
  7) Padrão                                 → qwen2.5:3b-instruct
"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional

ModeName = Literal["trading", "creative"]

# === Modelos locais (nunca GLM no runtime principal) ===
PRIMARY = os.environ.get("AURA_LLM_PRIMARY", "qwen2.5:3b-instruct")
LONGCTX = os.environ.get("AURA_LLM_LONGCTX", "llama3.2:3b")
JSON_AGENT = os.environ.get("AURA_LLM_JSON", "qwen2.5:3b-instruct")
TRADING_MODEL = os.environ.get("AURA_LLM_TRADING", "hermes-aura")

MODE_MODELS = {
    "trading": os.environ.get("AURA_LLM_TRADING", PRIMARY),
    "creative": os.environ.get("AURA_LLM_CREATIVE", PRIMARY),
}

# === DeepSeek Harness (nuvem) ===
DEEPSEEK_ENABLED = os.environ.get("AURA_DEEPSEEK_HARNESS_ENABLED", "0") == "1"
DEEPSEEK_MODEL = os.environ.get("AURA_LLM_DEEPSEEK", "deepseek-chat")

CHARS_PER_TOKEN = 3
LONGCTX_THRESHOLD = 24000

COMPOUND_RE = re.compile(
    r"(depois|em seguida|ent[ãa]o|se falhar|se n[ãa]o|primeiro|segundo|terceiro|"
    r"ap[óo]s isso|caso contr[áa]rio|e depois)",
    re.IGNORECASE,
)

# Palavras-chave que forçam uso do DeepSeek
DEEPSEEK_TRIGGER_RE = re.compile(
    r"\b(deepseek|use\s+dsh|harness|modelo\s+deepseek|usa\s+o\s+deepseek)\b",
    re.IGNORECASE,
)

# Lista negra: GLM e variantes nunca entram no runtime local via este router
BLOCKED_LOCAL = ("glm", "glm4", "glm-4", "chatglm")


def _is_blocked(name: str) -> bool:
    low = (name or "").lower()
    return any(b in low for b in BLOCKED_LOCAL)


class LLMRouter:
    def __init__(self) -> None:
        self.current_mode: ModeName = "trading"

    def set_mode(self, mode: ModeName) -> None:
        if mode in MODE_MODELS:
            self.current_mode = mode

    def select(
        self,
        text: str = "",
        needs_json: bool = False,
        est_tokens: int = 0,
        system_prompt: str = "",
        force_model: Optional[str] = None,
    ) -> str:
        """
        Retorna o nome do modelo a usar.
        - Modelos locais: nomes Ollama (qwen..., llama..., hermes...)
        - DeepSeek: retorna o valor de AURA_LLM_DEEPSEEK (ex: deepseek-chat)
        """
        # 1) Forçado explicitamente
        if force_model:
            if _is_blocked(force_model):
                return PRIMARY
            if "deepseek" in force_model.lower():
                return DEEPSEEK_MODEL if DEEPSEEK_ENABLED else PRIMARY
            return force_model

        # 2) Pedido explícito de DeepSeek / Harness no texto do usuário
        if DEEPSEEK_ENABLED and DEEPSEEK_TRIGGER_RE.search(text or ""):
            return DEEPSEEK_MODEL

        # 3) Estimativa de tokens se não veio pronta
        if est_tokens <= 0 and text:
            est_tokens = max(1, len(text) // CHARS_PER_TOKEN)
        if system_prompt:
            est_tokens += max(1, len(system_prompt) // CHARS_PER_TOKEN)

        # 4) Contexto longo → llama
        if est_tokens >= LONGCTX_THRESHOLD:
            return LONGCTX

        # 5) Precisa de JSON / tool call / agente → qwen (melhor em structured output)
        if needs_json:
            return JSON_AGENT

        # 6) Instrução composta (múltiplos passos) → llama
        if COMPOUND_RE.search(text or ""):
            return LONGCTX

        # 7) Modo trading
        if self.current_mode == "trading":
            return MODE_MODELS.get("trading", TRADING_MODEL)

        # 8) Padrão
        return MODE_MODELS.get(self.current_mode, PRIMARY)

    def keep_alive_for(self, model: str) -> str:
        """
        Retorna o valor de keep_alive recomendado para o modelo.
        DeepSeek (nuvem) não usa keep_alive do Ollama.
        """
        if "deepseek" in (model or "").lower():
            return "0"  # não se aplica

        # Modelos longos sobem on-demand
        if model == LONGCTX:
            return os.environ.get("AURA_OLLAMA_KEEP_ALIVE", "0m")

        return os.environ.get("AURA_OLLAMA_KEEP_ALIVE", "5m")

    def is_cloud_model(self, model: str) -> bool:
        """Indica se o modelo selecionado é de nuvem (DeepSeek)."""
        return "deepseek" in (model or "").lower()


# Instância global usada pelo resto do sistema
LLM_ROUTER = LLMRouter()
