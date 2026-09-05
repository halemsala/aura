"""
Módulo 1 — Auto-backtest + alerta ROI no close
Arquivo único, produção. Integra com data_store + backtest_engine + metrics.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

DB_DEFAULT = "aura_quant_x.db"
SNAPSHOT_PATH = Path("metrics_snapshot.json")


def run_auto_backtest(db_path: str = DB_DEFAULT) -> Dict[str, Any]:
    """Executa backtest completo e retorna métricas + alerta."""
    try:
        from backtest_engine import load_from_sqlite, run_backtest
    except ImportError:
        from engine.backtest_engine import load_from_sqlite, run_backtest  # type: ignore

    rows = load_from_sqlite(db_path)
    if not rows:
        return {
            "ok": False,
            "n_trades": 0,
            "message": "sem outcomes fechados",
            "alert": None,
        }

    result = run_backtest(rows)
    if not isinstance(result, dict) or "error" in result:
        return {"ok": False, "error": result.get("error") if isinstance(result, dict) else "backtest_fail"}

    roi = result.get("roi")
    alert = None
    if roi is not None and roi < 0:
        alert = "ROI negativo — revisar thresholds ou pausar paper"
    elif result.get("max_drawdown") is not None and result["max_drawdown"] > 0.25:
        alert = "Drawdown > 25% — reduzir stake ou subir min_prob"

    out = {
        "ok": True,
        "ts": time.time(),
        "n_trades": result.get("n_trades"),
        "hit_rate": result.get("hit_rate"),
        "brier": result.get("brier"),
        "roi": roi,
        "max_drawdown": result.get("max_drawdown"),
        "profit_factor": result.get("profit_factor"),
        "total_pnl": result.get("total_pnl"),
        "alert": alert,
    }
    _persist_snapshot(out)
    return out


def _persist_snapshot(data: Dict[str, Any]) -> None:
    try:
        SNAPSHOT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_last_snapshot() -> Optional[Dict[str, Any]]:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def on_trade_closed(db_path: str = DB_DEFAULT) -> Dict[str, Any]:
    """Chamado automaticamente após resolve_paper_trade /api/outcome."""
    return run_auto_backtest(db_path)
