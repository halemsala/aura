"""Roteador seguro de comandos de voz locais.

O módulo apenas classifica comandos. A execução deve ser feita por um gatekeeper
já autenticado; nenhuma chamada de rede ou alteração de estado ocorre aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class VoiceCommand:
    name: str
    reply: str
    requires_confirmation: bool = True


class VoiceCommandRouter:
    def __init__(self, *, authorizer: Optional[Callable[[str], bool]] = None) -> None:
        self._authorizer = authorizer or (lambda _command: False)

    def try_handle_command(self, transcribed_text: str) -> Optional[VoiceCommand]:
        text = " ".join(str(transcribed_text or "").lower().strip().split())
        if not text:
            return None
        if "pausar sistema" in text or "parar entradas" in text:
            command = VoiceCommand("pause", "Sistema pausado. Entradas bloqueadas.")
        elif "retomar sistema" in text or "voltar a operar" in text:
            command = VoiceCommand("resume", "Sistema retomado em modo paper-only.")
        elif "status da memória" in text or "status da memoria" in text or "status do sistema" in text:
            command = VoiceCommand("status", "Status local solicitado.", requires_confirmation=False)
        else:
            return None
        return command if self._authorizer(command.name) else None


__all__ = ["VoiceCommand", "VoiceCommandRouter"]
