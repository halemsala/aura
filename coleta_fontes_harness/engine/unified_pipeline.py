# unified_pipeline.py — Integra melhorias no fluxo de telemetria → sinal
from __future__ import annotations
import time
from typing import Any, Dict, List

from improvements.telemetry_schema import validate_payload
from improvements.frame_cache import FrameCache
from improvements.rate_limit import RateLimiter
from improvements.trading_mode import get_mode, requires_real_odds, allows_stake, TradingMode
from improvements.structured_log import log_event
from improvements.notify_policy import should_notify
from improvements.health_agg import build_health
from improvements.model_checksum import verify_weights
from features import engineer_sequence, frame_from_stats, baseline_signal
from risk_manager import RiskManager
from data_store import log_signal, open_paper_trade, init_schema
from signals_service import process_live_signal

init_schema()

frame_cache = FrameCache(ttl_seconds=3.0)
rate_limiter = RateLimiter(per_fixture_interval=2.0, global_per_sec=10)
risk = RiskManager(bankroll=1000.0)
match_history: Dict[str, List[List[float]]] = {}


def process_telemetry(raw_payload: Dict[str, Any], model_corner: float = 0.5, model_goal: float = 0.5) -> Dict[str, Any]:
    t0 = time.time()
    ok, err, norm = validate_payload(raw_payload)
    if not ok:
        log_event("warn", "invalid_payload", error=err)
        return {"signal": "HOLD", "error": err, "approved": False}

    fid = norm["fixtureId"]
    if not rate_limiter.allow(fid):
        log_event("info", "rate_limited", fixtureId=fid)
        cached = frame_cache.get(fid, norm["stats"])
        if cached:
            cached["rate_limited"] = True
            return cached
        return {"signal": "HOLD", "reason": "rate_limited", "approved": False, "fixtureId": fid}

    cached = frame_cache.get(fid, norm["stats"])
    if cached:
        cached["from_frame_cache"] = True
        return cached

    frame = frame_from_stats(norm["stats"])
    hist = match_history.setdefault(fid, [])
    hist.append(frame)
    if len(hist) > 15:
        hist.pop(0)

    mode = get_mode()
    odds = norm.get("odds")
    try:
        odds_f = float(odds) if odds is not None and str(odds).strip() != "" else None
    except (TypeError, ValueError):
        odds_f = None
    if odds_f is None or odds_f <= 1.0:
        log_event("warn", "odds_unobserved", fixtureId=fid)
        result = {
            "fixtureId": fid,
            "signal": "HOLD",
            "approved": False,
            "reason": "odds_unobserved",
            "data_gap": "missing_odds",
            "match": f"{norm['home']} vs {norm['away']}",
            "paper_trade": True,
            "execution_allowed": False,
        }
        frame_cache.set(fid, norm["stats"], result)
        return result
    svc = process_live_signal(
        fixture_id=fid,
        stats=norm["stats"],
        history=hist,
        model_corner_prob=model_corner,
        model_goal_prob=model_goal,
        odds=odds_f,
        use_baseline_if_weak=(mode != TradingMode.LIVE),
    )

    # observe mode: força não stake
    if mode == TradingMode.OBSERVE:
        svc["approved"] = False
        svc["signal"] = "HOLD" if not svc.get("approved") else svc["signal"]
        svc["stake_pct"] = 0.0
        svc["paper_trade_id"] = None
        svc["risk_reason"] = "observe_mode"

    if not allows_stake(mode) and mode == TradingMode.OBSERVE:
        pass

    notify = should_notify(svc.get("signal", "HOLD"), bool(svc.get("approved")))
    latency = round((time.time() - t0) * 1000, 2)

    result = {
        "fixtureId": fid,
        "match": f"{norm['home']} vs {norm['away']}",
        "clock": norm["clock"],
        "signal": svc.get("signal", "HOLD"),
        "approved": svc.get("approved", False),
        "stake_pct": svc.get("stake_pct", 0),
        "prob": svc.get("prob", 0),
        "risk_reason": svc.get("risk_reason"),
        "features": svc.get("features"),
        "baseline_signal": svc.get("baseline_signal"),
        "paper_trade_id": svc.get("paper_trade_id"),
        "notify": notify,
        "trading_mode": mode.value,
        "latency_ms": latency,
        "odds": odds_f,
        "schema_version": norm["schema_version"],
    }
    frame_cache.set(fid, norm["stats"], result)
    log_event(
        "info",
        "telemetry_processed",
        fixtureId=fid,
        signal=result["signal"],
        approved=result["approved"],
        latency_ms=latency,
    )
    return result


def health_snapshot(**kwargs) -> Dict[str, Any]:
    weights_ok = verify_weights("model_weights.pt")
    return build_health(
        quant_weights_ok=weights_ok,
        trading_mode=get_mode().value,
        extra=kwargs,
    )
