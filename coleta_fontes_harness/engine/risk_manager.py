# risk_manager.py — Gestão de risco obrigatória antes de stake real
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


def validate_trade_with_market(signal: str, odds_velocity: float, threshold: float = 1.5) -> bool:
    """Filtro Anti-Red (Weight of Money) — v12.6.0.

    Se o sinal for de entrada (BUY_CORNER) mas a odd asiática de escanteios
    estiver subindo acima do threshold (indicando dinheiro indo para o
    Under), o trade é abortado por divergência entre campo e mercado.
    Puramente defensivo: nunca aprova um sinal, só pode vetar um.
    """
    if signal == "BUY_CORNER" and odds_velocity > threshold:
        print(f"[RISK MANAGER] Trade abortado. Motivo: Divergência de Smart Money "
              f"(odds_velocity={odds_velocity:.2f}% > {threshold}%).")
        return False
    return True


@dataclass
class RiskLimits:
    max_stake_pct: float = 0.02          # 2% bankroll por sinal
    max_daily_loss_pct: float = 0.05     # stop diário 5%
    max_signals_per_match: int = 2
    max_signals_per_day: int = 15
    min_prob_corner: float = 0.72
    min_prob_goal: float = 0.75
    min_kelly_stake_pct: float = 0.005   # ignora stake residual
    cooldown_seconds: float = 120.0      # entre sinais na mesma fixture


