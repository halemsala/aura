from __future__ import annotations
from typing import Optional
from .session import CaptureSessionManager, capture_session_manager
from .identity_gate import CaptureIdentityGate
from .deduplicator import StateDeduplicator, state_deduplicator
from .fixture_state import FixtureStateStore, fixture_state_store
from .hashes import build_state_hash
from .metrics import CaptureMetrics, capture_metrics

def normalize_payload(payload: dict) -> dict:
    state = payload.get("state")
    if state is None and isinstance(payload.get("view"), dict):
        state = payload["view"]
    if state is None and isinstance(payload.get("snapshot"), dict):
        state = payload["snapshot"]
    if not isinstance(state, dict):
        state = {k: v for k, v in payload.items() if k not in ("captureSessionId", "captureEpoch", "tabId")}
    fid = payload.get("fixtureId") or payload.get("fixture_id") or state.get("fixtureId") or ""
    return {"fixtureId": str(fid), "capturedAt": payload.get("capturedAt") or payload.get("captured_at"), "state": state}

class CapturePipeline:
    def __init__(self, session_manager=None, identity_gate=None, deduplicator=None, state_store=None, metrics=None, artifact_worker=None):
        self.session_manager = session_manager or capture_session_manager
        self.identity_gate = identity_gate or CaptureIdentityGate()
        self.deduplicator = deduplicator or state_deduplicator
        self.state_store = state_store or fixture_state_store
        self.metrics = metrics or capture_metrics
        self.artifact_worker = artifact_worker

    def ingest(self, payload: dict) -> dict:
        self.metrics.received += 1
        session = self.session_manager.get_active()
        if session is None:
            normalized = normalize_payload(payload)
            fid = normalized["fixtureId"] or "unknown"
            sh = build_state_hash(normalized["state"])
            if not self.deduplicator.accept(fid, sh):
                self.metrics.duplicate_state += 1
                return {"accepted": False, "reason": "DUPLICATE_STATE", "paper_trade": True, "execution_allowed": False}
            state = self.state_store.put(fid, 0, sh, normalized)
            self.metrics.accepted += 1
            return {"accepted": True, "fixtureId": state.fixture_id, "stateVersion": 0, "stateHash": sh, "mode": "NO_SESSION", "paper_trade": True, "execution_allowed": False}

        gate = self.identity_gate.validate(payload, session)
        if not gate.accepted:
            reason = gate.reason or "REJECTED"
            if reason == "FOREIGN_TAB": self.metrics.foreign_tab += 1
            elif reason == "FOREIGN_FIXTURE": self.metrics.foreign_fixture += 1
            elif reason == "STALE_SESSION": self.metrics.stale_session += 1
            elif reason == "STALE_EPOCH": self.metrics.stale_epoch += 1
            return {"accepted": False, "reason": reason, "event_diag": {"capture_session_id": session.capture_session_id, "fixture_id": session.fixture_id, "stage": "CaptureIdentityGate", "accepted": False, "reason": reason, "persisted": False, "engine_processed": False, "state_version": session.state_version}, "paper_trade": True, "execution_allowed": False}

        normalized = normalize_payload(payload)
        sh = build_state_hash(normalized["state"])
        if not self.deduplicator.accept(session.fixture_id, sh):
            self.metrics.duplicate_state += 1
            return {"accepted": False, "reason": "DUPLICATE_STATE", "stateVersion": session.state_version, "event_diag": {"stage": "StateDeduplicator", "accepted": False, "reason": "DUPLICATE_STATE", "fixture_id": session.fixture_id, "state_version": session.state_version, "persisted": False, "engine_processed": False}, "paper_trade": True, "execution_allowed": False}

        session = self.session_manager.next_state_version()
        state = self.state_store.put(session.fixture_id, session.state_version, sh, normalized)
        if self.artifact_worker is not None:
            try:
                self.artifact_worker.submit({"type": "STATE_ACCEPTED", "fixture_id": state.fixture_id, "version": state.version})
            except Exception:
                pass
        self.metrics.accepted += 1
        return {"accepted": True, "fixtureId": state.fixture_id, "stateVersion": state.version, "stateHash": sh, "paper_trade": True, "execution_allowed": False}

capture_pipeline = CapturePipeline()
