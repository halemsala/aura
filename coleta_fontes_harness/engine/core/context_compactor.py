# engine/core/context_compactor.py — V23: delta-state + whitelist for LLM payloads
from __future__ import annotations
import json
from typing import Any

KEEP_KEYS = frozenset((
    "match_id",
    "fixture_id",
    "fixtureId",
    "minute",
    "score",
    "pressure",
    "xG",
    "xg",
    "dangerous_attacks",
    "dangerous",
    "corners",
    "corner_events",
    "decision",
    "asian_corner_line",
    "asian_corner_odds",
    "odds_velocity",
    "smart_money_divergence",
    "home",
    "away",
    "imc",
    "action",
))


def compact_payload(payload: dict[str, Any], max_chars: int = 900) -> str:
    """Whitelist + float rounding. Fail-closed: empty dict → empty string."""
    if not isinstance(payload, dict):
        return ""
    compact: dict[str, Any] = {}
    for k in KEEP_KEYS:
        if k in payload:
            v = payload[k]
            if isinstance(v, float):
                v = round(v, 4)
            compact[k] = v
    txt = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return txt if len(txt) <= max_chars else txt[: max_chars - 3] + "..."



# P1: epsilon per field to suppress numeric jitter
_EPSILON: dict = {
    "odds_velocity": 0.020, "pressure": 0.002, "xG": 0.010, "win_probability": 0.010,
    "edge": 0.010, "calculated_edge": 0.010, "asian_corner_odds": 0.010,
}

def _changed(key: str, old, new) -> bool:
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        eps = float(_EPSILON.get(key, 0.0) or 0.0)
        if eps > 0.0:
            return abs(float(old) - float(new)) >= eps
    return old != new

def delta_state_eps(prev: dict, curr: dict) -> dict:
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return dict(curr) if isinstance(curr, dict) else {}
    return {k: v for k, v in curr.items() if k not in prev or _changed(k, prev[k], v)}

def delta_state(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any]:
    """Return only keys whose values changed vs previous snapshot."""
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return dict(curr) if isinstance(curr, dict) else {}
    out: dict[str, Any] = {}
    for k, v in curr.items():
        if _changed(k, prev.get(k), v):
            out[k] = v
    return out


def compact_for_model(
    snapshot: dict[str, Any],
    fixture_id: str | None = None,
    prev_card: dict[str, Any] | None = None,
) -> str:
    """Produce a minimal JSON card for GLM. Prefer delta when prev is available."""
    keep = {
        "match_id": snapshot.get("match_id") or fixture_id,
        "minute": snapshot.get("minute"),
        "score": snapshot.get("score"),
        "pressure": snapshot.get("pressure"),
        "xg": snapshot.get("xG") or snapshot.get("xg"),
        "dangerous_attacks": snapshot.get("dangerous_attacks") or snapshot.get("dangerous"),
        "corners": snapshot.get("corners"),
        "decision": snapshot.get("decision"),
        "odds_velocity": (
            (snapshot.get("wom") or {}).get("odds_velocity")
            if isinstance(snapshot.get("wom"), dict)
            else snapshot.get("odds_velocity")
        ),
    }
    # Drop None values to shrink further
    keep = {k: v for k, v in keep.items() if v is not None}
    if prev_card:
        delta = delta_state(prev_card, keep)
        payload = delta if delta else keep
    else:
        payload = keep
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# Extreme P1 2.1 — trim semântico (nunca corta JSON no meio)
CORE_KEYS = (
    "match_id", "fixture_id", "minute", "period", "score", "corners",
    "dangerous_attacks", "shots", "shots_on_target", "odds", "edge",
    "signal_state", "decision", "risk", "data_quality", "freshness", "ts",
)
SECONDARY_KEYS = (
    "xg", "attacks", "possession", "fouls", "offsides", "odds_velocity", "pressure",
)

def compact_for_llm(payload: dict, max_chars: int = 2048) -> str:
    import json as _json
    compact = {}
    for key in CORE_KEYS:
        if key in payload and payload[key] is not None:
            compact[key] = payload[key]
    for key in SECONDARY_KEYS:
        if key in payload and payload[key] is not None:
            trial = _json.dumps(compact, separators=(",", ":"), ensure_ascii=False, default=str)
            if len(trial) < max_chars * 0.75:
                compact[key] = payload[key]
    encoded = _json.dumps(compact, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return encoded
    for key in reversed(SECONDARY_KEYS):
        compact.pop(key, None)
        encoded = _json.dumps(compact, separators=(",", ":"), ensure_ascii=False, default=str)
        if len(encoded) <= max_chars:
            return encoded
    core = {k: compact[k] for k in CORE_KEYS if k in compact}
    return _json.dumps(core, separators=(",", ":"), ensure_ascii=False, default=str)
