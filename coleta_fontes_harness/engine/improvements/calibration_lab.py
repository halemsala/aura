# calibration_lab.py
# AURA QUANT-X — Calibration Lab + Walk-forward + Isotonic Regression
# Nunca declara acurácia preditiva com dados sintéticos.
# Paper-first / fail-closed.

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_pred: float
    mean_outcome: float
    ece_contrib: float


@dataclass
class CalibrationReport:
    method: str
    n_samples: int
    brier: float
    log_loss: float
    ece: float
    bins: List[CalibrationBin]
    horizon: str
    model_version: str
    is_synthetic: bool
    disclaimer: str
    timestamp: float = field(default_factory=time.time)


def _clip01(x: float) -> float:
    return max(1e-6, min(1.0 - 1e-6, float(x)))


def brier_score(y_true: Sequence[float], y_prob: Sequence[float]) -> float:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_prob, dtype=np.float64)
    if len(yt) == 0:
        return float("nan")
    return float(np.mean((yp - yt) ** 2))


def log_loss(y_true: Sequence[float], y_prob: Sequence[float]) -> float:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.clip(np.asarray(y_prob, dtype=np.float64), 1e-6, 1 - 1e-6)
    if len(yt) == 0:
        return float("nan")
    return float(-np.mean(yt * np.log(yp) + (1 - yt) * np.log(1 - yp)))


