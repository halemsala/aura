"""P0 Fase 3 — Contrato de alvo e censura.

Produto principal: next_corner_within_300s
Horizontes auxiliares: 60s, 180s, 600s

Y_H(t) = 1 se ocorrer >=1 escanteio em [t, t+H]
Y_H(t) = 0 se a janela inteira for observada e nenhum escanteio ocorrer
Y_H(t) = censored (label=NULL) se a janela não puder ser observada integralmente

Nunca converter janela incompleta em RED automático (label=0).
Produto over_9_5 é SEPARADO e não compartilhado neste módulo.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- Contrato formal de alvos ---

TARGET_PRIMARY = "next_corner_within_300s"
TARGET_NAME = "next_corner_within_horizon"

HORIZONS_SEC: Tuple[int, ...] = (60, 180, 300, 600)

PRODUCT_A = "next_corner_within_300s"
PRODUCT_B = "match_total_corners_over_9_5"  # declarado mas NÃO rotulado aqui

LABEL_VERSION = "label_v1_p0_censor"

CENSOR_REASONS = (
    "HALFTIME",
    "MATCH_END",
    "CAPTURE_LOSS",
    "ABANDONED",
    "UNKNOWN",
)

# liveStatus / clock heuristics
_HALFTIME_MARKERS = ("HT", "HALF", "INTERVALO", "HALFTIME", "HALF-TIME", "HALF_TIME")
_END_MARKERS = ("FT", "END", "FINISHED", "AET", "PEN", "FULL TIME", "ENCERRADO", "FINAL")
_ABANDON_MARKERS = ("ABANDON", "SUSP", "POSTP", "CANCEL", "ABANDONED", "SUSPENSO")


def target_id(horizon_sec: int) -> str:
    if horizon_sec not in HORIZONS_SEC:
        raise ValueError(f"horizon_sec inválido: {horizon_sec}; use {HORIZONS_SEC}")
    return f"next_corner_within_{horizon_sec}s"


def is_primary_product(name: str) -> bool:
    return str(name) in (TARGET_PRIMARY, PRODUCT_A, "next_corner_within_horizon")


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def detect_match_phase(payload: Dict[str, Any], *, clock_sec: Optional[float] = None) -> str:
    """
    Returns one of: LIVE, HALFTIME, MATCH_END, ABANDONED, UNKNOWN
    """
    status = _norm_text(
        payload.get("liveStatus")
        or payload.get("status")
        or payload.get("matchStatus")
        or payload.get("periodo")
    )
    for m in _ABANDON_MARKERS:
        if m in status:
            return "ABANDONED"
    for m in _END_MARKERS:
        if m in status or status == "FT":
            return "MATCH_END"
    for m in _HALFTIME_MARKERS:
        if m in status or status == "HT":
            return "HALFTIME"

    # clock-based soft signals
    minute = payload.get("minute")
    try:
        minute_f = float(minute) if minute is not None else None
    except (TypeError, ValueError):
        minute_f = None
    if minute_f is not None:
        if 45.0 <= minute_f < 46.0 and status in ("", "LIVE", "1H", "1º", "1O"):
            # borderline HT — only if explicit HT period flag present
            period = _norm_text(payload.get("period") or payload.get("half") or "")
            if period in ("HT", "HALF", "INTERVAL"):
                return "HALFTIME"
        if minute_f >= 130:
            return "MATCH_END"

    if payload.get("match_ended") is True or payload.get("finished") is True:
        return "MATCH_END"
    if payload.get("abandoned") is True:
        return "ABANDONED"

    return "LIVE"


def extract_corner_event_times(payload: Dict[str, Any]) -> List[float]:
    """
    Extract corner event timestamps in match-seconds (approximate).
    Accepts events list with minute/second fields or cumulative corners as fallback
    is NOT used here (would lose timing).
    """
    events = payload.get("events") or payload.get("eventos") or []
    times: List[float] = []
    if not isinstance(events, list):
        return times
    for event in events:
        if isinstance(event, dict):
            blob = " ".join(
                str(event.get(k) or "") for k in ("type", "event", "name", "kind", "label")
            ).lower()
            if "corner" not in blob and "escante" not in blob:
                continue
            sec = None
            for key in ("match_seconds", "seconds", "sec", "clock_sec"):
                if event.get(key) is not None:
                    try:
                        sec = float(event[key])
                        break
                    except (TypeError, ValueError):
                        pass
            if sec is None:
                try:
                    m = float(event.get("minute") or event.get("min") or 0)
                    s = float(event.get("second") or event.get("seg") or 0)
                    sec = m * 60.0 + s
                except (TypeError, ValueError):
                    continue
            times.append(sec)
        else:
            text = str(event).lower()
            if "corner" in text or "escante" in text:
                # no timing → skip (cannot place in window)
                continue
    times.sort()
    return times


def extract_corner_count(payload: Dict[str, Any]) -> Optional[int]:
    stats = payload.get("stats") or payload.get("estatisticas") or {}
    if not isinstance(stats, dict):
        return None
    corners = stats.get("corners") or stats.get("escanteios") or {}
    if not isinstance(corners, dict):
        return None
    total = 0
    found = False
    for side in ("home", "away"):
        if side in corners and corners.get(side) is not None:
            found = True
            try:
                total += int(float(corners.get(side)))
            except (TypeError, ValueError):
                return None
    return total if found else None


def resolve_window_start(
    payload: Dict[str, Any],
    *,
    window_start_ts: Optional[float] = None,
    match_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve absolute and match-relative window start."""
    if window_start_ts is None:
        stamp = (
            payload.get("capturedAt")
            or payload.get("captured_at")
            or payload.get("timestamp")
            or payload.get("ts")
        )
        if isinstance(stamp, (int, float)):
            window_start_ts = float(stamp if stamp < 10_000_000_000 else stamp / 1000.0)
        elif isinstance(stamp, str):
            try:
                from datetime import datetime, timezone
                text = stamp.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(text)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                window_start_ts = parsed.timestamp()
            except Exception:
                window_start_ts = None

    if match_seconds is None:
        try:
            if payload.get("match_seconds") is not None:
                match_seconds = float(payload["match_seconds"])
            elif payload.get("minute") is not None:
                m = float(payload.get("minute") or 0)
                extra = float(payload.get("extraMinute") or payload.get("second") or 0)
                # if extra looks like seconds into minute
                if extra > 60:
                    match_seconds = m * 60.0
                else:
                    match_seconds = m * 60.0 + extra
        except (TypeError, ValueError):
            match_seconds = None

    return {
        "window_start_ts": window_start_ts,
        "match_seconds": match_seconds,
    }


