#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes RAG V9 — recuperação sobre JSONL + runbooks + KB
=======================================================
Zero vector DB. TF + sobreposição de tokens. Serve o nó DIAGNOSE.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9_]{3,}", (text or "").lower()))


def retrieve(root: Path, query: str, kb_hits: List[str], top_k: int = 4) -> List[Dict[str, str]]:
    docs: List[Dict[str, str]] = []
    q = _tokens(query + " " + " ".join(kb_hits))
    events = root / "logs_supervisor" / "hermes_events.jsonl"
    if events.exists():
        try:
            lines = events.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
            for line in lines:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                blob = json.dumps(rec, ensure_ascii=False)
                docs.append({"src": "event", "title": str(rec.get("kind", "event")), "body": blob[:240]})
        except Exception:
            pass
    rb = root / "logs_supervisor" / "runbooks" / "RUNBOOK_LATEST.md"
    if rb.exists():
        try:
            docs.append({"src": "runbook", "title": "RUNBOOK_LATEST", "body": rb.read_text(encoding="utf-8", errors="replace")[:600]})
        except Exception:
            pass
    scored = []
    for doc in docs:
        bag = _tokens(doc["title"] + " " + doc["body"])
        inter = q & bag
        if not inter:
            continue
        score = len(inter) / max(1, len(q)) + 0.08 * len(inter)
        scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, doc in scored[:top_k]:
        out.append({"src": doc["src"], "title": doc["title"], "score": f"{score:.3f}", "body": doc["body"][:160]})
    return out
