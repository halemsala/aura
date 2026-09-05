# engine/core/voice/speech_sanitizer.py — P1 Ultra pt-BR
from __future__ import annotations
import re

class SpeechSanitizer:
    _markdown = re.compile(r"(\*\*|__|`{1,3}|#{1,6}\s*|>\s*|\[[^\]]*\]\([^)]+\))")
    _whitespace = re.compile(r"\s+")
    _pipes = re.compile(r"[|~]+")
    _timestamp = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
    _percent = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
    _decimal = re.compile(r"(?<=\s)(\d+)\.(\d+)(?=\s|[.,;!?]|$)")
    _lexicon = {
        "O1.5": "mais de um e meio", "O2.5": "mais de dois e meio",
        "LSE": "linha superior de escanteios", "ESC": "escanteios",
        "ODD": "cotacao", "COMBO": "combinacao", "INF": "inferior", "SUP": "superior",
        "W1": "janela um", "W2": "janela dois", "IMC": "indice de momentum de cantos",
        "xG": "expected goals", "GLM": "modelo local", "BUY": "entrada paper",
        "HOLD": "aguarda", "NO_BET": "nao entra",
    }

    def sanitize(self, text: str) -> str:
        text = self._markdown.sub(" ", text or "")
        text = self._pipes.sub(" ", text)
        text = self._timestamp.sub(" ", text)
        text = self._percent.sub(lambda m: m.group(1).replace(".", ",") + " por cento", text)
        text = self._decimal.sub(r"\1,\2", text)
        for ch in "{}[]()":
            text = text.replace(ch, " ")
        for pat, rep in sorted(self._lexicon.items(), key=lambda kv: -len(kv[0])):
            text = re.sub(rf"\b{re.escape(pat)}\b", rep, text, flags=re.IGNORECASE)
        for sigla in ("STT", "TTS", "LLM", "API"):
            text = re.sub(rf"\b{sigla}\b", " ".join(sigla), text)
        return self._whitespace.sub(" ", text).strip()


TOKEN_MAP = {
    "BUY_CORNER": "entrada em escanteios",
    "NO_BET": "sem entrada",
    "PREPARE": "preparar",
    "OBSERVE": "observar",
    "HOLD": "aguardar",
    "xG": "x g",
    "EV": "valor esperado",
    "APPM": "ataques perigosos por minuto",
    "WOM": "peso de mercado",
}

def sanitize_for_speech(text: str) -> str:
    import re
    text = str(text or "")
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_>#~]", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    for token, spoken in TOKEN_MAP.items():
        text = re.sub(rf"\b{re.escape(token)}\b", spoken, text, flags=re.I)
    text = text.replace("≥", " maior ou igual a ")
    text = text.replace("≤", " menor ou igual a ")
    text = text.replace("→", " depois ")
    text = text.replace("%", " por cento ")
    text = text.replace("×", " vezes ")
    text = re.sub(r"[\[\]{}()<>|#*_+=~^]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
