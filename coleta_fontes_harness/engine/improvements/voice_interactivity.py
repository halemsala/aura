# -*- coding: utf-8 -*-
"""
Voice Interactivity Enhancer — v12.8.0
Melhora a conversa com o usuário via Jarvis:
- Contexto de jogo persistente
- Geração de perguntas proativas
- Limpeza e priorização de respostas
- Detecção de intenção de follow-up
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional


INTENT_PATTERNS = {
    "what_if": re.compile(r"(e se|what.?if|cenário|scenario|simula|muda(r)? a pressão)", re.I),
    "explain": re.compile(r"(explica|por que|porque|detalha|como chegou|motivo)", re.I),
    "status": re.compile(r"(status|como está|atual|agora|resumo)", re.I),
    "risk": re.compile(r"(risco|gate|bloqueio|kelly|stake)", re.I),
    "feedback": re.compile(r"(errado|correto|gostei|não gostei|feedback|ajustar)", re.I),
    "refresh": re.compile(r"(atualiza|refresh|recarrega|força captura)", re.I),
}


def detect_intent(user_text: str) -> str:
    text = (user_text or "").strip()
    for name, pat in INTENT_PATTERNS.items():
        if pat.search(text):
            return name
    return "general"


def build_voice_response_package(
    analysis: Dict[str, Any],
    user_text: str = "",
    coach_addon: str = "",
) -> Dict[str, Any]:
    """
    Monta pacote pronto para TTS + UI.
    Respostas curtas, com 1 pergunta opcional.
    """
    intent = detect_intent(user_text)
    signal = analysis.get("signal") or analysis.get("recommended_action") or "NEUTRO"
    conf = analysis.get("confidence") or analysis.get("score") or 50
    edge = analysis.get("edge")
    veracity = analysis.get("veracity") or analysis.get("data_quality")

    # Headline curta
    if signal in ("BUY_CORNER", "STRONG_BUY"):
        headline = f"Sinal favorável a canto. Confiança {conf:.0f}."
    elif signal in ("AVOID", "SELL"):
        headline = f"Evitar entrada. Confiança {conf:.0f}."
    else:
        headline = f"Neutro / aguardar. Confiança {conf:.0f}."

    details = []
    if edge is not None:
        details.append(f"Edge {float(edge):+.3f}")
    if veracity is not None:
        details.append(f"Dados {float(veracity)*100:.0f}%")

    body = headline
    if details:
        body += " " + " · ".join(details) + "."

    # Follow-up conforme intenção
    followup = None
    if intent == "what_if":
        followup = "Quer variação de +20% de pressão ou de odds caindo 5%?"
    elif intent == "explain":
        followup = "Prefere o detalhe do Hawkes ou da confluência com o mercado?"
    elif intent == "risk":
        followup = "Quer ver o motivo exato do último gate?"
    elif intent == "feedback":
        followup = "Avalie de 1 a 5 a última análise que eu registrei."
    else:
        # proativo leve
        if float(conf) >= 70:
            followup = "Quer o card completo ou só o próximo checkpoint?"

    return {
        "tts_text": body + ((" " + followup) if followup else ""),
        "ui_headline": headline,
        "ui_details": details,
        "intent": intent,
        "followup": followup,
        "coach_addon": coach_addon,
        "timestamp": time.time(),
        "version": "12.8.0-voice-interactivity",
    }


def sanitize_for_tts(text: str) -> str:
    """Remove artefatos que atrapalham TTS (números longos, * etc)."""
    if not text:
        return ""
    t = re.sub(r"\*+", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    # Evita ler IDs longos
    t = re.sub(r"\b[0-9a-f]{8,}\b", "id", t, flags=re.I)
    return t[:420]  # limite seguro para frase única
