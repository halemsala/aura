# Patch de exemplo para bridge/jarvis/core/llm_router.py
# Adicione estas linhas no final da classe LLMRouter ou no método select()

"""
=== ADICIONE NO TOPO DO ARQUIVO (junto com os outros imports de env) ===

DEEPSEEK_ENABLED = os.environ.get("AURA_DEEPSEEK_HARNESS_ENABLED", "0") == "1"
DEEPSEEK_MODEL = os.environ.get("AURA_LLM_DEEPSEEK", "deepseek-chat")

=== ADICIONE DENTRO DO MÉTODO select() (depois dos checks existentes) ===

        # DeepSeek Harness (nuvem) — só quando explicitamente forçado ou em modo hybrid
        if force_model and "deepseek" in force_model.lower():
            if DEEPSEEK_ENABLED:
                return DEEPSEEK_MODEL
            return PRIMARY

        # Exemplo de rota híbrida: se o texto pedir "use deepseek" ou "harness"
        if DEEPSEEK_ENABLED and any(k in (text or "").lower() for k in ("deepseek", "harness", "use dsh")):
            return DEEPSEEK_MODEL
"""
