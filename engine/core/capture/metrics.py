from __future__ import annotations
from dataclasses import dataclass

@dataclass
class CaptureMetrics:
    received: int = 0
    accepted: int = 0
    foreign_tab: int = 0
    foreign_fixture: int = 0
    stale_session: int = 0
    stale_epoch: int = 0
    duplicate_state: int = 0
    duplicate_event: int = 0
    engine_processed: int = 0
    persisted: int = 0
    failures: int = 0

    def snapshot(self) -> dict:
        return {
            "received": self.received, "accepted": self.accepted,
            "rejected": {
                "foreignTab": self.foreign_tab, "foreignFixture": self.foreign_fixture,
                "staleSession": self.stale_session, "staleEpoch": self.stale_epoch,
                "duplicateState": self.duplicate_state, "duplicateEvent": self.duplicate_event,
            },
            "engineProcessed": self.engine_processed, "persisted": self.persisted, "failures": self.failures,
            "paper_trade": True, "execution_allowed": False,
        }

capture_metrics = CaptureMetrics()