def label_window(
    *,
    horizon_sec: int,
    window_start_ts: Optional[float],
    match_seconds: Optional[float],
    corner_event_times: Sequence[float],
    corners_at_start: Optional[int] = None,
    corners_at_end: Optional[int] = None,
    phase_at_start: str = "LIVE",
    phase_at_end: Optional[str] = None,
    window_observed_until_ts: Optional[float] = None,
    capture_lost: bool = False,
    label_version: str = LABEL_VERSION,
) -> Dict[str, Any]:
    """
    Core labeling with censoring.

    Preference order for positive detection:
    1) timed corner events in [match_seconds, match_seconds+H]
    2) cumulative corner count increase if both start and end counts known AND window complete
    """
    if horizon_sec not in HORIZONS_SEC:
        raise ValueError(f"horizon_sec inválido: {horizon_sec}")

    target = target_id(horizon_sec)
    window_end_ts = (window_start_ts + horizon_sec) if window_start_ts is not None else None

    result: Dict[str, Any] = {
        "target_name": TARGET_NAME,
        "product": target,
        "horizon_sec": horizon_sec,
        "window_start_ts": window_start_ts,
        "window_end_ts": window_end_ts,
        "match_seconds_start": match_seconds,
        "label": None,
        "censored": 0,
        "censor_reason": None,
        "window_complete": 0,
        "label_version": label_version,
    }

    # Immediate censor conditions
    if capture_lost:
        result["censored"] = 1
        result["censor_reason"] = "CAPTURE_LOSS"
        result["label"] = None
        return result

    if phase_at_start in ("HALFTIME", "MATCH_END", "ABANDONED"):
        # window starts in non-live phase → cannot label as observed live window
        result["censored"] = 1
        result["censor_reason"] = phase_at_start if phase_at_start in CENSOR_REASONS else "UNKNOWN"
        result["label"] = None
        return result

    # Determine if window was fully observed
    window_complete = False
    if window_start_ts is not None and window_observed_until_ts is not None:
        window_complete = window_observed_until_ts >= (window_start_ts + horizon_sec - 1e-6)
    elif phase_at_end is not None:
        # if match ended/HT before horizon elapsed relative to start, incomplete
        if phase_at_end in ("HALFTIME", "MATCH_END", "ABANDONED"):
            window_complete = False
        elif phase_at_end == "LIVE" and window_observed_until_ts is None:
            # insufficient evidence of full observation
            window_complete = False
    # explicit complete flag path for offline labeling when end snapshot exists after horizon
    if window_observed_until_ts is not None and window_start_ts is not None:
        window_complete = window_observed_until_ts >= (window_start_ts + horizon_sec - 1e-6)

    result["window_complete"] = 1 if window_complete else 0

    # Positive via timed events
    if match_seconds is not None and corner_event_times:
        end_m = match_seconds + horizon_sec
        hits = [t for t in corner_event_times if match_seconds <= t < end_m]
        if hits:
            result["label"] = 1
            result["censored"] = 0
            result["censor_reason"] = None
            # positive can be assigned even if later observation incomplete
            return result

    # Positive via cumulative corners if both ends known
    if corners_at_start is not None and corners_at_end is not None:
        if corners_at_end > corners_at_start:
            result["label"] = 1
            result["censored"] = 0
            result["censor_reason"] = None
            return result

    # No positive evidence
    if not window_complete:
        # Censor — NEVER auto RED
        reason = "UNKNOWN"
        if phase_at_end == "HALFTIME":
            reason = "HALFTIME"
        elif phase_at_end == "MATCH_END":
            reason = "MATCH_END"
        elif phase_at_end == "ABANDONED":
            reason = "ABANDONED"
        elif capture_lost:
            reason = "CAPTURE_LOSS"
        result["censored"] = 1
        result["censor_reason"] = reason
        result["label"] = None
        return result

    # Window fully observed and no corner → label 0
    result["label"] = 0
    result["censored"] = 0
    result["censor_reason"] = None
    return result


