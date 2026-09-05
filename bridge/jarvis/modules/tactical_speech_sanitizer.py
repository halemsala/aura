# bridge/jarvis/modules/tactical_speech_sanitizer.py — Radical 3.1
from __future__ import annotations
import re


class TacticalSpeechSanitizer:
    __slots__ = ("_entity_map", "_num_pattern")

    def __init__(self) -> None:
        self._entity_map = {
            "xG": "gols esperados",
            "EV+": "valor esperado positivo",
            "EV-": "valor esperado negativo",
            "BUY_CORNER": "sinal de compra de escanteio",
            "WATCH_CORNER": "monitorar escanteios",
            "BLOCKED_BY_DATA": "bloqueado por falta de dados",
            "BLOCKED_BY_MARKET": "bloqueado pelo mercado",
            "APPM": "ataques perigosos por minuto",
            "HT": "primeiro tempo",
            "FT": "segundo tempo",
            "WoM": "peso do dinheiro",
            "HOLD": "aguardar",
        }
        self._num_pattern = re.compile(r"(\d+)[.,](\d+)")

    def sanitize(self, text: str) -> str:
        text = re.sub(r"[#*_`\[\]{}|]", "", text or "")
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        for token, expansion in self._entity_map.items():
            text = text.replace(token, expansion)
        def _verbalize(m):
            return f"{m.group(1)} vírgula {m.group(2)}"
        text = self._num_pattern.sub(_verbalize, text)
        text = re.sub(r"(\d+)\s*%", r"\1 por cento", text)
        return " ".join(text.split())

    def to_ssml(self, text: str, rate: float = 1.05, pitch: float = 0.88) -> str:
        clean = self.sanitize(text)
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">'
            f'<voice name="pt-BR-AntonioNeural">'
            f'<prosody rate="{rate:.2f}" pitch="{pitch:.0%}">{clean}</prosody>'
            f"</voice></speak>"
        )
