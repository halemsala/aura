#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Episodes V10 — memória de casos
======================================
Quando um ciclo fecha HEALTHY, guarda a receita (tools OK) daquela classe.
No próximo CORE_DOWN/CORE_SAFETY, o planner pode reordenar à receita vencedora.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class EpisodeMemory:
    def __init__(self, root: Path):
        self.path = root / "logs_supervisor" / "hermes_episodes.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {"version": 10, "by_class": {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                    self.data.setdefault("by_class", {})
            except Exception:
                pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def remember_success(self, incident: str, tools_ok: List[str], score: int) -> None:
        if not incident or incident in ("HEALTHY", "CAPTURE_ONLY"):
            return
        prev = self.data["by_class"].get(incident, {})
        wins = int(prev.get("wins", 0)) + 1
        self.data["by_class"][incident] = {
            "recipe": tools_ok[:12],
            "wins": wins,
            "last_score": score,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def recipe(self, incident: str) -> Optional[List[str]]:
        rec = self.data.get("by_class", {}).get(incident) or {}
        tools = rec.get("recipe")
        return list(tools) if isinstance(tools, list) and tools else None
