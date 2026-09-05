"""P2 Fase 6 — Prosody planner, SSML seguro, fila de voz, dicionário pt-BR.

Regras:
- Escapar XML antes de SSML
- Não usar 'Hmm' como respiração
- Perfis de voz / pausas
- Fila cancelável (barge-in)
"""
from __future__ import annotations

import re
import time
import uuid
import xml.sax.saxutils
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Dicionário de pronúncia pt-BR (substituições simples antes do TTS)
PRONUNCIATION_PTBR: Dict[str, str] = {
    "xG": "equis gue",
    "xg": "equis gue",
    "dDA/dt": "derivada de ataques perigosos",
    "BUY_CORNER": "compra de escanteio",
    "WATCH_CORNER": "observar escanteio",
    "BLOCKED_BY_DATA": "bloqueado por dados",
    "BLOCKED_BY_RISK": "bloqueado por risco",
    "BLOCKED_BY_MARKET": "bloqueado por mercado",
    "BLOCKED_BY_LEDGER": "bloqueado por ledger",
    "BLOCKED_BY_MODEL": "bloqueado por modelo",
    "fixture": "partida",
    "Kelly": "kélí",
    "edge": "vantagem",
    "odds": "odds",
    "WoM": "peso do dinheiro",
}

VOICE_PROFILES: Dict[str, Dict[str, str]] = {
    "neutral": {"rate": "-4%", "pitch": "-2Hz", "style": "general"},
    "risk_guard": {"rate": "-10%", "pitch": "-6Hz", "style": "serious"},
    "alert_focus": {"rate": "-2%", "pitch": "-1Hz", "style": "alert"},
    "watch_calm": {"rate": "-6%", "pitch": "-3Hz", "style": "calm"},
}


def escape_xml(text: str) -> str:
    return xml.sax.saxutils.escape(str(text or ""), {"'": "&apos;", '"': "&quot;"})


def apply_pronunciation(text: str) -> str:
    out = str(text or "")
    # longer keys first
    for src in sorted(PRONUNCIATION_PTBR.keys(), key=len, reverse=True):
        out = out.replace(src, PRONUNCIATION_PTBR[src])
    return out


def strip_forbidden_fillers(text: str) -> str:
    """Remove fillers proibidos, markdown e símbolos que o TTS lê em voz alta."""
    out = str(text or "")
    out = re.sub(r"\b[Hh]m+\b", "", out)
    # Remove asteriscos, markdown e símbolos
    out = re.sub(r"[*_`#~|>\\]", "", out)
    out = re.sub(r"\[[^\]]+\]", "", out)
    # Percentuais -> "N por cento" arredondado
    def _pct(m):
        raw = m.group(1).replace(",", ".")
        try:
            n = float(raw)
        except Exception:
            return m.group(0)
        pct = n * 100.0 if n <= 1.0 and not m.group(1).startswith(("1", "2", "3", "4", "5", "6", "7", "8", "9")) else n
        return f"{int(round(pct))} por cento"
    out = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", _pct, out)
    # Arredonda decimais longos para fala natural
    def _num(m):
        raw = (m.group(1) + "." + m.group(2)).replace(",", ".")
        try:
            n = float(raw)
        except Exception:
            return m.group(0)
        if abs(n) >= 100:
            s = str(int(round(n)))
        elif abs(n) >= 10:
            s = f"{round(n, 1):.1f}".rstrip("0").rstrip(".")
        else:
            s = f"{round(n, 2):.2f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    out = re.sub(r"(-?\d+)[.,](\d{3,})", _num, out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def plan_segments(text: str, *, max_len: int = 280) -> List[str]:
    clean = strip_forbidden_fillers(apply_pronunciation(text))
    if not clean:
        return []
    parts: List[str] = []
    buf = ""
    for piece in re.split(r"(?<=[\.\!\?;:])\s+", clean):
        if not piece:
            continue
        if len(buf) + len(piece) + 1 <= max_len:
            buf = (buf + " " + piece).strip()
        else:
            if buf:
                parts.append(buf)
            buf = piece if len(piece) <= max_len else piece[:max_len]
    if buf:
        parts.append(buf)
    return parts


