#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Memory V7 — sucessos, falhas com cooldown e decaimento."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class FixMemory:
    """Memória persistente. Sucessos sobem prioridade; falhas geram cooldown."""

    def __init__(self, root: Path):
        self.path = root / "logs_supervisor" / "hermes_memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {
            "version": 7,
            "fixes": {},
            "failures": {},
            "stats": {"hits": 0, "saves": 0, "fails": 0, "cooldowns": 0},
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                    self.data.setdefault("fixes", {})
                    self.data.setdefault("failures", {})
                    self.data.setdefault("stats", {})
            except Exception:
                pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def recall(self, fp: str) -> Optional[Dict[str, Any]]:
        f = self.data.get("fixes", {}).get(fp)
        if f:
            self.data["stats"]["hits"] = int(self.data["stats"].get("hits", 0)) + 1
            self.save()
        return f

    def in_cooldown(self, fp: str, seconds: int = 180) -> bool:
        rec = self.data.get("failures", {}).get(fp)
        if not rec:
            return False
        try:
            ts = datetime.fromisoformat(str(rec.get("ts", "")).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age < seconds:
                self.data["stats"]["cooldowns"] = int(self.data["stats"].get("cooldowns", 0)) + 1
                self.save()
                return True
        except Exception:
            return False
        return False

    def remember(self, fp: str, action: str, detail: Dict[str, Any], ok: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if ok:
            prev = self.data.get("fixes", {}).get(fp, {})
            self.data.setdefault("fixes", {})[fp] = {
                "action": action,
                "detail": detail,
                "ts": now,
                "success_count": int(prev.get("success_count", 0)) + 1,
            }
            self.data["stats"]["saves"] = int(self.data["stats"].get("saves", 0)) + 1
            self.data.get("failures", {}).pop(fp, None)
        else:
            prev = self.data.get("failures", {}).get(fp, {})
            self.data.setdefault("failures", {})[fp] = {
                "action": action,
                "detail": detail,
                "ts": now,
                "fail_count": int(prev.get("fail_count", 0)) + 1,
            }
            self.data["stats"]["fails"] = int(self.data["stats"].get("fails", 0)) + 1
        self.save()
