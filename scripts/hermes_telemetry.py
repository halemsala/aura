#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Telemetry V8 — JSONL append-only para memória de longo prazo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class Telemetry:
    def __init__(self, root: Path):
        self.path = root / "logs_supervisor" / "hermes_events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, kind: str, payload: Dict[str, Any]) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def tail(self, n: int = 30) -> list:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            out = []
            for line in lines[-n:]:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
            return out
        except Exception:
            return []
