"""Sanitização local e gate de wake-word para comandos advisory."""
from __future__ import annotations

import re
import unicodedata


class PhoneticSanitizer:
    @staticmethod
    def normalize(text: str) -> str:
        value = unicodedata.normalize("NFKD", str(text or ""))
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(re.sub(r"[^a-zA-Z0-9 ]+", " ", value).lower().split())


class WakeWordGatekeeper:
    WAKE_WORDS = ("aura", "sistema", "jarvis")

    def check_activation(self, transcribed_text: str) -> bool:
        normalized = PhoneticSanitizer.normalize(transcribed_text)
        return any(word in normalized.split() for word in self.WAKE_WORDS)


WAKE_KEEPER = WakeWordGatekeeper()
__all__ = ["PhoneticSanitizer", "WakeWordGatekeeper", "WAKE_KEEPER"]
