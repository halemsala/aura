# -*- coding: utf-8 -*-
"""
Hook de voz JARVIS.

Ordem:
  1) VoiceSkillBridge (WhatsApp/Telegram operador humano + confirmação)
  2) VoiceRouter clássico (desktop_control / panic / face)

Uso:
  from bridge.jarvis.router.hook_voice_server import process_voice_command
"""
from __future__ import annotations

import logging

logger = logging.getLogger("aura.jarvis.hook")

try:
    from bridge.jarvis.router.voice_skill_bridge import SKILL_BRIDGE
except Exception as e:
    SKILL_BRIDGE = None
    logger.debug("voice_skill_bridge indisponível: %s", e)

try:
    from bridge.jarvis.router.voice_router import process_voice_command as _router_process
    from bridge.jarvis.router.voice_router import VOICE_ROUTER
except Exception:
    _router_process = None
    VOICE_ROUTER = None


def process_voice_command(user_transcript: str) -> str:
    """API estável para jarvis_voice_server integrar."""
    text = (user_transcript or "").strip()
    if not text:
        return "Não ouvi nada."

    # 1) Skills de operador humano (envio + anel de confirmação)
    if SKILL_BRIDGE is not None:
        try:
            spoken = SKILL_BRIDGE.handle(text)
            if spoken is not None:
                return spoken
        except Exception as e:
            logger.exception("skill_bridge fail: %s", e)

    # 2) Router clássico
    if _router_process is not None:
        return _router_process(text)

    return "Router de voz indisponível."


__all__ = ["process_voice_command", "VOICE_ROUTER", "SKILL_BRIDGE"]
