# engine/agents_glm/elo_rating_agent.py
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("aura.agent.elo")


def _db_path() -> Path:
    root = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[2])
    path = root / "engine" / "data" / "tips_intel.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DB_PATH = _db_path()


class EloRatingAgent:
    def __init__(self, base_elo=1500, k_factor=30):
        self.k = k_factor
        self._init_db()

    def _init_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS team_elo (team_name TEXT PRIMARY KEY, elo REAL)"
        )
        conn.commit()
        conn.close()

    def get_elo(self, team: str) -> float:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT elo FROM team_elo WHERE team_name = ?", (team,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 1500.0

    def update_elo(self, winner: str, loser: str, draw: bool = False):
        elo_w = self.get_elo(winner)
        elo_l = self.get_elo(loser)
        exp_w = 1 / (1 + 10 ** ((elo_l - elo_w) / 400))
        score_w = 0.5 if draw else 1.0
        new_elo_w = elo_w + self.k * (score_w - exp_w)
        new_elo_l = elo_l + self.k * ((0.5 if draw else 0.0) - (1 - exp_w))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO team_elo (team_name, elo) VALUES (?, ?)",
            (winner, new_elo_w),
        )
        c.execute(
            "INSERT OR REPLACE INTO team_elo (team_name, elo) VALUES (?, ?)",
            (loser, new_elo_l),
        )
        conn.commit()
        conn.close()

    def inspect(self, home: str, away: str, market_odd_home: float) -> dict:
        elo_h = self.get_elo(home)
        elo_a = self.get_elo(away)
        exp_home = 1 / (1 + 10 ** ((elo_a - elo_h) / 400))
        fair_odd_home = 1 / exp_home if exp_home > 0 else 999.0
        value = bool(market_odd_home and market_odd_home > fair_odd_home)
        return {
            "home": home,
            "away": away,
            "elo_home": elo_h,
            "elo_away": elo_a,
            "p_home": exp_home,
            "fair_odd_home": fair_odd_home,
            "market_odd_home": market_odd_home,
            "value": value,
            "paper_trade": True,
            "execution_allowed": False,
            "detail": (
                f"VALUE DETECTADO: Odd mercado ({market_odd_home}) > Odd Justa ({fair_odd_home:.2f})."
                if value
                else f"Sem value. Odd justa {fair_odd_home:.2f} vs mercado {market_odd_home}."
            ),
        }

    def find_value(self, home: str, away: str, market_odd_home: float) -> str:
        return self.inspect(home, away, market_odd_home)["detail"]


ELO_AGENT = EloRatingAgent()
