"""Classificação local da fase de uma partida para contexto advisory."""
from __future__ import annotations


class MatchPhaseEngine:
    @staticmethod
    def get_phase(minute: int, period: str, score_diff: int) -> str:
        minute = max(0, int(minute))
        period = str(period or "").upper()
        score_diff = int(score_diff)
        if period in ("HT", "1H"):
            if minute <= 20:
                return "EARLY_PROBE"
            if 30 <= minute <= 45:
                return "PRE_INTERVAL_PUSH"
        elif period in ("ST", "2H", "FT"):
            if 45 <= minute <= 60:
                return "SECOND_HALF_SLEEP"
            if 75 <= minute <= 90:
                return "LATE_GAME_FRENZY_DRAW" if score_diff == 0 else "LATE_GAME_FRENZY_LEAD"
        return "MID_GAME_NEUTRAL"


__all__ = ["MatchPhaseEngine"]