def build_ssml(text: str, *, profile: str = "neutral", pause_ms: int = 200) -> str:
    """Gera SSML seguro (XML escapado). Tags por planner, não por replace cego de vírgulas."""
    prof = VOICE_PROFILES.get(profile) or VOICE_PROFILES["neutral"]
    segments = plan_segments(text)
    body_parts = []
    for i, seg in enumerate(segments):
        body_parts.append(escape_xml(seg))
        if i < len(segments) - 1 and pause_ms > 0:
            body_parts.append(f'<break time="{int(pause_ms)}ms"/>')
    body = " ".join(body_parts)
    # Edge neural often accepts plain prosody wrapper
    ssml = (
        f'<speak version="1.0" xml:lang="pt-BR">'
        f'<prosody rate="{prof["rate"]}" pitch="{prof["pitch"]}">'
        f"{body}"
        f"</prosody></speak>"
    )
    return ssml


def narrative_from_card(card: Dict[str, Any]) -> str:
    """Narrativa determinística (sem LLM) a partir do cartão — fallback seguro."""
    action = str(card.get("action") or "HOLD")
    clock = card.get("match_clock") or ""
    score = card.get("score") or ""
    reasons = card.get("reason_codes") or []
    p = card.get("p_calibrated")

    bits = []
    if clock:
        bits.append(f"Minuto {clock}.")
    if score:
        bits.append(f"Placar {score}.")
    if action.startswith("BLOCKED"):
        bits.append(f"Decisão: bloqueado ({action}).")
        if reasons:
            bits.append("Motivos: " + ", ".join(str(r) for r in reasons[:4]) + ".")
    elif action.startswith("BUY"):
        bits.append("Sinal preliminar de escanteio.")
        if p is not None:
            bits.append(f"Probabilidade calibrada cerca de {float(p)*100:.0f} por cento.")
        bits.append("Kelly desligado. Sem stake real.")
    elif action.startswith("WATCH"):
        bits.append("Modo observação de escanteio.")
        if p is not None:
            bits.append(f"Probabilidade cerca de {float(p)*100:.0f} por cento.")
    else:
        bits.append("Sem entrada operacional.")
    if not card.get("humor_allowed", True):
        # ensure serious tone, no joke suffix
        pass
    return " ".join(bits)


@dataclass
class VoiceJob:
    job_id: str
    text: str
    ssml: str
    profile: str
    created_at: float
    cancelled: bool = False
    status: str = "queued"  # queued|speaking|done|cancelled


class VoiceQueue:
    """Fila simples cancelável para barge-in."""

    def __init__(self) -> None:
        self._jobs: List[VoiceJob] = []
        self._current: Optional[VoiceJob] = None

    def enqueue(self, text: str, *, profile: str = "neutral") -> VoiceJob:
        ssml = build_ssml(text, profile=profile)
        job = VoiceJob(
            job_id=f"vj_{uuid.uuid4().hex[:10]}",
            text=text,
            ssml=ssml,
            profile=profile,
            created_at=time.time(),
        )
        self._jobs.append(job)
        return job

    def cancel_all(self) -> int:
        n = 0
        for j in self._jobs:
            if j.status in ("queued", "speaking"):
                j.cancelled = True
                j.status = "cancelled"
                n += 1
        if self._current and self._current.status == "speaking":
            self._current.cancelled = True
            self._current.status = "cancelled"
            n += 1
        self._jobs = [j for j in self._jobs if j.status == "queued" and not j.cancelled]
        return n

    def barge_in(self, text: str, *, profile: str = "neutral") -> VoiceJob:
        """Cancela fala atual e enfileira nova (barge-in real, não boolean no lugar de áudio)."""
        self.cancel_all()
        return self.enqueue(text, profile=profile)

    def pop_next(self) -> Optional[VoiceJob]:
        while self._jobs:
            j = self._jobs.pop(0)
            if not j.cancelled and j.status == "queued":
                j.status = "speaking"
                self._current = j
                return j
        return None

    def mark_done(self, job_id: str) -> None:
        if self._current and self._current.job_id == job_id:
            self._current.status = "done"
            self._current = None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "queued": len([j for j in self._jobs if j.status == "queued"]),
            "current": self._current.job_id if self._current else None,
            "current_status": self._current.status if self._current else None,
        }


VOICE_QUEUE = VoiceQueue()
