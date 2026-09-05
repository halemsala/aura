#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Anomaly Detector (patched V37.3.38)
- Tipos sempre Python nativos (bool/float) — evita 500 no FastAPI
- live_missing usa AURA_ROOT e paths reais
- history com maxlen estrito
- IsolationForest so treina com amostras suficientes; score normalizado estavel
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    _HAS_SKLEARN = True
except ImportError:
    IsolationForest = None  # type: ignore
    _HAS_SKLEARN = False

try:
    import structlog
    logger = structlog.get_logger("hermes.anomaly")
except Exception:
    import logging
    logger = logging.getLogger("hermes.anomaly")


def _native(v):
    """Garante tipo JSON-serializavel (nunca numpy.bool_ / numpy scalar)."""
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.generic):
        try:
            return v.item()
        except Exception:
            return float(v)
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _native(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_native(x) for x in v]
    return v


@dataclass
class MetricSnapshot:
    ts: str
    port_down_count: int
    log_mb: float
    live_missing: int
    error_markers: int
    cpu_percent: float = 0.0
    mem_percent: float = 0.0


class AnomalyDetector:
    def __init__(self, root: str = ".", config_path: Optional[str] = None):
        self.root = Path(root).resolve()
        # AURA root (parent of hermes_v10) for live files
        self.aura_root = Path(os.getenv("AURA_ROOT") or (
            self.root.parent if self.root.name == "hermes_v10" else self.root
        )).resolve()
        self.config_path = config_path or str(self.root / "hermes_config_ultra.json")
        self.db_path = self.root / "orchestrator" / "state_checkpoints" / "anomalies.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()
        self._init_db()
        if _HAS_SKLEARN and IsolationForest is not None:
            self.model = IsolationForest(
                contamination=min(0.15, max(0.02, self.contamination)),
                random_state=42,
                n_estimators=80,
            )
        else:
            self.model = None
        self._window_size = 60
        self._history: Deque[MetricSnapshot] = deque(maxlen=self._window_size)
        self._fitted = False

    def _load_config(self):
        defaults = {
            "contamination": 0.08,
            "alert_threshold": 0.85,
            # live_missing removido das features por default (stale paths geravam falso positivo)
            "features": ["port_down_count", "log_mb", "error_markers", "cpu_percent", "mem_percent"],
        }
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            ad = cfg.get("anomaly_detection", {})
            self.contamination = float(ad.get("contamination", defaults["contamination"]))
            self.alert_threshold = float(ad.get("alert_threshold", defaults["alert_threshold"]))
            feats = ad.get("features", defaults["features"])
            # nunca usar so live_missing como feature dominante
            self.features = [f for f in feats if f != "live_missing"] or defaults["features"]
        except Exception:
            self.contamination = defaults["contamination"]
            self.alert_threshold = defaults["alert_threshold"]
            self.features = defaults["features"]

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    snapshot TEXT,
                    score REAL,
                    is_anomaly INTEGER,
                    alert_triggered INTEGER
                )
                """
            )
            conn.commit()

    def _port_listening(self, port: int) -> bool:
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                return s.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            return False

    def collect_snapshot(self) -> MetricSnapshot:
        try:
            import psutil
        except ImportError:
            psutil = None  # type: ignore

        expected_ports = [8080, 8765, 8766, 8777]
        port_down = sum(1 for p in expected_ports if not self._port_listening(p))

        log_dir = self.aura_root / "logs_supervisor"
        log_mb = 0.0
        error_markers = 0
        if log_dir.exists():
            for f in log_dir.glob("*.log"):
                try:
                    log_mb += f.stat().st_size / (1024 * 1024)
                except OSError:
                    pass
            # so ultimas linhas dos logs recentes (evita varrer MB inteiros)
            for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                try:
                    data = log_file.read_text(encoding="utf-8", errors="ignore")[-8000:].lower()
                    for k in ("traceback", "critical", "fatal"):
                        error_markers += data.count(k)
                except Exception:
                    pass

        # live files sob AURA_ROOT (nao sob hermes_v10)
        live_patterns = [
            "bridge/live_latest.json",
            "engine/data/live_state.json",
            "engine/data/agent_states.json",
        ]
        live_missing = 0
        for rel in live_patterns:
            p = self.aura_root / rel
            if not p.exists():
                # glob fallback
                if not list(self.aura_root.glob(rel.replace("live_state.json", "live_*.json"))):
                    live_missing += 1

        cpu = float(psutil.cpu_percent(interval=0.05)) if psutil else 0.0
        mem = float(psutil.virtual_memory().percent) if psutil else 0.0

        return MetricSnapshot(
            ts=datetime.utcnow().isoformat() + "Z",
            port_down_count=int(port_down),
            log_mb=round(float(log_mb), 2),
            live_missing=int(live_missing),
            error_markers=int(min(error_markers, 50)),
            cpu_percent=round(cpu, 1),
            mem_percent=round(mem, 1),
        )

    def detect(self, snapshot: Optional[MetricSnapshot] = None) -> Tuple[bool, float, Dict]:
        """Retorna (is_anomaly: bool, score: float, details: dict) — sempre tipos nativos."""
        snap = snapshot or self.collect_snapshot()
        self._history.append(snap)

        if len(self._history) < 10 or self.model is None:
            details = _native({
                "reason": "insufficient_history" if len(self._history) < 10 else "no_sklearn",
                "samples": len(self._history),
                "snapshot": asdict(snap),
                "score": 0.0,
                "threshold": self.alert_threshold,
                "is_anomaly": False,
                "history_size": len(self._history),
            })
            return False, 0.0, details

        X = np.array(
            [[float(getattr(h, feat, 0) or 0) for feat in self.features] for h in self._history],
            dtype=np.float64,
        )

        # rule-based gate: so considera anomalia se portas down ou erros altos
        rule_hit = snap.port_down_count >= 2 or snap.error_markers >= 20

        try:
            train = X[:-1] if len(X) > 12 else X
            self.model.fit(train)
            self._fitted = True
            raw = float(self.model.score_samples(X[-1:].reshape(1, -1))[0])
            # IsolationForest: valores mais negativos = mais anomalos
            # mapear aproximadamente para [0,1]
            normalized = float(max(0.0, min(1.0, (0.5 - raw))))
        except Exception as exc:
            logger.warning("anomaly_fit_failed error=%s", exc)
            normalized = 0.0
            rule_hit = rule_hit or False

        # exigir regra OU score alto — evita alarme permanente score=1.0
        is_anomaly = bool(rule_hit and normalized >= self.alert_threshold) or bool(
            snap.port_down_count >= 3
        )
        if not rule_hit and normalized >= 0.95:
            # score max sem regra = degradar para aviso, nao anomalia
            is_anomaly = False
            normalized = min(normalized, 0.7)

        is_anomaly = bool(is_anomaly)
        normalized = float(normalized)

        result = _native({
            "snapshot": asdict(snap),
            "score": round(normalized, 4),
            "threshold": float(self.alert_threshold),
            "is_anomaly": is_anomaly,
            "history_size": int(len(self._history)),
            "features": list(self.features),
            "rule_hit": bool(rule_hit),
        })

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO anomalies (ts, snapshot, score, is_anomaly, alert_triggered) VALUES (?, ?, ?, ?, ?)",
                    (snap.ts, json.dumps(asdict(snap)), normalized, int(is_anomaly), int(is_anomaly)),
                )
                conn.commit()
        except Exception:
            pass

        if is_anomaly:
            logger.warning("anomaly_detected score=%s port_down=%s", normalized, snap.port_down_count)

        return is_anomaly, normalized, result

    def get_recent(self, hours: int = 24) -> List[Dict]:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM anomalies WHERE ts > ? ORDER BY ts DESC LIMIT 100",
                (since,),
            ).fetchall()
        return [_native(dict(r)) for r in rows]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    det = AnomalyDetector(root=args.root)
    is_a, sc, det_details = det.detect()
    print(json.dumps(det_details, indent=2, ensure_ascii=False))
    print("types", type(is_a).__name__, type(sc).__name__)
