# drift_monitor.py
# Monitor de drift de dados — pressão, xG, corners, odds, latência, missing/conflict
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

import numpy as np


@dataclass
class DriftAlert:
    feature: str
    metric: str
    value: float
    baseline: float
    threshold: float
    severity: str          # INFO | WARN | CRITICAL
    message: str
    timestamp: float = field(default_factory=time.time)


class FeatureDriftMonitor:
    """
    Monitor simples de drift baseado em média móvel e desvio.
    Não substitui PSI/KL completo — é o primeiro nível operacional.
    """

    def __init__(self, window: int = 120, z_warn: float = 2.5, z_crit: float = 4.0):
        self.window = window
        self.z_warn = z_warn
        self.z_crit = z_crit
        self._hist: Dict[str, Deque[float]] = {}
        self._alerts: Deque[DriftAlert] = deque(maxlen=200)

    def update(self, features: Dict[str, float]) -> List[DriftAlert]:
        alerts: List[DriftAlert] = []
        for name, val in features.items():
            if val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if name not in self._hist:
                self._hist[name] = deque(maxlen=self.window)
            hist = self._hist[name]
            if len(hist) >= 20:
                arr = np.asarray(hist, dtype=np.float64)
                mu, sigma = float(arr.mean()), float(arr.std()) + 1e-9
                z = abs(v - mu) / sigma
                if z >= self.z_crit:
                    a = DriftAlert(name, "zscore", z, mu, self.z_crit, "CRITICAL",
                                   f"{name} drift crítico z={z:.2f}")
                    alerts.append(a)
                    self._alerts.append(a)
                elif z >= self.z_warn:
                    a = DriftAlert(name, "zscore", z, mu, self.z_warn, "WARN",
                                   f"{name} drift z={z:.2f}")
                    alerts.append(a)
                    self._alerts.append(a)
            hist.append(v)
        return alerts

    def missing_rate(self, present: int, expected: int) -> Optional[DriftAlert]:
        if expected <= 0:
            return None
        rate = 1.0 - (present / expected)
        if rate >= 0.35:
            a = DriftAlert("capture", "missing_rate", rate, 0.0, 0.35, "CRITICAL",
                           f"missing_rate={rate:.2%} — fonte possivelmente inativa")
            self._alerts.append(a)
            return a
        if rate >= 0.15:
            a = DriftAlert("capture", "missing_rate", rate, 0.0, 0.15, "WARN",
                           f"missing_rate={rate:.2%}")
            self._alerts.append(a)
            return a
        return None

    def recent_alerts(self, n: int = 20) -> List[DriftAlert]:
        return list(self._alerts)[-n:]

# --- V23 BLOCO 7: drift como bloqueio real ---
PSI_THRESHOLD = 0.25
KS_THRESHOLD = 0.15

def check_feature_drift_block(psi_score: float = 0.0, ks_score: float = 0.0) -> bool:
    """True = BLOQUEAR sinal por drift (dados fora da distribuicao de treino)."""
    try:
        if float(psi_score) > PSI_THRESHOLD or float(ks_score) > KS_THRESHOLD:
            try:
                import logging
                logging.getLogger("aura.drift").warning(
                    "SINAL BLOQUEADO POR DRIFT: PSI=%.3f KS=%.3f", float(psi_score), float(ks_score)
                )
            except Exception:
                pass
            return True
    except Exception:
        return False
    return False
