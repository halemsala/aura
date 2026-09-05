"""
Módulo 3 — Calibração automática de min_prob / Kelly
Dispara quando n>=30 e ROI < 0 (ou sob demanda).
"""
from __future__ import annotations
from typing import Any, Dict, Optional


def maybe_auto_calibrate(
    risk_manager,
    min_samples: int = 30,
    force: bool = False,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Se ROI negativo e amostra suficiente, recalibra thresholds.
    Retorna resultado da calibração ou skip reason.
    """
    if metrics is None:
        try:
            from modules.auto_backtest_on_close import load_last_snapshot, run_auto_backtest
            metrics = load_last_snapshot() or run_auto_backtest()
        except Exception:
            metrics = {}

    n = int(metrics.get("n_trades") or 0)
    roi = metrics.get("roi")

    if not force:
        if n < min_samples:
            return {"ok": False, "reason": "insufficient_samples", "n": n, "need": min_samples}
        if roi is None or roi >= 0:
            return {"ok": False, "reason": "roi_ok_or_missing", "roi": roi}

    try:
        result = risk_manager.calibrate_from_paper(min_samples=min_samples)
        return {"ok": True, "triggered_by": "roi_negative" if not force else "force", **result}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
