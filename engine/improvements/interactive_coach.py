# -*- coding: utf-8 -*-
"""
Interactive Coach — v12.8.0
Aumenta interatividade: gera perguntas de follow-up inteligentes,
pede feedback do usuário sobre análises, e ajusta confiança/estilos.
Integra com voz (Jarvis) e UI central.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class UserFeedback:
    fixture_id: str
    analysis_id: str
    user_rating: float  # 0.0–1.0
    correction: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class InteractionState:
    last_analysis: Optional[Dict[str, Any]] = None
    pending_questions: List[str] = field(default_factory=list)
    feedback_history: deque = field(default_factory=lambda: deque(maxlen=50))
    engagement_score: float = 0.5  # 0–1, sobe com feedback e follow-ups respondidos
    style: str = "tecnico"  # tecnico | didatico | agressivo | calm


class InteractiveCoach:
    """
    Gera interatividade proativa e feedback loop para aumentar
    precisão percebida e engajamento do usuário.
    """

    def __init__(self):
        self.state = InteractionState()
        self._calibration: Dict[str, float] = {}  # fixture_type -> bias

    def on_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Chamado após cada análise. Retorna pacote interativo."""
        self.state.last_analysis = analysis
        questions = self._generate_followups(analysis)
        self.state.pending_questions = questions
        self.state.engagement_score = min(1.0, self.state.engagement_score + 0.02)

        return {
            "followup_questions": questions,
            "suggested_style": self.state.style,
            "engagement": round(self.state.engagement_score, 3),
            "proactive_alert": self._maybe_proactive(analysis),
            "explanation_boost": self._rich_explanation(analysis),
        }

    def record_feedback(self, feedback: UserFeedback) -> Dict[str, Any]:
        self.state.feedback_history.append(feedback)
        self.state.engagement_score = min(1.0, self.state.engagement_score + 0.08)
        # Ajuste de calibração simples
        key = feedback.fixture_id[:8] if feedback.fixture_id else "global"
        prev = self._calibration.get(key, 0.0)
        delta = (feedback.user_rating - 0.5) * 0.1
        self._calibration[key] = max(-0.15, min(0.15, prev + delta))
        return {
            "accepted": True,
            "new_engagement": self.state.engagement_score,
            "calibration": self._calibration.get(key, 0.0),
        }

    def get_voice_prompt_addon(self) -> str:
        """Texto extra para o system prompt do Jarvis conforme engajamento."""
        eng = self.state.engagement_score
        if eng > 0.75:
            return (
                "Usuário altamente engajado. Ofereça 1 follow-up proativo por resposta. "
                "Pergunte se quer cenário what-if ou detalhe de feature."
            )
        if eng < 0.3:
            return (
                "Usuário pouco interativo. Respostas ainda mais curtas. "
                "Só faça pergunta se o risco for alto ou dados incompletos."
            )
        return "Mantenha tom técnico e ofereça 1 pergunta de clarificação quando útil."

    def _generate_followups(self, analysis: Dict[str, Any]) -> List[str]:
        qs: List[str] = []
        conf = float(analysis.get("confidence") or analysis.get("score") or 50) / 100.0
        edge = float(analysis.get("edge") or 0)
        veracity = float(analysis.get("veracity") or analysis.get("data_quality") or 0.7)

        if conf < 0.55:
            qs.append("Quer que eu detalhe por que a confiança está baixa neste momento?")
        if abs(edge) > 0.08:
            qs.append("Quer um cenário what-if se a pressão mudar 20% nos próximos 5 min?")
        if veracity < 0.65:
            qs.append("Os dados de captura parecem incompletos. Quer que eu force um refresh do HUD?")
        if not qs:
            qs.append("Posso explicar a confluência dos sinais em 2 frases?")
        return qs[:2]  # max 2 para não sobrecarregar

    def _maybe_proactive(self, analysis: Dict[str, Any]) -> Optional[str]:
        risk = analysis.get("risk_gate") or {}
        if risk.get("blocked"):
            return f"Alerta: gate de risco bloqueou. Motivo: {risk.get('reason', 'desconhecido')}"
        conf = float(analysis.get("confidence") or 50)
        if conf >= 78 and analysis.get("signal") in ("BUY_CORNER", "STRONG_BUY"):
            return "Sinal forte detectado. Quer que eu prepare o card de explicação completo?"
        return None

    def _rich_explanation(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Gera estrutura rica para UI/voz."""
        return {
            "headline": analysis.get("signal", "NEUTRO"),
            "key_drivers": [
                f"Prob modelo: {analysis.get('corner_prob', 'N/A')}",
                f"Edge: {analysis.get('edge', 'N/A')}",
                f"Veracidade: {analysis.get('veracity', analysis.get('data_quality', 'N/A'))}",
            ],
            "next_check_in_sec": 45 if float(analysis.get("confidence") or 50) > 60 else 90,
        }

    def adapt_style(self, preferred: str) -> None:
        if preferred in ("tecnico", "didatico", "agressivo", "calm"):
            self.state.style = preferred


# Singleton leve para o engine
_coach: Optional[InteractiveCoach] = None


def get_coach() -> InteractiveCoach:
    global _coach
    if _coach is None:
        _coach = InteractiveCoach()
    return _coach
