#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Meta-Labeling: segundo modelo que decide QUANDO
apostar no sinal primario. Treina em features de contexto para prever
P(sinal primario estar certo). Corta recall, sobe precision.

Implementacao: regressao logistica online (SGD) em Python puro.
Nao precisa de sklearn — matematica suficiente para o problema.

Pipeline:
  1. register(features, primary_p, pred_id) -> armazena pendente
  2. resolve(pred_id, y_outcome) -> treina com (features, y_outcome)
  3. predict(features, primary_p) -> MetaDecision(take_bet)

Green-light: so ativar apos >= 50 resolucoes (min_train).
Antes disso, take_bet=False sempre (nao fabrica confianca).
"""
from __future__ import annotations
import json
import logging
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("aura.meta")
__version__ = "1.0.0"
__all__ = ["MetaLabeler", "MetaFeatures", "MetaDecision"]

DEFAULT_FEATURES = ("drift", "data_age_sec", "pressure",
                     "minute", "gap", "p_primary")


@dataclass
class MetaFeatures:
    drift: float
    data_age_sec: float
    pressure: float
    minute: float
    gap: float
    p_primary: float

    def to_vector(self, names=DEFAULT_FEATURES) -> List[float]:
        return [float(getattr(self, n, 0.0)) for n in names]


@dataclass
class MetaDecision:
    meta_p: float
    primary_p: float
    take_bet: bool
    features: Dict[str, float]
    n_train: int
    ts: str = ""


class MetaLabeler:
    """Regressao logistica online (SGD) com normalizacao rolling."""

    def __init__(self, state_dir=None, *, feature_names=None,
                 meta_threshold: float = 0.55,
                 learning_rate: float = 0.01, l2: float = 0.001,
                 min_train: int = 50, window: int = 1000):
        self.feature_names = list(feature_names or DEFAULT_FEATURES)
        self.threshold = float(meta_threshold)
        self.lr = float(learning_rate)
        self.l2 = float(l2)
        self.min_train = int(min_train)
        self._lock = threading.RLock()
        n_feat = len(self.feature_names)
        self._weights: List[float] = [0.0] * (n_feat + 1)  # +bias
        self._n_train = 0
        self._pending: Dict[str, Tuple[MetaFeatures, float]] = {}
        self._feat_mean = [0.0] * n_feat
        self._feat_m2 = [0.0] * n_feat
        self._loss_history = deque(maxlen=200)
        self._state_dir = Path(state_dir) if state_dir else None
        if self._state_dir:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def _normalize(self, vec: List[float]) -> List[float]:
        out = []
        for i, v in enumerate(vec):
            mean = self._feat_mean[i]
            var = self._feat_m2[i] / max(self._n_train, 1)
            std = math.sqrt(var) if var > 1e-8 else 1.0
            out.append((v - mean) / std)
        return out

    def _update_stats(self, vec: List[float]) -> None:
        n = self._n_train + 1
        for i, v in enumerate(vec):
            delta = v - self._feat_mean[i]
            self._feat_mean[i] += delta / n
            self._feat_m2[i] += delta * (v - self._feat_mean[i])

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def _train_one(self, x: List[float], y: int) -> None:
        x_norm = self._normalize(x)
        x_bias = x_norm + [1.0]
        z = sum(w * xi for w, xi in zip(self._weights, x_bias))
        p = self._sigmoid(z)
        grad = p - y
        for i in range(len(self._weights)):
            self._weights[i] -= self.lr * (
                grad * x_bias[i] + self.l2 * self._weights[i])
        loss = -(y * math.log(max(p, 1e-10))
                 + (1 - y) * math.log(max(1 - p, 1e-10)))
        self._loss_history.append(loss)

    def register(self, features: MetaFeatures, primary_p: float,
                 pred_id: str) -> None:
        with self._lock:
            pid = str(pred_id)
            if pid not in self._pending:
                self._pending[pid] = (features, float(primary_p))
                while len(self._pending) > 5000:
                    self._pending.popitem(last=False)

    def resolve(self, pred_id: str, y: int) -> bool:
        with self._lock:
            pend = self._pending.pop(str(pred_id), None)
            if pend is None:
                return False
            features, _ = pend
            x = features.to_vector(self.feature_names)
            self._update_stats(x)
            self._train_one(x, int(y))
            self._n_train += 1
            if self._state_dir and self._n_train % 25 == 0:
                self._save()
            return True

    def predict(self, features: MetaFeatures,
                primary_p: float) -> MetaDecision:
        with self._lock:
            if self._n_train < self.min_train:
                return MetaDecision(
                    meta_p=0.5, primary_p=primary_p, take_bet=False,
                    features={}, n_train=self._n_train,
                    ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            x = features.to_vector(self.feature_names)
            x_norm = self._normalize(x)
            x_bias = x_norm + [1.0]
            z = sum(w * xi for w, xi in zip(self._weights, x_bias))
            meta_p = self._sigmoid(z)
            return MetaDecision(
                meta_p=meta_p, primary_p=primary_p,
                take_bet=meta_p >= self.threshold,
                features={n: round(v, 4) for n, v in zip(self.feature_names, x)},
                n_train=self._n_train,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def stats(self) -> dict:
        with self._lock:
            avg = (sum(self._loss_history) / len(self._loss_history)
                   if self._loss_history else None)
            return {"n_train": self._n_train, "min_train": self.min_train,
                    "pending": len(self._pending),
                    "weights": [round(w, 4) for w in self._weights],
                    "threshold": self.threshold,
                    "avg_loss": round(avg, 6) if avg else None,
                    "feature_names": list(self.feature_names)}

    def _save(self) -> None:
        if not self._state_dir:
            return
        path = self._state_dir / "meta_labeler_state.json"
        data = {"n_train": self._n_train, "weights": self._weights,
                "feat_mean": self._feat_mean, "feat_m2": self._feat_m2,
                "threshold": self.threshold,
                "feature_names": self.feature_names}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(path))

    def _load(self) -> None:
        path = self._state_dir / "meta_labeler_state.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._weights = list(data["weights"])
            self._feat_mean = list(data["feat_mean"])
            self._feat_m2 = list(data["feat_m2"])
            self._n_train = int(data["n_train"])
            self.threshold = float(data.get("threshold", self.threshold))
        except Exception:
            log.exception("[meta] carga do estado falhou")

    def close(self) -> None:
        with self._lock:
            self._save()


if __name__ == "__main__":
    import random
    import sys
    random.seed(42)
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    ml = MetaLabeler(meta_threshold=0.55, min_train=50, learning_rate=0.05)

    # Cold start
    md = ml.predict(MetaFeatures(0.5, 5, 0.5, 80, 4, 0.7), 0.7)
    check("cold start: take_bet=False", md.take_bet is False)
    check("cold start: meta_p=0.5", abs(md.meta_p - 0.5) < 1e-9)

    # Treina: drift alto + p alto -> y=1; drift baixo -> y=0
    for i in range(200):
        drift = random.choice([0.8, 0.9, 0.1, 0.2])
        p = random.uniform(0.6, 0.85)
        feat = MetaFeatures(drift, random.uniform(1, 10),
                            random.uniform(0.3, 0.7), random.uniform(75, 90),
                            random.uniform(0, 8), p)
        pid = f"t{i}"
        ml.register(feat, p, pid)
        y = 1 if drift > 0.5 and p > 0.65 else 0
        ml.resolve(pid, y)

    st = ml.stats()
    check("treina 200 amostras", st["n_train"] == 200)
    check("loss registrado", st["avg_loss"] is not None and st["avg_loss"] < 1.0)

    md_hi = ml.predict(MetaFeatures(0.85, 3, 0.6, 85, 3, 0.75), 0.75)
    md_lo = ml.predict(MetaFeatures(0.15, 3, 0.4, 85, 3, 0.55), 0.55)
    check("drift alto -> meta_p maior que baixo",
          md_hi.meta_p > md_lo.meta_p,
          f"hi={md_hi.meta_p:.3f} lo={md_lo.meta_p:.3f}")

    # Persistencia
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ml2 = MetaLabeler(state_dir=td, min_train=50)
        for i in range(100):
            ml2.register(MetaFeatures(0.8, 5, 0.5, 80, 3, 0.7), 0.7, f"p{i}")
            ml2.resolve(f"p{i}", 1)
        ml2.close()
        ml3 = MetaLabeler(state_dir=td, min_train=50)
        check("persistencia: n_train restaurado",
              ml3.stats()["n_train"] == 100)

    print(f"\nmeta_labeling selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
