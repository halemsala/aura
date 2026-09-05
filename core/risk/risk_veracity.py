"""core/risk/risk_veracity.py — Veracity decay, κ(V), fractional Kelly, fail-closed."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Final, Mapping

logger = logging.getLogger("aura.risk.veracity")

TAU_ODDS_S: Final[float] = 12.0
TAU_VELOCITY_S: Final[float] = 8.0
TAU_PRESSURE_LIN_S: Final[float] = 20.0
TAU_PRESSURE_EXP_S: Final[float] = 15.0
PRESSURE_BLEND_T_S: Final[float] = 10.0
GAMMA_AGE_REF_S: Final[float] = 30.0
FAIL_CLOSED_AGE_S: Final[float] = 45.0
KELLY_FRACTION: Final[float] = 0.25
MIN_EDGE: Final[float] = 1e-6
EPS: Final[float] = 1e-12


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    decimal_odds: float
    p_model: float
    age_s: float


@dataclass(frozen=True, slots=True)
class FieldPressure:
    value: float
    age_s: float


@dataclass(frozen=True, slots=True)
class VelocityState:
    value: float
    age_s: float


@dataclass(frozen=True, slots=True)
class VeracityInput:
    odds_freshness_s: float
    source_agreement: float
    integrity_score: float
    capture_coverage: float


@dataclass(frozen=True, slots=True)
class RiskDecision:
    stake_fraction: float
    kelly_raw: float
    kappa: float
    gamma_age: float
    p_decayed: float
    odds_decayed: float
    pressure_decayed: float
    velocity_decayed: float
    fail_closed: bool
    reason: str


def exp_decay(value: float, age_s: float, tau_s: float) -> float:
    if tau_s <= 0.0:
        return 0.0
    age = max(0.0, age_s)
    return value * math.exp(-age / tau_s)


def hybrid_pressure_decay(value: float, age_s: float) -> float:
    v = max(0.0, value)
    age = max(0.0, age_s)
    t = PRESSURE_BLEND_T_S
    if age <= t:
        factor = 1.0 - (age / (2.0 * TAU_PRESSURE_LIN_S))
        return v * max(0.0, factor)
    v_at_t = v * max(0.0, 1.0 - (t / (2.0 * TAU_PRESSURE_LIN_S)))
    return v_at_t * math.exp(-(age - t) / TAU_PRESSURE_EXP_S)


def veracity_score(inp: VeracityInput) -> float:
    fresh = math.exp(-max(0.0, inp.odds_freshness_s) / 20.0)
    a = _clamp01(inp.source_agreement)
    i = _clamp01(inp.integrity_score)
    c = _clamp01(inp.capture_coverage)
    geo = (fresh * a * i * c) ** 0.25
    return _clamp01(geo)


def kappa_cubic(v: float) -> float:
    x = _clamp01(v)
    return 3.0 * x * x - 2.0 * x * x * x


def gamma_age(age_s: float) -> float:
    age = max(0.0, age_s)
    return 1.0 / (1.0 + age / GAMMA_AGE_REF_S)


def kelly_fractional(
    p: float,
    decimal_odds: float,
    fraction: float = KELLY_FRACTION,
) -> float:
    if decimal_odds <= 1.0 or p <= 0.0:
        return 0.0
    b = decimal_odds - 1.0
    if b <= 0.0:
        return 0.0
    edge = p * (b + 1.0) - 1.0
    if edge <= MIN_EDGE:
        return 0.0
    f_star = edge / b
    return max(0.0, fraction * f_star)


def apply_decays(
    market: MarketSnapshot,
    pressure: FieldPressure,
    velocity: VelocityState,
) -> Mapping[str, float]:
    odds_d = max(1.01, exp_decay(market.decimal_odds, market.age_s, TAU_ODDS_S))
    p_d = _clamp01(exp_decay(market.p_model, market.age_s, TAU_VELOCITY_S))
    vel_d = exp_decay(velocity.value, velocity.age_s, TAU_VELOCITY_S)
    pr_d = hybrid_pressure_decay(pressure.value, pressure.age_s)
    return {
        "odds_decayed": odds_d,
        "p_decayed": p_d,
        "velocity_decayed": vel_d,
        "pressure_decayed": pr_d,
    }


def evaluate_risk(
    market: MarketSnapshot,
    pressure: FieldPressure,
    velocity: VelocityState,
    veracity_in: VeracityInput,
    kelly_frac: float = KELLY_FRACTION,
) -> RiskDecision:
    age = max(0.0, market.age_s)
    if age > FAIL_CLOSED_AGE_S:
        logger.error(
            "risk_fail_closed",
            extra={
                "event": "risk_fail_closed",
                "age_s": age,
                "threshold_s": FAIL_CLOSED_AGE_S,
                "odds": market.decimal_odds,
                "p_model": market.p_model,
            },
        )
        return RiskDecision(
            stake_fraction=0.0,
            kelly_raw=0.0,
            kappa=0.0,
            gamma_age=0.0,
            p_decayed=0.0,
            odds_decayed=market.decimal_odds,
            pressure_decayed=0.0,
            velocity_decayed=0.0,
            fail_closed=True,
            reason=f"fail_closed_age_{age:.1f}s>{FAIL_CLOSED_AGE_S:.0f}s",
        )
    decays = apply_decays(market, pressure, velocity)
    v = veracity_score(veracity_in)
    k = kappa_cubic(v)
    g = gamma_age(age)
    f_raw = kelly_fractional(decays["p_decayed"], decays["odds_decayed"], kelly_frac)
    stake = max(0.0, f_raw * k * g)
    return RiskDecision(
        stake_fraction=stake,
        kelly_raw=f_raw,
        kappa=k,
        gamma_age=g,
        p_decayed=decays["p_decayed"],
        odds_decayed=decays["odds_decayed"],
        pressure_decayed=decays["pressure_decayed"],
        velocity_decayed=decays["velocity_decayed"],
        fail_closed=False,
        reason="ok",
    )


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)
