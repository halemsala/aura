# engine/agents_glm/general_intel_db.py
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aura.intel.db")
DB_PATH = Path("engine/data/tips_intel.db")


class GeneralIntelDB:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS market_tips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                raw_text TEXT,
                home_team TEXT,
                away_team TEXT,
                market TEXT,
                odd REAL,
                implied_prob REAL,
                aura_validation TEXT,
                timestamp TEXT,
                status TEXT DEFAULT 'PENDING',
                match_time TEXT
            )
            """
        )
        for col, typedef in [("status", "TEXT DEFAULT 'PENDING'"), ("match_time", "TEXT")]:
            try:
                c.execute(f"ALTER TABLE market_tips ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def save_tip(self, source: str, raw: str, home: str, away: str, market: str, odd: float, validation: str) -> float:
        implied_prob = (1 / odd * 100) if odd and odd > 0 else 0
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """INSERT INTO market_tips
               (source, raw_text, home_team, away_team, market, odd, implied_prob, aura_validation, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, raw, home, away, market, odd, implied_prob, validation, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        logger.info("Tip salvo: %s x %s - %s (%s)", home, away, market, odd)
        return implied_prob

    def update_tip_status(self, tip_id: int, status: str):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE market_tips SET status = ? WHERE id = ?", (status.upper(), tip_id))
        conn.commit()
        conn.close()


INTEL_DB = GeneralIntelDB()
