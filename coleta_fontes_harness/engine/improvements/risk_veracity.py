# risk_veracity.py
# AURA QUANT-X v12.6.17 / 12.8.x — Frente 2
# Veracity Decay Timer + integração contínua com Kelly Fracionário
# Porta 8765 — Risk Manager
# Usa HLC.pt como t0 para eliminar distorção de relógio de parede

from __future__ import annotations

import math
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ------------------------------------------------------------------
# Constantes de half-life (segundos) conforme especificação
# ------------------------------------------------------------------
HALF_LIFE = {
    "odds_last": 18.0,
    "odds_velocity": 25.0,
    "pressure_slope": 35.0,
    "wom_imbalance": 22.0,
    "corner_event_count": 40.0,
    "fixture_metadata": 120.0,
}

# Pesos para agregação de veracity
WEIGHTS = {
    "odds_last": 0.30,
    "odds_velocity": 0.25,
    "pressure_slope": 0.25,
    "wom_imbalance": 0.20,
}


@dataclass
class FieldSnapshot:
    """Snapshot de um campo de telemetria com seu HLC.pt de origem."""
    name: str
    value: float
    t0_ms: int                    # HLC.pt do momento da captura
    half_life_s: float


@dataclass
class VeracityResult:
    V: float                      # veracity agregada [0, 1]
    kappa: float                  # fator de amortecimento κ(V)
    gamma_age: float              # fator de drift absoluto
    delta_t_s: float              # idade do campo mais antigo crítico
    field_scores: Dict[str, float]
    f_star: float                 # Kelly clássico antes do decay
    f_final: float                # stake final após κ e γ
    action: str                   # "TRADE" | "HOLD" | "BLOCK_SOFT"


class SpinLock:
    """Mesmo padrão de caminho quente da Frente 1."""
    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "SpinLock":
        self._lock.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self._lock.release()


# ------------------------------------------------------------------
# Funções puras de decaimento
# ------------------------------------------------------------------
def exponential_decay(v0: float, t0_ms: int, now_ms: int, half_life_s: float) -> float:
    """
    v(t) = v0 * exp(-λ * (t - t0))
    λ = ln(2) / H
    """
    if half_life_s <= 0:
        return 0.0
    dt_s = max(0.0, (now_ms - t0_ms) / 1000.0)
    lam = math.log(2.0) / half_life_s
    return v0 * math.exp(-lam * dt_s)


def hybrid_linear_exponential_decay(
    v0: float, t0_ms: int, now_ms: int, half_life_s: float, mu_factor: float = 0.4
) -> float:
    """
    Decaimento híbrido para pressure_slope:
    v(t) = v0 * max(0, 1 - (t-t0)/H) * exp(-μ * (t-t0))
    μ = 0.4 * λ
    """
    if half_life_s <= 0:
        return 0.0
    dt_s = max(0.0, (now_ms - t0_ms) / 1000.0)
    linear = max(0.0, 1.0 - dt_s / half_life_s)
    lam = math.log(2.0) / half_life_s
    mu = mu_factor * lam
    return v0 * linear * math.exp(-mu * dt_s)


def field_relative_score(
    name: str, value: float, t0_ms: int, now_ms: int
) -> float:
    """
    Retorna v(t)/v0 ∈ [0, 1] (relativo).
    """
    H = HALF_LIFE.get(name, 30.0)
    if name == "pressure_slope":
        return max(0.0, min(1.0, hybrid_linear_exponential_decay(1.0, t0_ms, now_ms, H)))
    else:
        return max(0.0, min(1.0, exponential_decay(1.0, t0_ms, now_ms, H)))


