# engine/core/capture_integrity.py — Extreme P1 §5
from __future__ import annotations
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class CaptureIntegrityMonitor:
    """Estado local do watchdog de captura para Bridge/WebView2."""
    def __init__(self, silence_timeout_sec: float = 10.0):
        self.silence_timeout_sec = max(1.0, float(silence_timeout_sec))
        self._last_feed_ts = 0.0
        self._dom_broken = False
        self._last_error: dict[str, Any] | None = None

    def update_feed_ts(self) -> None:
        self._last_feed_ts = time.time()
        self._dom_broken = False

    def receive_browser_event(self, event_data: dict) -> bool:
        """Recebe eventos do WebView2; não recarrega página nem chama rede."""
        if not isinstance(event_data, dict):
            return False
        event_type = str(event_data.get("type") or "")
        if event_type == "CAPTURE_ERROR":
            self._dom_broken = True
            self._last_error = {
                "detail": str(event_data.get("detail") or "UNKNOWN"),
                "url": str(event_data.get("url") or ""),
                "ts": time.time(),
            }
            logger.critical("DOM Canary Alert: %s", self._last_error["detail"])
            return True
        if event_type in ("FEED_DATA", "AURA_SOKKERPRO_CAPTURE"):
            self.update_feed_ts()
            return True
        return False

    def snapshot(self) -> dict[str, Any]:
        age = None if self._last_feed_ts <= 0 else max(0.0, time.time() - self._last_feed_ts)
        return {
            "dom_broken": self._dom_broken,
            "feed_age_sec": age,
            "stale": age is not None and age > self.silence_timeout_sec,
            "last_error": self._last_error,
        }


def accept_capture(payload: dict, session: Any) -> bool:
    """Valida identidade composta: session + epoch + tab + fixture + state_version."""
    if not isinstance(payload, dict) or session is None:
        return False
    try:
        if payload.get("captureSessionId") != getattr(session, "capture_session_id", None):
            return False
        if int(payload.get("captureEpoch", -1)) != int(getattr(session, "capture_epoch", -2)):
            return False
        if int(payload.get("tabId", -1)) != int(getattr(session, "tab_id", -2)):
            return False
        if str(payload.get("fixtureId", "")) != str(getattr(session, "fixture_id", "")):
            return False
        if int(payload.get("stateVersion", -1)) < int(getattr(session, "state_version", 0)):
            return False
        return True
    except Exception:
        return False
