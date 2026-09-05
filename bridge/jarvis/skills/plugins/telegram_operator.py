# bridge/jarvis/skills/plugins/telegram_operator.py
"""
Skill: Telegram Operator (modo humano — teclado/mouse, zero API)

Mesma arquitetura do WhatsApp Operator.
Atalhos idênticos: Ctrl+F → nome → Enter → Ctrl+V → Enter.
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from .whatsapp_operator import Skill as WhatsAppSkill
except ImportError:
    from jarvis.skills.plugins.whatsapp_operator import Skill as WhatsAppSkill


class Skill(WhatsAppSkill):
    def __init__(self):
        super().__init__()
        self.description = (
            "Envia mensagens/arquivos por Telegram Desktop como humano "
            "(teclado/mouse, sem API). Ações: send_message, send_file. "
            "Requer AURA_TELEGRAM_OPERATOR_ENABLED=1 e confirmação por voz."
        )
        self.window_keyword = "telegram"
        self.env_flag = "AURA_TELEGRAM_OPERATOR_ENABLED"
