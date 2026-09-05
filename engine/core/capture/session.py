from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from threading import RLock
from time import time_ns
from typing import Optional
from uuid import uuid4

class CapturePhase(str, Enum):
    IDLE = "IDLE"
    ARMING = "ARMING"
    ACTIVE = "ACTIVE"
    SWITCHING = "SWITCHING"
    INVALIDATED = "INVALIDATED"
    DISARMED = "DISARMED"

@dataclass(frozen=True)
class CaptureSession:
    capture_session_id: str
    capture_epoch: int
    tab_id: int
    fixture_id: str
    url: str
    phase: CapturePhase
    state_version: int
    armed_at_ns: int

class CaptureSessionManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._session: Optional[CaptureSession] = None
        self._epoch = 0

    def arm(self, *, tab_id: int, fixture_id: str, url: str = "") -> CaptureSession:
        if not isinstance(tab_id, int):
            raise ValueError("tab_id invalido")
        if not fixture_id:
            raise ValueError("fixture_id obrigatorio")
        with self._lock:
            self._epoch += 1
            session = CaptureSession(
                capture_session_id=str(uuid4()),
                capture_epoch=self._epoch,
                tab_id=tab_id,
                fixture_id=str(fixture_id),
                url=url or "",
                phase=CapturePhase.ARMING,
                state_version=0,
                armed_at_ns=time_ns(),
            )
            self._session = replace(session, phase=CapturePhase.ACTIVE)
            return self._session

    def get_active(self) -> Optional[CaptureSession]:
        with self._lock:
            if self._session is None or self._session.phase is not CapturePhase.ACTIVE:
                return None
            return self._session

    def disarm(self) -> None:
        with self._lock:
            if self._session is None:
                return
            self._session = replace(self._session, phase=CapturePhase.DISARMED)

    def next_state_version(self) -> CaptureSession:
        with self._lock:
            if self._session is None:
                raise RuntimeError("CAPTURE_NOT_ARMED")
            if self._session.phase is not CapturePhase.ACTIVE:
                raise RuntimeError("CAPTURE_NOT_ACTIVE")
            self._session = replace(self._session, state_version=self._session.state_version + 1)
            return self._session

capture_session_manager = CaptureSessionManager()
