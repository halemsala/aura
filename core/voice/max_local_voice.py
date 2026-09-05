"""
AURA QUANT-X Max Local Voice
Prioriza 100% offline: Piper (se instalado) > Edge Neural local cache > fallback.
Integra com SiliconOptimizer para respeitar margem de VRAM (porta 8099).
"""

from __future__ import annotations

import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("aura.max_local_voice")

VOICE_PORT = 8099
PREFERRED_VOICES = [
    "pt-BR-AntonioNeural",
    "pt-BR-HumbertoNeural",
    "pt-BR-FranciscaNeural",
]


class MaxLocalVoice:
    """
    Camada de preferência de voz 100% local-first.
    Não chama APIs pagas. Usa o servidor já existente em 8099
    e força preferência por Piper/offline quando disponível.
    """

    def __init__(self) -> None:
        self.port = int(os.getenv("AURA_VOICE_PORT", VOICE_PORT))
        self.prefer_piper = True
        self.piper_bin = shutil.which("piper") or shutil.which("piper.exe")
        self.edge_tts_available = shutil.which("edge-tts") is not None
        logger.info(
            "MaxLocalVoice | port=%d | piper=%s | edge-tts=%s",
            self.port, bool(self.piper_bin), self.edge_tts_available
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "port": self.port,
            "piper_installed": bool(self.piper_bin),
            "edge_tts_cli": self.edge_tts_available,
            "prefer_local": True,
            "recommended_voice": PREFERRED_VOICES[0],
            "health_url": f"http://127.0.0.1:{self.port}/api/voice/health",
            "talk_url": f"http://127.0.0.1:{self.port}/api/voice/talk",
            "note": "Servidor de voz já existente (jarvis_voice_server.py). Esta camada só força preferência local e documenta o caminho MAX POWER.",
        }

    def ensure_local_env(self) -> Dict[str, str]:
        """Retorna env vars recomendadas para subir a voz com máximo local."""
        env = {
            "AURA_VOICE_PREFER_LOCAL": "1",
            "AURA_VOICE_PORT": str(self.port),
            "AURA_TTS_VOICE": PREFERRED_VOICES[0],
            "AURA_TTS_RATE": "-6%",
            "AURA_TTS_PITCH": "-4Hz",
            "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "0"),
        }
        if self.piper_bin:
            env["AURA_PIPER_BIN"] = self.piper_bin
            env["AURA_TTS_ENGINE"] = "piper"
        else:
            env["AURA_TTS_ENGINE"] = "edge_neural_or_cache"
        return env

    def print_start_instructions(self) -> str:
        lines = [
            "=== VOZ MAX LOCAL (custo zero) ===",
            f"1. Porta: {self.port}",
            "2. Subir servidor: python bridge/jarvis_voice_server.py --port 8099",
            "   ou: bridge/iniciar_voz.sh / iniciar_voz.bat",
            "3. Preferência: Piper (offline) > Edge Neural (cache) > gTTS",
            "4. Health: curl http://127.0.0.1:8099/api/voice/health",
            "5. SiliconOptimizer já reserva 15% VRAM para este serviço.",
        ]
        if self.piper_bin:
            lines.append(f"6. Piper detectado: {self.piper_bin}")
        else:
            lines.append("6. Piper não detectado — use INSTALAR_PIPER_PTBR.bat/.sh para voz 100% offline.")
        return "\n".join(lines)


def get_max_local_voice() -> MaxLocalVoice:
    return MaxLocalVoice()
