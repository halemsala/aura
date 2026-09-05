from __future__ import annotations
import json
import logging
import sqlite3
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("zombie_escalator")

try:
    import zmq
    ZMQ_OK = True
except ImportError:
    ZMQ_OK = False

class DirectorZombieEscalator:
    def __init__(self, db_path: str = "aura_quant_x.db", zmq_port: int = 5560) -> None:
        self.db_path = db_path
        self.zmq_port = zmq_port
        self.priority = 10  # P10 default
        self._background_paused = False

    def count_telemetry_last_seconds(self, seconds: int = 30) -> int:
        try:
            conn = sqlite3.connect(self.db_path, timeout=2.0)
            cur = conn.cursor()
            # support both timestamp_unix and timestamp
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM logs_telemetria WHERE timestamp_unix >= ?",
                    (int(time.time()) - seconds,),
                )
            except Exception:
                cur.execute(
                    "SELECT COUNT(*) FROM logs_telemetria WHERE timestamp >= ?",
                    (time.time() - seconds,),
                )
            n = int(cur.fetchone()[0])
            conn.close()
            return n
        except Exception:
            return -1

    def check_and_escalate(self, match_minute: float) -> Dict[str, Any]:
        live = 0.0 <= float(match_minute) <= 90.0
        inserts = self.count_telemetry_last_seconds(30)
        if live and inserts == 0:
            self.priority = 0
            self._background_paused = True
            alert = {
                "alert_type": "QUANT_ENGINE_ZOMBIE",
                "priority": 0,
                "match_minute": match_minute,
                "telemetry_inserts_30s": inserts,
                "action": "RESTART_ENGINE_IMMEDIATE",
                "voice_instruction": "Alerta crítico. Motor quant sem telemetria há 30 segundos. Reinício imediato exigido.",
            }
            self._publish_critical(alert)
            logger.critical("ZOMBIE ESCALATION P0: %s", alert)
            return {"escalated": True, "priority": 0, "alert": alert, "pause_background": True}
        self.priority = 10
        self._background_paused = False
        return {"escalated": False, "priority": 10, "telemetry_inserts_30s": inserts}

    def _publish_critical(self, payload: Dict[str, Any]) -> None:
        if not ZMQ_OK:
            return
        try:
            ctx = zmq.Context.instance()
            sock = ctx.socket(zmq.PUB)
            sock.setsockopt(zmq.LINGER, 0)
            try:
                sock.bind(f"tcp://127.0.0.1:{self.zmq_port}")
            except zmq.ZMQError:
                sock.connect(f"tcp://127.0.0.1:{self.zmq_port}")
            time.sleep(0.05)
            sock.send_string("critical::" + json.dumps(payload, ensure_ascii=False))
            sock.close(0)
        except Exception as e:
            logger.error("publish critical failed: %s", e)

    @property
    def background_paused(self) -> bool:
        return self._background_paused
