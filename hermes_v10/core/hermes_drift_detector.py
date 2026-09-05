#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision/behavior drift (stdlib statistics)."""
from __future__ import annotations
import sqlite3, statistics, time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Deque, Optional

@dataclass
class DriftAlert:
    kind: str
    metric: str
    current: float
    baseline: float
    severity: float
    recommendation: str

class DriftDetector:
    def __init__(self, db_path: str, baseline_window: int = 100, alert_threshold: float = 0.3):
        self.db_path = str(db_path)
        self.baseline_window = baseline_window
        self.alert_threshold = alert_threshold
        self._conf: Deque[float] = deque(maxlen=baseline_window)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS decisions (ts REAL, agent TEXT, action TEXT, confidence REAL)")
            conn.commit()

    def record_decision(self, confidence: float, agent: str, action: str) -> None:
        self._conf.append(float(confidence))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO decisions VALUES (?,?,?,?)", (time.time(), agent, action, confidence))
            conn.commit()

    def check_decision_drift(self) -> Optional[DriftAlert]:
        if len(self._conf) < min(self.baseline_window, 40):
            return None
        data = list(self._conf)
        split = max(len(data) // 5, 10)
        recent = data[-split:]
        baseline = data[:-split] or data
        recent_mean = statistics.mean(recent)
        baseline_mean = statistics.mean(baseline)
        drift = abs(recent_mean - baseline_mean) / max(baseline_mean, 0.01)
        if drift > self.alert_threshold:
            return DriftAlert(
                "decision", "confidence_mean", round(recent_mean, 3), round(baseline_mean, 3),
                round(min(drift, 1.0), 3),
                "confiança mudou vs baseline — rever prompts/constituição",
            )
        return None

if __name__ == "__main__":
    import tempfile
    d = DriftDetector(str(Path(tempfile.gettempdir()) / "drift.db"), baseline_window=50)
    for i in range(40):
        d.record_decision(0.9, "a", "status")
    for i in range(20):
        d.record_decision(0.2, "a", "status")
    print(asdict(d.check_decision_drift() or DriftAlert("none", "-", 0, 0, 0, "ok")))