@dataclass
class RiskState:
    bankroll: float = 1000.0
    daily_pnl: float = 0.0
    day_key: str = ""
    signals_today: int = 0
    signals_per_match: Dict[str, int] = field(default_factory=dict)
    last_signal_ts: Dict[str, float] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self, limits: Optional[RiskLimits] = None, bankroll: float = 1000.0):
        self.limits = limits or RiskLimits()
        self.state = RiskState(bankroll=bankroll)
        self._ensure_day()

    def _ensure_day(self):
        key = time.strftime("%Y-%m-%d")
        if self.state.day_key != key:
            self.state.day_key = key
            self.state.daily_pnl = 0.0
            self.state.signals_today = 0
            self.state.halted = False
            self.state.halt_reason = ""

    def record_pnl(self, pnl: float):
        self._ensure_day()
        self.state.daily_pnl += pnl
        self.state.bankroll += pnl
        if self.state.daily_pnl <= -self.limits.max_daily_loss_pct * (
            self.state.bankroll - self.state.daily_pnl
        ):
            self.state.halted = True
            self.state.halt_reason = "daily_stop_loss"

    def fractional_kelly(self, prob: float, odds: float, fraction: float = 0.25) -> float:
        if odds <= 1.0 or prob <= 0:
            return 0.0
        edge = prob - (1.0 / odds)
        if edge <= 0:
            return 0.0
        raw = (prob * odds - 1.0) / (odds - 1.0)
        stake_pct = max(0.0, min(raw * fraction, self.limits.max_stake_pct))
        if stake_pct < self.limits.min_kelly_stake_pct:
            return 0.0
        return round(stake_pct * 100, 2)  # % da banca

    def approve(
        self,
        fixture_id: str,
        signal: str,
        prob: float,
        odds: float = 1.85,
        odds_velocity: float = 0.0,
    ) -> Dict:
        """Retorna se o sinal pode ser emitido e o stake recomendado."""
        self._ensure_day()
        out = {
            "approved": False,
            "signal": "HOLD",
            "stake_pct": 0.0,
            "reason": "",
        }

        if signal == "HOLD":
            out["reason"] = "hold"
            return out

        if self.state.halted:
            out["reason"] = self.state.halt_reason or "halted"
            return out

        if self.state.signals_today >= self.limits.max_signals_per_day:
            out["reason"] = "max_signals_day"
            return out

        n_match = self.state.signals_per_match.get(fixture_id, 0)
        if n_match >= self.limits.max_signals_per_match:
            out["reason"] = "max_signals_match"
            return out

        last = self.state.last_signal_ts.get(fixture_id, 0)
        if time.time() - last < self.limits.cooldown_seconds:
            out["reason"] = "cooldown"
            return out

        if signal == "BUY_CORNER" and prob < self.limits.min_prob_corner:
            out["reason"] = "prob_below_threshold"
            return out
        if signal == "BUY_GOAL" and prob < self.limits.min_prob_goal:
            out["reason"] = "prob_below_threshold"
            return out

        # v12.6.0 — Filtro Anti-Red (Weight of Money)
        if not validate_trade_with_market(signal, odds_velocity):
            out["reason"] = "smart_money_divergence"
            return out

        stake_pct = self.fractional_kelly(prob, odds)
        if stake_pct <= 0:
            out["reason"] = "no_edge_or_stake"
            return out

        # aprova
        self.state.signals_today += 1
        self.state.signals_per_match[fixture_id] = n_match + 1
        self.state.last_signal_ts[fixture_id] = time.time()
        out.update({"approved": True, "signal": signal, "stake_pct": stake_pct, "reason": "ok"})
        return out


    def calibrate_from_paper(self, min_samples: int = 30) -> Dict:
        """Ajusta thresholds com base em paper trades fechados (offline)."""
        try:
            from data_store import list_closed_trades, save_calibration, paper_summary
            from metrics import brier_score, roi
        except ImportError:
            return {"ok": False, "reason": "import_fail"}

        trades = list_closed_trades(limit=500)
        if len(trades) < min_samples:
            return {
                "ok": False,
                "reason": "insufficient_samples",
                "n": len(trades),
                "need": min_samples,
            }

        corner = [t for t in trades if "CORNER" in (t.get("signal") or "")]
        goal = [t for t in trades if "GOAL" in (t.get("signal") or "")]

        def _best_thresh(subset, default=0.72):
            if len(subset) < 10:
                return default
            best_t, best_roi = default, -1e9
            for t in [0.60, 0.65, 0.70, 0.72, 0.75, 0.78, 0.80, 0.85]:
                sel = [x for x in subset if float(x.get("prob") or 0) >= t]
                if len(sel) < 5:
                    continue
                pnls = [float(x.get("pnl") or 0) for x in sel]
                stakes = [float(x.get("stake_amount") or 1) for x in sel]
                r = roi(pnls, stakes)
                if r > best_roi:
                    best_roi = r
                    best_t = t
            return best_t

        new_corner = _best_thresh(corner, self.limits.min_prob_corner)
        new_goal = _best_thresh(goal, self.limits.min_prob_goal)

        probs = [float(t.get("prob") or 0.5) for t in trades]
        outs = [int(t.get("outcome") or 0) for t in trades]
        brier = brier_score(probs, outs)
        pnls = [float(t.get("pnl") or 0) for t in trades]
        stakes = [float(t.get("stake_amount") or 1) for t in trades]
        r = roi(pnls, stakes)

        if r < 0:
            new_corner = min(0.90, new_corner + 0.03)
            new_goal = min(0.90, new_goal + 0.03)

        self.limits.min_prob_corner = round(new_corner, 3)
        self.limits.min_prob_goal = round(new_goal, 3)

        save_calibration(
            self.limits.min_prob_corner,
            self.limits.min_prob_goal,
            self.limits.max_stake_pct,
            len(trades),
            brier,
            r,
            notes="auto_calibrate_from_paper",
        )
        summary = paper_summary()
        return {
            "ok": True,
            "min_prob_corner": self.limits.min_prob_corner,
            "min_prob_goal": self.limits.min_prob_goal,
            "brier": round(brier, 4),
            "roi": round(r, 4),
            "n": len(trades),
            "paper_summary": summary,
        }

    def load_latest_calibration(self) -> bool:
        try:
            from data_store import latest_calibration
        except ImportError:
            return False
        cal = latest_calibration()
        if not cal:
            return False
        self.limits.min_prob_corner = float(cal.get("min_prob_corner") or self.limits.min_prob_corner)
        self.limits.min_prob_goal = float(cal.get("min_prob_goal") or self.limits.min_prob_goal)
        self.limits.max_stake_pct = float(cal.get("max_stake_pct") or self.limits.max_stake_pct)
        return True
