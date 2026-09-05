"""AURA QUANT-X v12.7.7 — porteiro de veracidade do feed."""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("aura.data_veracity")


class DataVeracityGate:
    """Filtra snapshots impossíveis por fixture e mantém o último estado válido."""

    def __init__(self) -> None:
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.accepted = 0
        self.rejected = 0

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _fixture_key(data: Dict[str, Any]) -> str:
        return str(
            data.get("fixture_id")
            or data.get("fixtureId")
            or data.get("match_id")
            or data.get("matchId")
            or "__default__"
        )

    def sanitize(self, incoming_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(incoming_data, dict) or not incoming_data:
            self.rejected += 1
            return None
        fixture_key = self._fixture_key(incoming_data)
        minute = self._number(incoming_data.get("minute"), 0.0)
        corners = self._number(
            incoming_data.get("corners_total", incoming_data.get("corners", 0)), 0.0
        )
        score = incoming_data.get("score", "0-0")
        with self._lock:
            previous = self._states.get(fixture_key, {})
            last_minute = self._number(previous.get("minute"), 0.0)
            last_corners = self._number(previous.get("corners_total"), 0.0)
            if minute < last_minute and last_minute <= 45:
                self.rejected += 1
                logger.warning("Dado rejeitado: minuto regrediu (%s < %s).", minute, last_minute)
                return None
            if corners < last_corners:
                self.rejected += 1
                logger.warning("Dado rejeitado: escanteios regrediram (%s < %s).", corners, last_corners)
                return None
            if isinstance(score, str) and "-" in score:
                try:
                    home, away = (int(part.strip()) for part in score.split("-", 1))
                    if home < 0 or away < 0:
                        self.rejected += 1
                        logger.warning("Dado rejeitado: placar negativo detectado.")
                        return None
                except ValueError:
                    self.rejected += 1
                    logger.warning("Dado rejeitado: placar inválido (%r).", score)
                    return None
            clean = dict(incoming_data)
            clean["_veracity_fixture"] = fixture_key
            clean["_veracity_accepted"] = True
            clean["_veracity_previous"] = dict(previous) if previous else None
            self._states[fixture_key] = dict(clean)
            self.accepted += 1
            return clean

    def last_valid_state(self, fixture_id: str = "__default__") -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._states.get(str(fixture_id))
            return dict(state) if state else None

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "fixtures_tracked": len(self._states),
                "accepted": self.accepted,
                "rejected": self.rejected,
            }


VERACITY_GATE = DataVeracityGate()

__all__ = ["DataVeracityGate", "VERACITY_GATE"]
