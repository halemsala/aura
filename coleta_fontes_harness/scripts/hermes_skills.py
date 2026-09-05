#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loader de skills locais. Rejeita pacote sem manifesto. Sem rede."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


REQUIRED = ("id", "version", "risk_level", "writes_external", "human_approval")


@dataclass
class SkillPack:
    id: str
    version: str
    risk_level: str
    writes_external: bool
    human_approval: bool
    path: str
    enabled: bool
    reason: str = ""


def _roots(aura_root: Path) -> List[Path]:
    here = Path(__file__).resolve().parents[1] / "skills"
    return [here, aura_root / "skills"]


def load_skills(aura_root: Path) -> List[SkillPack]:
    seen = set()
    out: List[SkillPack] = []
    for base in _roots(aura_root):
        if not base.is_dir():
            continue
        for man in sorted(base.glob("*/manifest.json")):
            try:
                data = json.loads(man.read_text(encoding="utf-8"))
            except Exception as e:
                out.append(SkillPack("?", "0", "high", True, True, str(man.parent), False, f"json:{e}"))
                continue
            missing = [k for k in REQUIRED if k not in data]
            sid = str(data.get("id") or man.parent.name)
            if sid in seen:
                continue
            seen.add(sid)
            if missing:
                out.append(SkillPack(sid, str(data.get("version", "")), "high", True, True,
                                     str(man.parent), False, "missing:" + ",".join(missing)))
                continue
            if data.get("writes_external") is True and not data.get("human_approval"):
                out.append(SkillPack(sid, str(data["version"]), str(data["risk_level"]), True, False,
                                     str(man.parent), False, "external_without_approval"))
                continue
            out.append(SkillPack(
                id=sid,
                version=str(data["version"]),
                risk_level=str(data["risk_level"]),
                writes_external=bool(data["writes_external"]),
                human_approval=bool(data["human_approval"]),
                path=str(man.parent),
                enabled=True,
            ))
    return out