def expected_calibration_error(
    y_true: Sequence[float], y_prob: Sequence[float], n_bins: int = 10
) -> Tuple[float, List[CalibrationBin]]:
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_prob, dtype=np.float64)
    if len(yt) == 0:
        return float("nan"), []
    bins: List[CalibrationBin] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (yp >= lo) & (yp < hi if i < n_bins - 1 else yp <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            bins.append(CalibrationBin(lo, hi, 0, 0.0, 0.0, 0.0))
            continue
        mean_p = float(yp[mask].mean())
        mean_y = float(yt[mask].mean())
        contrib = (cnt / len(yt)) * abs(mean_p - mean_y)
        ece += contrib
        bins.append(CalibrationBin(lo, hi, cnt, mean_p, mean_y, contrib))
    return float(ece), bins


# ------------------------------------------------------------------
# Isotonic Regression (PAV — Pool Adjacent Violators) puro NumPy
# ------------------------------------------------------------------
def isotonic_regression(y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Isotonic regression crescente (PAV).
    y: valores observados (ou previsões a calibrar ordenadas por score bruto).
    Retorna valores calibrados monotônicos.
    """
    y = np.asarray(y, dtype=np.float64).copy()
    n = len(y)
    if n == 0:
        return y
    if sample_weight is None:
        w = np.ones(n, dtype=np.float64)
    else:
        w = np.asarray(sample_weight, dtype=np.float64)

    # Blocos: (start, end, sum_wy, sum_w)
    blocks: List[List[float]] = [[i, i + 1, w[i] * y[i], w[i]] for i in range(n)]

    i = 0
    while i < len(blocks) - 1:
        # média do bloco atual e do próximo
        mean_i = blocks[i][2] / blocks[i][3]
        mean_next = blocks[i + 1][2] / blocks[i + 1][3]
        if mean_i > mean_next + 1e-12:  # violação de monotonicidade
            # funde
            blocks[i][1] = blocks[i + 1][1]
            blocks[i][2] += blocks[i + 1][2]
            blocks[i][3] += blocks[i + 1][3]
            del blocks[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1

    out = np.empty(n, dtype=np.float64)
    for start, end, sum_wy, sum_w in blocks:
        val = sum_wy / sum_w
        out[int(start):int(end)] = val
    return out


@dataclass
class IsotonicCalibrator:
    """
    Calibrador isotônico.
    Fit apenas com dados rotulados reais.
    Se is_synthetic=True, o predict() adiciona disclaimer e não deve ser usado
    para declaração de acertividade em produção.
    """
    x_thresholds_: Optional[np.ndarray] = None
    y_thresholds_: Optional[np.ndarray] = None
    is_synthetic: bool = True
    n_train: int = 0
    fitted: bool = False

    def fit(self, raw_scores: Sequence[float], outcomes: Sequence[float], is_synthetic: bool = True) -> "IsotonicCalibrator":
        x = np.asarray(raw_scores, dtype=np.float64)
        y = np.asarray(outcomes, dtype=np.float64)
        if len(x) != len(y) or len(x) < 5:
            self.fitted = False
            self.is_synthetic = True
            return self
        order = np.argsort(x)
        x_sorted = x[order]
        y_sorted = y[order]
        y_iso = isotonic_regression(y_sorted)
        self.x_thresholds_ = x_sorted
        self.y_thresholds_ = y_iso
        self.n_train = len(x)
        self.is_synthetic = bool(is_synthetic)
        self.fitted = True
        return self

    def predict(self, raw_scores: Sequence[float]) -> np.ndarray:
        if not self.fitted or self.x_thresholds_ is None:
            return np.clip(np.asarray(raw_scores, dtype=np.float64), 0.0, 1.0)
        x = np.asarray(raw_scores, dtype=np.float64)
        # interpolação linear entre limiares
        return np.interp(x, self.x_thresholds_, self.y_thresholds_, left=self.y_thresholds_[0], right=self.y_thresholds_[-1])

    def report(
        self,
        y_true: Sequence[float],
        y_prob_raw: Sequence[float],
        horizon: str = "unknown",
        model_version: str = "unknown",
    ) -> CalibrationReport:
        y_cal = self.predict(y_prob_raw) if self.fitted else np.asarray(y_prob_raw, dtype=np.float64)
        brier = brier_score(y_true, y_cal)
        ll = log_loss(y_true, y_cal)
        ece, bins = expected_calibration_error(y_true, y_cal)
        disc = (
            "SYNTHETIC_NOT_VALIDATED — não usar para declarar acertividade em produção"
            if self.is_synthetic
            else "Calibrado com dados rotulados. Validar walk-forward antes de promoção."
        )
        return CalibrationReport(
            method="isotonic",
            n_samples=len(y_true),
            brier=brier,
            log_loss=ll,
            ece=ece,
            bins=bins,
            horizon=horizon,
            model_version=model_version,
            is_synthetic=self.is_synthetic,
            disclaimer=disc,
        )


# ------------------------------------------------------------------
# Walk-forward por fixture (sem leakage temporal)
# ------------------------------------------------------------------
def walk_forward_splits(
    fixture_ids: Sequence[str],
    timestamps: Sequence[float],
    min_train: int = 30,
    test_size: int = 10,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Gera splits walk-forward ordenados por tempo.
    Cada split: (indices_train, indices_test).
    Nunca embaralha — respeita ordem temporal.
    """
    order = np.argsort(np.asarray(timestamps, dtype=np.float64))
    n = len(order)
    splits = []
    start = 0
    while start + min_train + test_size <= n:
        train_idx = order[start : start + min_train]
        test_idx = order[start + min_train : start + min_train + test_size]
        splits.append((train_idx, test_idx))
        start += test_size
    return splits


def walk_forward_evaluate(
    raw_scores: Sequence[float],
    outcomes: Sequence[float],
    timestamps: Sequence[float],
    fixture_ids: Sequence[str],
    is_synthetic: bool = True,
    horizon: str = "5m",
    model_version: str = "unknown",
) -> Dict[str, Any]:
    """
    Avalia calibrador isotônico em regime walk-forward.
    Retorna métricas agregadas + disclaimer obrigatório.
    """
    scores = np.asarray(raw_scores, dtype=np.float64)
    y = np.asarray(outcomes, dtype=np.float64)
    splits = walk_forward_splits(fixture_ids, timestamps)
    if not splits:
        return {
            "status": "INSUFFICIENT_DATA",
            "n_splits": 0,
            "is_synthetic": is_synthetic,
            "disclaimer": "Dados insuficientes para walk-forward. NÃO declarar acertividade.",
        }

    briers, lls, eces = [], [], []
    for train_idx, test_idx in splits:
        cal = IsotonicCalibrator()
        cal.fit(scores[train_idx], y[train_idx], is_synthetic=is_synthetic)
        rep = cal.report(y[test_idx], scores[test_idx], horizon=horizon, model_version=model_version)
        if not math.isnan(rep.brier):
            briers.append(rep.brier)
            lls.append(rep.log_loss)
            eces.append(rep.ece)

    return {
        "status": "OK" if briers else "FAILED",
        "n_splits": len(splits),
        "mean_brier": float(np.mean(briers)) if briers else None,
        "mean_log_loss": float(np.mean(lls)) if lls else None,
        "mean_ece": float(np.mean(eces)) if eces else None,
        "is_synthetic": is_synthetic,
        "horizon": horizon,
        "model_version": model_version,
        "disclaimer": (
            "SYNTHETIC_NOT_VALIDATED"
            if is_synthetic
            else "Walk-forward concluído. Revisar amostra e horizonte antes de promoção."
        ),
    }
