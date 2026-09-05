#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Auditor V8 — deriva de código vs baseline CLEAN 12.7
==========================================================
Não escreve no engine. Só prova se os patches conhecidos existem.
Fonte de verdade do domínio: skill AURA QUANT-X.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class AuditHit:
    code: str
    ok: bool
    file: str
    message: str
    hint: str = ""


CHECKS = (
    ("engine/grounding.py", "view.get(\"corner_events\")",
     "GROUNDING_READS_VIEW", "grounding.py lê view.corner_events",
     "Rever engine/grounding.py — snap/view + corner_events"),
    ("engine/grounding.py", "snap.get(\"home\")",
     "GROUNDING_READS_SNAP", "grounding.py lê snap.home",
     "Lift snapshot.view no card factual"),
    ("engine/features.py", "_as_side_dict",
     "FEATURES_SIDE_DICT", "features.py aceita dict e lista [h,a]",
     "Gate dangerous.home deve aceitar lista"),
    ("engine/server.py", "def _fixture_context",
     "SERVER_FIXTURE_CONTEXT", "server.py tem _fixture_context",
     "Chat precisa de lift view/payload"),
    ("engine/server.py", "_snapshot_for_engine",
     "SERVER_SNAPSHOT_LIFT", "server.py tem _snapshot_for_engine",
     "Sem lift, ui/state e chat divergem"),
    ("engine/server.py", "PAPER_TRADE must be true",
     "SERVER_PAPER_GUARD", "server.py aborta se paper_trade != true",
     "Guard de arranque do Engine"),
)


def audit_tree(root: Path) -> List[AuditHit]:
    hits: List[AuditHit] = []
    for rel, needle, code, ok_msg, hint in CHECKS:
        path = root / rel
        if not path.exists():
            hits.append(AuditHit(code, False, rel, f"ausente {rel}", hint))
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            hits.append(AuditHit(code, False, rel, f"ilegal ler {rel}: {e}", hint))
            continue
        if needle in text:
            hits.append(AuditHit(code, True, rel, ok_msg, ""))
        else:
            hits.append(AuditHit(
                code, False, rel,
                f"deriva: falta `{needle}` em {rel}",
                hint,
            ))
    return hits
