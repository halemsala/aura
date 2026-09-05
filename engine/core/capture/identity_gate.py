from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from .session import CaptureSession

class CaptureRejectReason(str, Enum):
    NOT_ARMED = "NOT_ARMED"
    FOREIGN_TAB = "FOREIGN_TAB"
    FOREIGN_FIXTURE = "FOREIGN_FIXTURE"
    STALE_SESSION = "STALE_SESSION"
    STALE_EPOCH = "STALE_EPOCH"
    DUPLICATE_STATE = "DUPLICATE_STATE"

@dataclass(frozen=True)
class GateResult:
    accepted: bool
    reason: Optional[str] = None

class CaptureIdentityGate:
    @staticmethod
    def validate(payload: dict, session: Optional["CaptureSession"]) -> GateResult:
        if session is None:
            return GateResult(False, CaptureRejectReason.NOT_ARMED.value)
        if payload.get("tabId") is not None and payload.get("tabId") != session.tab_id:
            return GateResult(False, CaptureRejectReason.FOREIGN_TAB.value)
        if payload.get("fixtureId") is not None and str(payload.get("fixtureId")) != session.fixture_id:
            return GateResult(False, CaptureRejectReason.FOREIGN_FIXTURE.value)
        if payload.get("captureSessionId") is not None and payload.get("captureSessionId") != session.capture_session_id:
            return GateResult(False, CaptureRejectReason.STALE_SESSION.value)
        if payload.get("captureEpoch") is not None and payload.get("captureEpoch") != session.capture_epoch:
            return GateResult(False, CaptureRejectReason.STALE_EPOCH.value)
        return GateResult(True)
