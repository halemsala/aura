# bridge/jarvis/governor/resource_governor.py
"""
Resource Governor - Dual Mode Seguro
------------------------------------
Trading Mode   → AURA ligado, Assistente Pessoal desligado
Assistant Mode → Assistente Pessoal ligado, AURA desligado

Uso:
    from bridge.jarvis.governor.resource_governor import GOVERNOR
    GOVERNOR.switch_to_assistant_mode()
    GOVERNOR.switch_to_trading_mode()
    GOVERNOR.get_status()
"""

from __future__ import annotations
import subprocess
import logging
import time
from typing import Literal
from pathlib import Path

logger = logging.getLogger("aura.governor")


class ResourceGovernor:
    def __init__(self):
        self.current_mode: Literal["trading", "assistant", "idle"] = "idle"
        # Ajuste este caminho se o AURA estiver em outra pasta
        self.aura_root = Path(r"C:\aura")

    def switch_to_assistant_mode(self) -> str:
        """Desliga o AURA de trading e libera recursos para o Assistente Pessoal."""
        if self.current_mode == "assistant":
            return "Já estou no Modo Assistente."

        logger.warning("=== Trocando para MODO ASSISTENTE ===")

        try:
            # Para processos do AURA de forma ordenada
            subprocess.run(
                ["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq *engine*"],
                capture_output=True,
                text=True
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq *bridge*"],
                capture_output=True,
                text=True
            )
            # Não matamos ollama.exe de propósito (pode ser útil no modo assistente)
        except Exception as e:
            logger.error(f"Erro ao parar serviços AURA: {e}")

        time.sleep(2)
        self.current_mode = "assistant"
        return "Modo Assistente ativado. AURA de trading foi desligado. Recursos liberados."

    def switch_to_trading_mode(self) -> str:
        """Desliga o Assistente e sobe o AURA novamente."""
        if self.current_mode == "trading":
            return "Já estou no Modo Trading."

        logger.warning("=== Trocando para MODO TRADING ===")

        # Tenta encontrar o BAT oficial do AURA
        possible_bats = [
            self.aura_root / "AURA_TUDO_EM_UM.bat",
            self.aura_root / "AURA_START_ALL.bat",
            self.aura_root / "INICIAR_SERVICOS_AURA.bat",
        ]

        bat_path = None
        for p in possible_bats:
            if p.exists():
                bat_path = p
                break

        if bat_path is None:
            return "Não encontrei o BAT de inicialização do AURA. Verifique o caminho."

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(bat_path)],
                cwd=str(self.aura_root),
                shell=True
            )
        except Exception as e:
            logger.error(f"Erro ao iniciar AURA: {e}")
            return f"Falha ao iniciar o AURA: {e}"

        self.current_mode = "trading"
        return "Modo Trading ativado. Assistente Pessoal desligado. AURA subindo..."

    def get_status(self) -> str:
        return f"Modo atual: {self.current_mode.upper()}"


# Singleton global
GOVERNOR = ResourceGovernor()
