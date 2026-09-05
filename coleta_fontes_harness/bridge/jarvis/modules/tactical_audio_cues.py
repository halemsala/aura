"""Alertas táticos inertes: registra o evento, não acessa hardware de áudio."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import List


@dataclass(frozen=True)
class AudioCue:
    event_type: str
    frequency: int
    duration_ms: int
    emitted: bool = False


class TacticalAudioOrchestrator:
    SOUND_MAP = {"ENTRA_SIGNAL": (880, 500), "RISK_BLOCK": (200, 1000), "FEED_STALE": (440, 200)}

    def __init__(self) -> None:
        self._events: List[AudioCue] = []
        self._lock = RLock()

    def play_cue(self, event_type: str) -> AudioCue | None:
        if event_type not in self.SOUND_MAP:
            return None
        frequency, duration = self.SOUND_MAP[event_type]
        cue = AudioCue(event_type, frequency, duration, emitted=False)
        with self._lock:
            self._events.append(cue)
        return cue

    def history(self) -> list[dict]:
        with self._lock:
            return [cue.__dict__.copy() for cue in self._events]


TACTICAL_AUDIO = TacticalAudioOrchestrator()
__all__ = ["TacticalAudioOrchestrator", "TACTICAL_AUDIO", "AudioCue"]
