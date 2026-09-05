# bridge/jarvis/router/voice_skill_bridge.py
"""
Ponte voz ↔ skills de operador humano (WhatsApp / Telegram).

Fluxo de confirmação (anel 4):
  1) Usuário: "manda pro João: reunião às 15h"
  2) LLM emite intenção → skill prepara (janela + contato verificados)
  3) Skill devolve "PRONTO PARA ENVIAR... Confirme por voz"
  4) Router guarda pending; fala a pergunta
  5) Usuário: "confirmo" → re-executa com _confirmado_pelo_operador=True
  6) Enter final envia

Integração no voice server:
  from bridge.jarvis.router.voice_skill_bridge import SKILL_BRIDGE
  spoken = SKILL_BRIDGE.handle(transcript)
  if spoken is not None:
      return spoken  # já tratou (skill ou confirmação)
  # senão cai no VoiceRouter normal
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("aura.jarvis.skill_bridge")

CONFIRM_WORDS = ("confirmo", "confirma", "pode mandar", "pode enviar", "autorizo envio", "manda")
CANCEL_WORDS = ("cancela", "cancelar", "aborta", "não", "nao", "para")

# Mapeamento de intenções simples → skill (sem depender de LLM para o caso comum)
SEND_RE = re.compile(
    r"(?:manda|envia|enviar|mandar)\s+(?:pro|para|ao|à|a)\s+([A-Za-zÀ-ú0-9 ._-]+?)\s*[:\-]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
SEND_FILE_RE = re.compile(
    r"(?:manda|envia|enviar)\s+(?:o\s+)?(?:arquivo|ficheiro|file)\s+(.+?)\s+(?:pro|para)\s+([A-Za-zÀ-ú0-9 ._-]+)$",
    re.IGNORECASE,
)


@dataclass
class PendingSend:
    skill_name: str
    action: str
    args: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    expires_s: float = 90.0

    def alive(self) -> bool:
        return (time.time() - self.created_at) < self.expires_s


class VoiceSkillBridge:
    def __init__(self) -> None:
        self._pending: Optional[PendingSend] = None
        self._skill_manager = None

    def _sm(self):
        if self._skill_manager is None:
            try:
                from bridge.jarvis.skills.skill_manager import SKILL_MANAGER
                self._skill_manager = SKILL_MANAGER
            except Exception as e:
                logger.error("SkillManager indisponível: %s", e)
        return self._skill_manager

    def handle(self, transcript: str) -> Optional[str]:
        """
        Retorna string falada se tratou o turno; None se deve cair no router normal.
        """
        t = (transcript or "").strip()
        if not t:
            return None

        low = t.lower()

        # ── Confirmação / cancelamento de pending ──
        if self._pending and self._pending.alive():
            if any(w in low for w in CONFIRM_WORDS):
                return self._confirm()
            if any(w in low for w in CANCEL_WORDS):
                self._pending = None
                return "Envio cancelado. Nada foi enviado."
            # Outra frase: não consome o pending (ainda válido)
            # mas se for novo pedido de envio, substitui

        # ── Intenção determinística de envio ──
        m = SEND_RE.search(t)
        if m:
            contato, texto = m.group(1).strip(), m.group(2).strip()
            return self._prepare("whatsapp_operator", "send_message", {
                "contato": contato,
                "texto": texto,
            })

        m = SEND_FILE_RE.search(t)
        if m:
            path, contato = m.group(1).strip().strip("\"'"), m.group(2).strip()
            return self._prepare("whatsapp_operator", "send_file", {
                "contato": contato,
                "path": path,
            })

        # Telegram explícito
        if "telegram" in low and ("manda" in low or "envia" in low):
            m = re.search(
                r"(?:telegram).{0,20}(?:pro|para)\s+([A-Za-zÀ-ú0-9 ._-]+?)\s*[:\-]\s*(.+)$",
                t, re.I | re.DOTALL,
            )
            if m:
                return self._prepare("telegram_operator", "send_message", {
                    "contato": m.group(1).strip(),
                    "texto": m.group(2).strip(),
                })

        return None

    def _prepare(self, skill_name: str, action: str, args: Dict[str, Any]) -> str:
        sm = self._sm()
        if sm is None:
            return "Skill manager indisponível."

        # Primeira passagem: SEM confirmação → skill valida janela/contato e devolve PRONTO
        result = sm.execute_skill(skill_name, action, dict(args))
        if result.startswith("PRONTO PARA ENVIAR"):
            self._pending = PendingSend(skill_name=skill_name, action=action, args=dict(args))
            # Frase curta para TTS
            contato = args.get("contato", "?")
            return (
                f"Pronto para enviar para {contato}. "
                f"Confirma dizendo confirmo, ou cancela."
            )
        # Erro / aborto / flag desligada
        self._pending = None
        return result

    def _confirm(self) -> str:
        if not self._pending or not self._pending.alive():
            self._pending = None
            return "Não há envio pendente."
        pending = self._pending
        self._pending = None
        sm = self._sm()
        if sm is None:
            return "Skill manager indisponível."
        args = dict(pending.args)
        args["_confirmado_pelo_operador"] = True
        return sm.execute_skill(pending.skill_name, pending.action, args)

    def clear_pending(self) -> None:
        self._pending = None


SKILL_BRIDGE = VoiceSkillBridge()
