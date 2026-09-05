from __future__ import annotations
import re
from typing import Dict, Pattern


class PhoneticSanitizer:
    LEXICON: Dict[str, str] = {
        r"\bxG\b": "expected goals",
        r"\bAP\b": "ataques perigosos",
        r"\bCPI\b": "indice de pressao ofensiva",
        r"\bW1\b": "janela um",
        r"\bW2\b": "janela dois",
        r"\bIMC\b": "indice de momentum de cantos",
        r"\bGLM\b": "modelo local",
        r"\bREG\b": "registro",
        r"\bBUY\b": "entrada paper",
        r"\bHOLD\b": "aguarda",
        r"\bNO_BET\b": "nao entra",
        r"\bROI\b": "retorno sobre investimento",
    }
    MARKDOWN_PATTERN: Pattern = re.compile(r"[*_`\[\]\(\)\|#>\-]+")
    EMOJI_PATTERN: Pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "]+"
    )
    DECIMAL_PATTERN: Pattern = re.compile(r"\d+\.\d{3,}")

    @classmethod
    def clean(cls, text: str) -> str:
        text = cls.MARKDOWN_PATTERN.sub(" ", text or "")
        text = cls.EMOJI_PATTERN.sub("", text)
        text = cls.DECIMAL_PATTERN.sub(lambda m: f"{float(m.group()):.2f}", text)
        for pattern, replacement in cls.LEXICON.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        if len(words) > 25:
            text = " ".join(words[:25]) + ". Dados completos no painel."
        return text


phonetic_sanitizer = PhoneticSanitizer()
