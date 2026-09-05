#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Alert Manager
Notificações multi-canal: webhook, Discord, email (opcional), arquivo.
Com rate limiting, deduplicação e severidade escalonável.
"""
import os
import json
import asyncio
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()
import httpx

logger = structlog.get_logger("hermes.alerts")

@dataclass
class Alert:
    id: str
    ts: str
    severity: str  # info, warning, critical, emergency
    source: str
    message: str
    metadata: Dict
    acknowledged: bool = False

class AlertManager:
    SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.db_path = self.root / "data" / "memory" / "alerts.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.webhook_url = os.getenv("HERMES_ALERT_WEBHOOK")
        self.discord_url = os.getenv("HERMES_DISCORD_WEBHOOK")
        self._recent_alerts: Dict[str, datetime] = {}  # dedup in-memory
        self._rate_limit_minutes = 5

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    ts TEXT,
                    severity TEXT,
                    source TEXT,
                    message TEXT,
                    metadata TEXT,
                    acknowledged INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_ts ON alerts(ts)")
            conn.commit()

    def _alert_hash(self, source: str, message: str) -> str:
        return hashlib.sha256(f"{source}:{message}".encode()).hexdigest()[:16]

    def _is_rate_limited(self, alert_hash: str) -> bool:
        last = self._recent_alerts.get(alert_hash)
        if last and (datetime.utcnow() - last).total_seconds() < self._rate_limit_minutes * 60:
            return True
        self._recent_alerts[alert_hash] = datetime.utcnow()
        return False

    async def send(self, severity: str, source: str, message: str, metadata: Optional[Dict] = None):
        alert_hash = self._alert_hash(source, message)

        if self._is_rate_limited(alert_hash):
            logger.debug("alert_rate_limited", source=source, severity=severity)
            return

        alert = Alert(
            id=f"alert_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            ts=datetime.utcnow().isoformat() + "Z",
            severity=severity,
            source=source,
            message=message,
            metadata=metadata or {},
        )

        # Persist
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO alerts (id, ts, severity, source, message, metadata, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (alert.id, alert.ts, alert.severity, alert.source, alert.message,
                  json.dumps(alert.metadata), int(alert.acknowledged)))
            conn.commit()

        # Dispatch
        tasks = []
        if self.webhook_url:
            tasks.append(self._send_webhook(alert))
        if self.discord_url and self.SEVERITY_ORDER.get(severity, 0) >= 1:
            tasks.append(self._send_discord(alert))

        # Always log to file
        tasks.append(self._send_file(alert))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.warning("alert_sent", severity=severity, source=source, message=message[:100])

    async def _send_webhook(self, alert: Alert):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.webhook_url, json={
                    "severity": alert.severity,
                    "source": alert.source,
                    "message": alert.message,
                    "ts": alert.ts,
                    "metadata": alert.metadata,
                })
        except Exception as e:
            logger.error("webhook_failed", error=str(e))

    async def _send_discord(self, alert: Alert):
        color_map = {"info": 3447003, "warning": 16776960, "critical": 15158332, "emergency": 16711680}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.discord_url, json={
                    "embeds": [{
                        "title": f"🚨 Hermes Alert — {alert.severity.upper()}",
                        "description": alert.message,
                        "color": color_map.get(alert.severity, 0),
                        "fields": [
                            {"name": "Source", "value": alert.source, "inline": True},
                            {"name": "Time", "value": alert.ts, "inline": True},
                        ],
                        "footer": {"text": "Hermes V10 Ultra"},
                    }]
                })
        except Exception as e:
            logger.error("discord_failed", error=str(e))

    async def _send_file(self, alert: Alert):
        log_path = self.root / "logs_supervisor" / "alerts.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": alert.ts,
                "severity": alert.severity,
                "source": alert.source,
                "message": alert.message,
            }, ensure_ascii=False) + "\n")

    def get_unacknowledged(self, min_severity: str = "warning") -> List[Dict]:
        min_level = self.SEVERITY_ORDER.get(min_severity, 1)
        severities = [s for s, v in self.SEVERITY_ORDER.items() if v >= min_level]
        placeholders = ",".join("?" * len(severities))
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM alerts WHERE acknowledged = 0 AND severity IN ({placeholders}) ORDER BY ts DESC",
                tuple(severities)
            ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge(self, alert_id: str):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
            conn.commit()


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--severity", default="warning")
    parser.add_argument("--source", default="cli")
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    mgr = AlertManager(root=args.root)
    await mgr.send(args.severity, args.source, args.message)
    print("Alert sent.")

if __name__ == "__main__":
    asyncio.run(main())
