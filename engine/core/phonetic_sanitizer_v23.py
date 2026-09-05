# engine/core/phonetic_sanitizer_v23.py — TTS-ready text, precompiled regex
from __future__ import annotations
import re


class PhoneticSanitizerV23:
    ACRONYM_MAP = {
        "STT": "Reconhecimento de Fala",
        "TTS": "Síntese de Voz",
        "LLM": "Modelo de Inteligência",
        "GLM": "G L M",
        "API": "A P I",
        "IO": "Entrada e Saída",
        "JSON": "Jaison",
        "WAL": "U A L",
        "xG": "xis gê",
        "EV": "ê vê",
        "HOLD": "aguardar",
    }
    RE_MARKDOWN = re.compile(r"(\*{1,2}|_{1,2}|~{1,2}|`{1,3}|#{1,6}|>|\[|\]|\(|\)|\{|\})")
    RE_SPACING = re.compile(r"\s+")
    RE_ACRONYM = re.compile(r"\b([A-Za-z]{2,12})\b")
    RE_PERCENT = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%")

    def sanitize(self, text: str) -> str:
        if not text:
            return ""
        s = self.RE_MARKDOWN.sub(" ", str(text))
        s = self.RE_PERCENT.sub(lambda m: m.group(1).replace(".", ",") + " por cento", s)

        def repl(m: re.Match) -> str:
            w = m.group(1)
            if w in self.ACRONYM_MAP:
                return self.ACRONYM_MAP[w]
            if w.isupper() and 2 <= len(w) <= 4:
                return " ".join(w)
            return w

        s = self.RE_ACRONYM.sub(repl, s)
        s = self.RE_SPACING.sub(" ", s).strip()
        if s and s[-1] not in ".!?;,":
            s += "."
        return s


phonetic_sanitizer_v23 = PhoneticSanitizerV23()
