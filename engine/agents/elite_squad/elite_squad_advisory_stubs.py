"""AURA Elite Squad — advisory stubs (paper-only). No Telegram, no YAML write, no network."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Default limits for janitor
DEFAULT_LIMITS: dict[str, tuple[float, float]] = {
    "attack_pressure_diff": (-100.0, 100.0),
    "dangerous_attacks_home": (0.0, 200.0),
    "corner_rate_15min": (0.0, 15.0),
    "minute": (0.0, 130.0),
    "corners": (0.0, 50.0),
    "shots_off_target": (0.0, 50.0),
}


@dataclass
class DataJanitor:
    limits: dict[str, tuple[float, float]] = field(default_factory=lambda: dict(DEFAULT_LIMITS))

    def sanitize_feed(self, raw: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        rejected: list[dict[str, Any]] = []
        for k, v in raw.items():
            if k in self.limits and isinstance(v, (int, float)):
                lo, hi = self.limits[k]
                if not (lo <= float(v) <= hi):
                    rejected.append({"key": k, "value": v, "reason": f"out_of_range[{lo},{hi}]"})
                    continue
            clean[k] = v
        return {"ok": True, "clean": clean, "rejected_keys": rejected}


@dataclass
class RedTeamAdversary:
    def audit_decision(self, features: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        ap = float(features.get("attack_pressure_diff") or 0)
        minute = float(features.get("minute") or 0)
        odd = float(proposal.get("odd") or 0)
        score = str(features.get("score") or "")
        shots_off = float(features.get("shots_off_target") or 0)
        corners = float(features.get("corners") or 0)

        if odd in (9.0, 10.0, 11.0) and ap < 20:
            reasons.append("Linha .0 com pressão insuficiente.")
        if score == "0-0" and minute > 85:
            reasons.append("Kill zone: risco de golo tardio.")
        if corners > 0 and shots_off > corners * 3:
            reasons.append("Domínio estéril (remates longe vs cantos).")

        vetoed = bool(reasons)
        prop_dec = str(proposal.get("decision") or "AGUARDA")
        effective = "AGUARDA" if vetoed and prop_dec == "ENTRA" else prop_dec
        if vetoed and prop_dec == "ENTRA":
            effective = "AGUARDA"

        return {
            "verdict": "VETOED" if vetoed else "APPROVED",
            "reasons": reasons or ["Tese sólida (advisory)."],
            "effective_decision": effective,
            "paper_trade": True,
            "execution_allowed": False,
        }


@dataclass
class OnlineThresholdTuner:
    """Produces suggestions only; never writes production YAML."""

    recent: deque = field(default_factory=lambda: deque(maxlen=10))
    suggestion_path: Path = field(
        default_factory=lambda: Path("engine/data/threshold_suggestions.json")
    )

    def record_result(self, res: str, minute: float | None = None, score: float | None = None) -> None:
        self.recent.append({"res": res, "m": minute, "s": score})
        if len(self.recent) >= 5:
            self._maybe_suggest()

    def _maybe_suggest(self) -> dict[str, Any]:
        losses = [r for r in self.recent if r["res"] == "LOSS"]
        wins = [r for r in self.recent if r["res"] == "WIN"]
        n = len(self.recent)
        lr = len(losses) / n if n else 0.0
        suggestions: dict[str, float] = {}
        if lr > 0.4:
            suggestions = {"entra_min_score": 75.0, "entra_min_confidence": 0.80}
        elif lr < 0.2 and len(wins) > 5:
            suggestions = {"entra_min_score": 70.0}
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "based_on_n": n,
            "loss_rate": lr,
            "suggestions": suggestions,
            "applied": False,
            "requires_human_approval": True,
        }
        try:
            self.suggestion_path.parent.mkdir(parents=True, exist_ok=True)
            import json

            self.suggestion_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass
        return payload


@dataclass
class PostMatchForensics:
    tuner: OnlineThresholdTuner

    def execute_autopsy(self, trade_data: dict[str, Any], result: str) -> dict[str, Any]:
        result = result.upper()
        if result not in ("WIN", "LOSS", "VOID"):
            return {"ok": False, "summary": "result inválido", "recorded": False, "suggestion_updated": False}
        self.tuner.record_result(result, trade_data.get("minute"), trade_data.get("score"))
        if result == "LOSS":
            summary = f"Falha paper no min {trade_data.get('minute')}."
        elif result == "WIN":
            summary = "Trade paper vencedor."
        else:
            summary = "Trade paper void."
        return {"ok": True, "summary": summary, "recorded": True, "suggestion_updated": True}


@dataclass
class ROIAuditorPaper:
    db_path: Path = field(default_factory=lambda: Path("engine/data/paper_intel.db"))

    def get_daily_stats(self, days: int = 1) -> dict[str, Any]:
        import sqlite3

        if not self.db_path.exists():
            return {"error": "DB not found", "paper_trade": True}
        limit = (datetime.utcnow() - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT market, odd, status FROM paper_trades WHERE timestamp >= ? AND status != 'PENDING'",
                (limit,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as e:
            return {"error": str(e), "paper_trade": True}
        finally:
            conn.close()
        if not rows:
            return {"error": "No paper trades", "paper_trade": True}
        wins = losses = voids = 0
        ret = 0.0
        from collections import defaultdict

        mkt: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "tips": 0})
        for market, odd, status in rows:
            mkt[market]["tips"] += 1
            if status == "WIN":
                wins += 1
                ret += float(odd) - 1.0
                mkt[market]["wins"] += 1
            elif status == "LOSS":
                losses += 1
                ret -= 1.0
                mkt[market]["losses"] += 1
            else:
                voids += 1
        total = len(rows)
        hr = (wins / (wins + losses) * 100) if (wins + losses) else 0.0
        roi = (ret / total * 100) if total else 0.0
        best = max(mkt.items(), key=lambda x: x[1]["wins"], default=(None, None))
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "voids": voids,
            "hit_rate": hr,
            "roi_paper_pct": roi,
            "best_market": best[0],
            "paper_trade": True,
        }


# Singletons for optional import in tests
DATA_JANITOR = DataJanitor()
RED_TEAM = RedTeamAdversary()
ONLINE_TUNER = OnlineThresholdTuner()
FORENSICS = PostMatchForensics(ONLINE_TUNER)
ROI_AUDITOR = ROIAuditorPaper()