def label_from_payloads(
    start_payload: Dict[str, Any],
    *,
    horizon_sec: int = 300,
    end_payload: Optional[Dict[str, Any]] = None,
    corner_event_times: Optional[Sequence[float]] = None,
    capture_lost: bool = False,
    label_version: str = LABEL_VERSION,
) -> Dict[str, Any]:
    """High-level helper: label one window from start (+ optional end) payloads."""
    start_meta = resolve_window_start(start_payload)
    phase_start = detect_match_phase(start_payload)

    times = list(corner_event_times) if corner_event_times is not None else extract_corner_event_times(start_payload)
    if end_payload:
        # merge corner times from end snapshot (often fuller event list)
        for t in extract_corner_event_times(end_payload):
            if t not in times:
                times.append(t)
        times.sort()

    corners_start = extract_corner_count(start_payload)
    corners_end = extract_corner_count(end_payload) if end_payload else None

    phase_end = detect_match_phase(end_payload) if end_payload else None
    end_meta = resolve_window_start(end_payload) if end_payload else {}
    observed_until = end_meta.get("window_start_ts")

    return label_window(
        horizon_sec=horizon_sec,
        window_start_ts=start_meta.get("window_start_ts"),
        match_seconds=start_meta.get("match_seconds"),
        corner_event_times=times,
        corners_at_start=corners_start,
        corners_at_end=corners_end,
        phase_at_start=phase_start,
        phase_at_end=phase_end,
        window_observed_until_ts=observed_until,
        capture_lost=capture_lost,
        label_version=label_version,
    )


def label_all_horizons(
    start_payload: Dict[str, Any],
    *,
    end_payload: Optional[Dict[str, Any]] = None,
    capture_lost: bool = False,
) -> List[Dict[str, Any]]:
    return [
        label_from_payloads(
            start_payload,
            horizon_sec=h,
            end_payload=end_payload,
            capture_lost=capture_lost,
        )
        for h in HORIZONS_SEC
    ]


def label_row_id(
    fixture_id: str,
    horizon_sec: int,
    window_start_ts: Optional[float],
    label_version: str = LABEL_VERSION,
) -> str:
    """Stable idempotent id for a label row."""
    base = f"{fixture_id}|{horizon_sec}|{window_start_ts}|{label_version}"
    return "lbl_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def assert_not_over_under_product(product: str) -> None:
    if "over_" in str(product).lower() or "under_" in str(product).lower() or "9_5" in str(product):
        raise ValueError(
            f"Produto '{product}' não é next_corner_within_horizon. "
            f"Use product separado: {PRODUCT_B}"
        )
