# engine/core/delta_compressor_v23.py — dense semantic delta for LLM payloads
from __future__ import annotations
from typing import Any


class DeltaCompressorV23:
    KEY_MAP = {
        "minute": "MIN",
        "score_home": "SC_H",
        "score_away": "SC_A",
        "score": "SC",
        "attacks": "ATK",
        "dangerous_attacks": "DNG",
        "dangerous": "DNG",
        "corners": "COR",
        "pressure": "PRS",
        "possession": "POS",
        "xg": "XG",
        "xG": "XG",
        "decision": "DEC",
        "odds_velocity": "OV",
    }

    def __init__(self) -> None:
        self._last_states: dict[str, dict] = {}

    def compress(self, fixture_id: str, current_state: dict[str, Any]) -> str:
        if not isinstance(current_state, dict):
            return ""
        last = self._last_states.get(fixture_id, {})
        delta_parts: list[str] = []
        base_parts: list[str] = []
        for k, v in current_state.items():
            if v is None:
                continue
            abbr = self.KEY_MAP.get(k, str(k).upper()[:3])
            if isinstance(v, float):
                v = round(v, 4)
            if k in last:
                if last[k] != v:
                    delta_parts.append(f"D_{abbr}={v}")
            else:
                base_parts.append(f"B_{abbr}={v}")
        self._last_states[fixture_id] = dict(current_state)
        return "||".join(["|".join(base_parts), "|".join(delta_parts)])

    def build_llm_payload(self, fixture_id: str, deltas_history: list[str], max_deltas: int = 20) -> str:
        windowed = deltas_history[-max_deltas:]
        return f"FIXTURE:{fixture_id}\nTIMELINE:\n" + "\n".join(windowed)


delta_compressor_v23 = DeltaCompressorV23()
