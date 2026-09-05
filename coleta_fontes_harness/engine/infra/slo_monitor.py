# engine/infra/slo_monitor.py — V23 burn-rate SLO alerts
from __future__ import annotations
import logging
import time
from typing import Dict, List

logger = logging.getLogger("aura.slo")


class SLOMonitor:
    def __init__(self, target_success_rate: float = 0.99, window_seconds: float = 300.0):
        self.target = float(target_success_rate)
        self.window = float(window_seconds)
        self.attempts: List[Dict] = []
        self.last_alert_time = 0.0

    def record_success(self) -> None:
        self.attempts.append({"ts": time.time(), "ok": True})

    def record_failure(self) -> None:
        self.attempts.append({"ts": time.time(), "ok": False})

    def check_burn_rate(self) -> bool:
        now = time.time()
        self.attempts = [a for a in self.attempts if now - a["ts"] < self.window]
        if not self.attempts:
            return False
        current_rate = sum(1 for a in self.attempts if a["ok"]) / len(self.attempts)
        if current_rate < (self.target * 0.90):
            if now - self.last_alert_time > 60:
                logger.critical(
                    "SLO BURN RATE ALTO! sucesso=%.2f alvo=%.2f",
                    current_rate,
                    self.target,
                )
                self.last_alert_time = now
                return True
        return False


slo_monitor = SLOMonitor()
