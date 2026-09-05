from __future__ import annotations
import logging
from collections import deque
from typing import Deque, Dict, Literal, Optional

logger = logging.getLogger("feature_flag")
Mode = Literal["PYTHON_SAFE", "NATIVE", "EBPF"]

class SafeFeatureFlag:
    WINDOW = 500

    def __init__(self) -> None:
        self.mode: Mode = "PYTHON_SAFE"
        self._parse_ok: Deque[int] = deque(maxlen=self.WINDOW)
        self._native_ok: Deque[int] = deque(maxlen=self.WINDOW)

    def record_tick(self, python_parsed: bool, native_parsed: Optional[bool] = None) -> None:
        self._parse_ok.append(1 if python_parsed else 0)
        if native_parsed is not None:
            self._native_ok.append(1 if native_parsed else 0)

    def evaluate_swap(self, new_module_performance: Dict[str, float], old_module_performance: Dict[str, float]) -> Mode:
        if len(self._native_ok) < self.WINDOW:
            logger.info("hotswap denied: window %s/%s", len(self._native_ok), self.WINDOW)
            self.mode = "PYTHON_SAFE"
            return self.mode
        native_err = 1.0 - (sum(self._native_ok) / len(self._native_ok))
        py_err = 1.0 - (sum(self._parse_ok) / max(len(self._parse_ok), 1))
        # require exactly 0% parse error on native vs python agreement window
        agreement = sum(1 for a, b in zip(self._parse_ok, self._native_ok) if a == b) / len(self._native_ok)
        if native_err == 0.0 and agreement == 1.0 and new_module_performance.get("latency_ms", 999) <= old_module_performance.get("latency_ms", 0) * 1.05:
            self.mode = "NATIVE"
            logger.info("hotswap approved -> NATIVE")
        else:
            self.mode = "PYTHON_SAFE"
            logger.warning("hotswap denied: native_err=%.4f agreement=%.4f", native_err, agreement)
        return self.mode
