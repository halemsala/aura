from __future__ import annotations
import hashlib, json

def stable_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def build_capture_hash(payload: dict) -> str:
    return stable_hash({"session": payload.get("captureSessionId"), "epoch": payload.get("captureEpoch"), "tab": payload.get("tabId"), "fixture": payload.get("fixtureId"), "state": payload.get("state")})

def build_state_hash(state: dict) -> str:
    return stable_hash({k: state.get(k) for k in ("minute","score","corners","dangerous","attacks","shots","xg","possession","period","events")})

def build_event_hash(fixture_id: str, event: dict) -> str:
    return stable_hash({"fixture": fixture_id, "type": event.get("type"), "minute": event.get("minute"), "team": event.get("team"), "ordinal": event.get("ordinal"), "payload": event.get("payload")})