# ------------------------------------------------------------------
# κ(V) com suavização cúbica nas fronteiras
# ------------------------------------------------------------------
def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite smoothstep clássico."""
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def cubic_smooth_kappa(V: float) -> float:
    """
    κ(V) com suavização cúbica:
      V ≥ 0.85 → 1.0
      0.45 ≤ V < 0.85 → rampa suave
      V < 0.45 → 0.0
    """
    if V >= 0.85:
        return 1.0
    if V <= 0.45:
        return 0.0
    return smoothstep(0.45, 0.85, V)


# ------------------------------------------------------------------
# γ_age — penalidade de drift absoluto
# ------------------------------------------------------------------
def gamma_age(delta_t_s: float) -> float:
    """
    γ_age =
        1.0                         se Δt ≤ 20 s
        1 - 0.028 * (Δt - 20)       se 20 < Δt ≤ 45
        0.0                         se Δt > 45
    """
    if delta_t_s <= 20.0:
        return 1.0
    if delta_t_s > 45.0:
        return 0.0
    return max(0.0, 1.0 - 0.028 * (delta_t_s - 20.0))


# ------------------------------------------------------------------
# Kelly clássico fracionário
# ------------------------------------------------------------------
def kelly_fractional(p: float, b: float, fraction: float = 0.25) -> float:
    """
    f* = fraction * (p*b - q) / b
    p = probabilidade do modelo
    b = odds líquidas (decimal - 1)
    q = 1 - p
    """
    if b <= 0.0 or p <= 0.0 or p >= 1.0:
        return 0.0
    q = 1.0 - p
    edge = p * b - q
    if edge <= 0.0:
        return 0.0
    f_star = fraction * (edge / b)
    return max(0.0, min(f_star, 0.05))  # hard cap 5 % do bankroll


# ------------------------------------------------------------------
# Motor principal de veracity + risk
# ------------------------------------------------------------------
class VeracityRiskEngine:
    """
    Calcula V, κ, γ e f_final de forma pura e thread-safe.
    Snapshot de campos é imutável após captura (copy-on-write semântico).
    """

    MIN_STAKE_THRESHOLD = 0.002          # abaixo de 0.2 % → HOLD

    def __init__(self) -> None:
        self._lock = SpinLock()
        self._last_result: Optional[VeracityResult] = None
        self._history: List[VeracityResult] = []

    def compute(
        self,
        fields: List[FieldSnapshot],
        model_prob: float,
        decimal_odds: float,
        now_ms: Optional[int] = None,
        kelly_fraction: float = 0.25,
    ) -> VeracityResult:
        """
        Função principal.
        fields: lista de FieldSnapshot com t0_ms = HLC.pt de origem.
        model_prob: probabilidade emitida pelo ensemble/Hawkes.
        decimal_odds: odds decimais atuais do mercado.
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        # --- scores relativos por campo ---
        scores: Dict[str, float] = {}
        critical_ages: List[float] = []

        for f in fields:
            score = field_relative_score(f.name, f.value, f.t0_ms, now_ms)
            scores[f.name] = score
            if f.name in WEIGHTS:
                age_s = max(0.0, (now_ms - f.t0_ms) / 1000.0)
                critical_ages.append(age_s)

        # --- veracity agregada ponderada ---
        V = 0.0
        w_sum = 0.0
        for name, w in WEIGHTS.items():
            s = scores.get(name, 0.0)
            V += w * s
            w_sum += w
        if w_sum > 0:
            V /= w_sum
        V = max(0.0, min(1.0, V))

        # --- idade do campo crítico mais antigo ---
        delta_t_s = max(critical_ages) if critical_ages else 0.0

        # --- fatores ---
        kappa = cubic_smooth_kappa(V)
        gamma = gamma_age(delta_t_s)

        # --- Kelly ---
        b = max(0.0, decimal_odds - 1.0)
        f_star = kelly_fractional(model_prob, b, fraction=kelly_fraction)
        f_final = f_star * kappa * gamma

        # --- ação ---
        if f_final < self.MIN_STAKE_THRESHOLD:
            action = "HOLD"
        elif kappa < 0.15 or gamma < 0.15:
            action = "BLOCK_SOFT"
        else:
            action = "TRADE"

        result = VeracityResult(
            V=round(V, 6),
            kappa=round(kappa, 6),
            gamma_age=round(gamma, 6),
            delta_t_s=round(delta_t_s, 3),
            field_scores={k: round(v, 6) for k, v in scores.items()},
            f_star=round(f_star, 8),
            f_final=round(f_final, 8),
            action=action,
        )

        with self._lock:
            self._last_result = result
            self._history.append(result)
            if len(self._history) > 500:
                self._history = self._history[-300:]

        return result

    def last(self) -> Optional[VeracityResult]:
        with self._lock:
            return self._last_result

    def history_tail(self, n: int = 20) -> List[VeracityResult]:
        with self._lock:
            return list(self._history[-n:])


# ------------------------------------------------------------------
# Helpers de construção de snapshot a partir de telemetria bruta
# ------------------------------------------------------------------
def build_field_snapshots(
    telemetry: Dict[str, Any],
    hlc_pt: int,
) -> List[FieldSnapshot]:
    """
    Converte dicionário de telemetria + HLC.pt único (ou por campo)
    em lista de FieldSnapshot.
    """
    out: List[FieldSnapshot] = []
    mapping = {
        "odds_last": ("odds", "odds_last"),
        "odds_velocity": ("odds_velocity", "velocity"),
        "pressure_slope": ("pressure_slope", "pressure"),
        "wom_imbalance": ("wom", "wom_imbalance"),
        "corner_event_count": ("corners", "corner_count"),
        "fixture_metadata": ("fixture_ts", "meta_ts"),
    }
    for logical_name, keys in mapping.items():
        val = None
        t0 = hlc_pt
        for k in keys:
            if k in telemetry:
                raw = telemetry[k]
                if isinstance(raw, dict):
                    val = float(raw.get("value", 0.0))
                    t0 = int(raw.get("t0_ms", hlc_pt))
                else:
                    val = float(raw)
                break
        if val is None:
            val = 0.0
        out.append(
            FieldSnapshot(
                name=logical_name,
                value=val,
                t0_ms=t0,
                half_life_s=HALF_LIFE.get(logical_name, 30.0),
            )
        )
    return out


# ------------------------------------------------------------------
# Singleton de conveniência
# ------------------------------------------------------------------
_engine: Optional[VeracityRiskEngine] = None
_engine_lock = threading.Lock()


def get_veracity_engine() -> VeracityRiskEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = VeracityRiskEngine()
        return _engine


def evaluate_risk(
    telemetry: Dict[str, Any],
    model_prob: float,
    decimal_odds: float,
    hlc_pt: int,
    kelly_fraction: float = 0.25,
) -> VeracityResult:
    """API de alto nível usada pelo Risk Manager da Engine."""
    fields = build_field_snapshots(telemetry, hlc_pt)
    return get_veracity_engine().compute(
        fields=fields,
        model_prob=model_prob,
        decimal_odds=decimal_odds,
        now_ms=int(time.time() * 1000),
        kelly_fraction=kelly_fraction,
    )
