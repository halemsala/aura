#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Self-Healing Engine
Auto-correção com limites de taxa, cooldown, confiança e escalonamento.
"""
import os
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Callable
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

logger = structlog.get_logger("hermes.healing")


@dataclass
class HealingAction:
    id: int
    ts: str
    fix_type: str
    target: str
    confidence: float
    result: str
    status: str  # applied, failed, rolled_back


class SelfHealingEngine:
    def __init__(self, root: str = ".", config_path: Optional[str] = None):
        self.root = Path(root).resolve()
        self.config_path = config_path or str(self.root / "hermes_config_ultra.json")
        self.db_path = self.root / "orchestrator" / "state_checkpoints" / "healing.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()
        self._init_db()
        self._handlers: Dict[str, Callable] = {}

    def _load_config(self):
        defaults = {
            "enabled": True,
            "max_auto_fixes_per_hour": 8,
            "confidence_threshold": 0.8,
            "cooldown_minutes": 3,
            "escalate_after_failures": 3,
        }
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            sh = cfg.get("self_healing", {})
            self.enabled = sh.get("enabled", defaults["enabled"])
            self.max_per_hour = sh.get("max_auto_fixes_per_hour", defaults["max_auto_fixes_per_hour"])
            self.confidence_threshold = sh.get("confidence_threshold", defaults["confidence_threshold"])
            self.cooldown_minutes = sh.get("cooldown_minutes", defaults["cooldown_minutes"])
            self.escalate_after = sh.get("escalate_after_failures", defaults["escalate_after_failures"])
        except Exception:
            self.enabled = defaults["enabled"]
            self.max_per_hour = defaults["max_auto_fixes_per_hour"]
            self.confidence_threshold = defaults["confidence_threshold"]
            self.cooldown_minutes = defaults["cooldown_minutes"]
            self.escalate_after = defaults["escalate_after_failures"]

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS healing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    fix_type TEXT,
                    target TEXT,
                    confidence REAL,
                    result TEXT,
                    status TEXT
                )
            """)
            conn.commit()

    def register_handler(self, fix_type: str, handler: Callable):
        """Registra handler para um tipo de correção."""
        self._handlers[fix_type] = handler
        logger.info("healing_handler_registered", fix_type=fix_type)

    def _count_recent(self, minutes: int = 60) -> int:
        since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM healing_log WHERE ts > ?",
                (since,)
            ).fetchone()
        return row[0]

    def _last_fix_ts(self) -> Optional[datetime]:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT ts FROM healing_log ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        if row:
            return datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        return None

    def _consecutive_failures(self, fix_type: str) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT status FROM healing_log WHERE fix_type = ? ORDER BY ts DESC LIMIT ?",
                (fix_type, self.escalate_after * 2)
            ).fetchall()
        count = 0
        for (status,) in rows:
            if status == "failed":
                count += 1
            else:
                break
        return count

    async def attempt_fix(self, fix_type: str, target: str, confidence: float, context: Optional[Dict] = None) -> Dict:
        """Tenta aplicar correção com todas as salvaguardas."""
        if not self.enabled:
            return {"status": "skipped", "reason": "self_healing_disabled"}

        if confidence < self.confidence_threshold:
            return {"status": "skipped", "reason": f"confidence {confidence} < threshold {self.confidence_threshold}"}

        if self._count_recent(60) >= self.max_per_hour:
            return {"status": "skipped", "reason": f"max fixes per hour ({self.max_per_hour}) reached"}

        last = self._last_fix_ts()
        if last and (datetime.utcnow() - last).total_seconds() < self.cooldown_minutes * 60:
            return {"status": "skipped", "reason": f"cooldown active ({self.cooldown_minutes} min)"}

        if self._consecutive_failures(fix_type) >= self.escalate_after:
            return {"status": "escalated", "reason": f"{self.escalate_after} falhas consecutivas em {fix_type}"}

        handler = self._handlers.get(fix_type)
        if not handler:
            return {"status": "failed", "reason": f"no handler for {fix_type}"}

        ts = datetime.utcnow().isoformat() + "Z"
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(target, context or {})
            else:
                result = handler(target, context or {})
            status = "applied" if result.get("success") else "failed"
        except Exception as e:
            result = {"success": False, "error": str(e)}
            status = "failed"

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO healing_log (ts, fix_type, target, confidence, result, status) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, fix_type, target, confidence, json.dumps(result), status)
            )
            conn.commit()

        logger.info("healing_attempt", fix_type=fix_type, target=target, status=status, confidence=confidence)
        return {"status": status, "result": result, "confidence": confidence}

    def get_log(self, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM healing_log ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# Handlers padrão
async def handler_domain_lock(target: str, ctx: Dict) -> Dict:
    """Garante que EXECUTION_ALLOWED=false e PAPER_TRADE=true."""
    os.environ["EXECUTION_ALLOWED"] = "false"
    os.environ["PAPER_TRADE"] = "true"
    return {"success": True, "action": "env_locked", "target": target}


async def handler_rotate_logs(target: str, ctx: Dict) -> Dict:
    """Rotaciona logs antigos."""
    from pathlib import Path
    log_dir = Path(target) / "logs_supervisor"
    rotated = 0
    for f in log_dir.glob("*.log"):
        if f.stat().st_size > 10 * 1024 * 1024:  # > 10MB
            new_name = f"{f.stem}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"
            f.rename(log_dir / new_name)
            rotated += 1
    return {"success": True, "rotated": rotated}


async def handler_set_execution_false(target: str, ctx: Dict) -> Dict:
    """Dry-run: reporta ficheiros que mencionam EXECUTION_ALLOWED=true. Não reescreve."""
    from pathlib import Path
    root = Path(target)
    matches = []
    for ext in (".bat", ".env"):
        for f in root.rglob(f"*{ext}"):
            try:
                text = f.read_text(encoding="utf-8")
                if "EXECUTION_ALLOWED=true" in text or "PAPER_TRADE=false" in text:
                    matches.append(str(f))
            except Exception:
                pass
    return {"success": True, "files_changed": 0, "dry_run": True, "matches": matches[:50]}


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--fix", default="domain_lock")
    args = parser.parse_args()

    engine = SelfHealingEngine(root=args.root)
    engine.register_handler("domain_lock", handler_domain_lock)
    engine.register_handler("rotate_logs", handler_rotate_logs)
    engine.register_handler("set_execution_false", handler_set_execution_false)

    result = await engine.attempt_fix(args.fix, target=str(engine.root), confidence=0.95)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
