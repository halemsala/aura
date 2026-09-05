# --- integração Alfred (inserir uma única vez, no topo do módulo de rotas) ---
try:
    from alfred.bridge import try_handle as alfred_try_handle
except Exception:
    alfred_try_handle = None  # Alfred ausente: Hermes funciona como hoje
# ---------------------------------------------------------------------------

# dentro do handler, com user_message e session_id em mãos:
if alfred_try_handle is not None:
    alfred = alfred_try_handle(user_message, session_id=session_id)
    if alfred is not None:
        return {
            "reply": alfred["reply"],
            "model": alfred["model"],          # "alfred:qwen3:8b" ou "qwen3:8b" (só conversação)
            "alfred_plan": alfred.get("plan"),  # a UI usa para botões autorizar/cancelar/progresso
            "alfred_job": alfred.get("job"),
            "requires_confirmation": alfred.get("requires_confirmation", False),
        }
# ... segue o fluxo normal do Hermes (fallback LLM) ...
