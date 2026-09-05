# engine/agents_glm/roi_auditor_agent.py
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("aura.agent.roi")
DB_PATH = Path("engine/data/tips_intel.db")


class ROIAuditorAgent:
    def __init__(self):
        self.db_path = DB_PATH

    def get_daily_stats(self, days: int = 1) -> dict:
        if not self.db_path.exists():
            return {"error": "Banco de dados de tips nao encontrado."}
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        limit_date = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute(
            "SELECT market, odd, status FROM market_tips WHERE timestamp >= ? AND status != 'PENDING'",
            (limit_date,),
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            return {"error": "Nenhuma dica finalizada neste periodo."}

        total_tips = len(rows)
        wins, losses, voids = 0, 0, 0
        total_staked = float(total_tips)
        total_return = 0.0
        market_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "roi": 0.0, "tips": 0})

        for market, odd, status in rows:
            market_stats[market]["tips"] += 1
            if status == "WIN":
                wins += 1
                total_return += (odd * 1.0) - 1.0
                market_stats[market]["wins"] += 1
            elif status == "LOSS":
                losses += 1
                total_return -= 1.0
                market_stats[market]["losses"] += 1
            elif status == "VOID":
                voids += 1
                total_staked -= 1.0

        roi_general = (total_return / total_staked * 100) if total_staked > 0 else 0.0
        hit_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

        for market, stats in market_stats.items():
            m_staked = stats["wins"] + stats["losses"]
            m_return = (stats["wins"] * 1.5) - m_staked  # aproximacao
            stats["roi"] = (m_return / m_staked * 100) if m_staked > 0 else 0.0

        best_market = max(market_stats.items(), key=lambda x: x[1]["roi"], default=(None, None))
        return {
            "total_tips": total_tips,
            "wins": wins,
            "losses": losses,
            "voids": voids,
            "hit_rate": hit_rate,
            "roi": roi_general,
            "best_market": best_market[0] if best_market else "Nenhum",
            "market_stats": dict(market_stats),
        }


ROI_AUDITOR = ROIAuditorAgent()
