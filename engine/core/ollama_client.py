from __future__ import annotations
import os
from typing import Optional

try:
    import httpx
except Exception:
    httpx = None  # type: ignore

_OLLAMA_CLIENT = None


def get_ollama_client():
    global _OLLAMA_CLIENT
    if httpx is None:
        return None
    if _OLLAMA_CLIENT is None:
        host = os.getenv("CORNERAI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        _OLLAMA_CLIENT = httpx.AsyncClient(
            base_url=host,
            timeout=httpx.Timeout(30.0, connect=2.0),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _OLLAMA_CLIENT


async def ask_ollama_optimized(
    prompt: str,
    snapshot: dict,
    route: str = "general",
    model: str = "glm4:9b-chat-q4_0",
) -> str:
    from engine.core.delta_state import DeltaStateEncoder
    from engine.core.semantic_cache import semantic_cache
    from engine.core.llm_grounding import (
        AURA_SYSTEM_PROMPT_V23_GROUNDED,
        validate_llm_output,
        deterministic_reply,
    )

    encoder = DeltaStateEncoder()
    delta_ctx = encoder.encode(snapshot or {})
    state_hash = encoder.last_hash
    cached = semantic_cache.get(route, state_hash)
    if cached:
        return cached
    client = get_ollama_client()
    if client is None:
        return deterministic_reply(route, snapshot or {})
    try:
        resp = await client.post(
            "/api/generate",
            json={
                "model": os.getenv("CORNERAI_CHAT_MODEL", model),
                "system": AURA_SYSTEM_PROMPT_V23_GROUNDED,
                "prompt": f"[CTX:{delta_ctx}]\nQ:{prompt}",
                "stream": False,
                "options": {"temperature": 0.10, "num_predict": 64, "top_p": 0.9},
            },
        )
        data = resp.json()
        reply = str(data.get("response") or "").strip()
    except Exception:
        return deterministic_reply(route, snapshot or {})
    validated = validate_llm_output(reply, snapshot or {})
    semantic_cache.set(route, state_hash, validated)
    return validated


async def close_ollama_client() -> None:
    global _OLLAMA_CLIENT
    if _OLLAMA_CLIENT is not None:
        try:
            await _OLLAMA_CLIENT.aclose()
        except Exception:
            pass
        _OLLAMA_CLIENT = None
