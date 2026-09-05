from engine.core.capture.session import CaptureSessionManager
from engine.core.capture.identity_gate import CaptureIdentityGate
from engine.core.capture.deduplicator import StateDeduplicator

def test_old_session_is_rejected():
    manager = CaptureSessionManager()
    first = manager.arm(tab_id=10, fixture_id="A", url="https://example/game/A")
    second = manager.arm(tab_id=10, fixture_id="B", url="https://example/game/B")
    payload = {"tabId": 10, "fixtureId": "A", "captureSessionId": first.capture_session_id, "captureEpoch": first.capture_epoch, "state": {}}
    result = CaptureIdentityGate.validate(payload, second)
    assert result.accepted is False

def test_duplicate_state_is_rejected():
    dedupe = StateDeduplicator()
    assert dedupe.accept("A", "hash1") is True
    assert dedupe.accept("A", "hash1") is False

if __name__ == "__main__":
    test_old_session_is_rejected()
    test_duplicate_state_is_rejected()
    print("PASS capture v24 integrity tests")
