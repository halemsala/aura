#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ToolKnowledge local — base JSONL pequena e fail-closed para o AURA.

Este arquivo preenche a interface que os módulos de pesquisa dos anexos
esperam. Ele não faz scraping nem chamadas de rede: fontes externas devem ser
consultadas pelos adaptadores explícitos e seus resultados podem ser inseridos
com add_text depois de revisão.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__version__ = "1.0.0-local"


def _tokens(text: str) -> List[str]:
    return [x.lower() for x in re.findall(r"[a-zA-ZÀ-ÿ0-9_]{2,}", text or "")]


class ToolKnowledge:
    """Knowledge base local, append-only em JSONL e consultável por tokens."""

    def __init__(self, kb_dir: Any = Path("engine/data/knowledge")):
        self.kb_dir = Path(kb_dir)
        self.path = self.kb_dir / "knowledge.jsonl"
        self._lock = threading.RLock()
        self._docs: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict) and item.get("text"):
                    self._docs.append(item)
        except Exception:
            self._docs = []

    def _flush(self) -> None:
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for item in self._docs:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def add_text(self, title: str, text: str, source: str = "manual",
                 metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        title = str(title or "sem titulo")[:300]
        text = str(text or "")[:200_000]
        source = str(source or "manual")[:500]
        if not text.strip():
            return {"ok": False, "speech": "Texto vazio não foi salvo."}
        digest = hashlib.sha256((title + "\n" + text + "\n" + source).encode(
            "utf-8", errors="replace")).hexdigest()
        with self._lock:
            if any(d.get("id") == digest for d in self._docs):
                return {"ok": True, "id": digest, "duplicate": True}
            item = {"id": digest, "title": title, "text": text,
                    "source": source,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": metadata or {}}
            self._docs.append(item)
            self._flush()
        return {"ok": True, "id": digest, "duplicate": False}

    def query(self, text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        query_tokens = set(_tokens(text))
        if not query_tokens:
            return []
        scored: List[Dict[str, Any]] = []
        with self._lock:
            docs = list(self._docs)
        for item in docs:
            hay = set(_tokens(item.get("title", "") + " " + item.get("text", "")))
            overlap = len(query_tokens & hay)
            if overlap:
                row = dict(item)
                row["score"] = round(overlap / max(1, len(query_tokens)), 4)
                scored.append(row)
        scored.sort(key=lambda item: (-item.get("score", 0), item.get("created_at", "")))
        return scored[:max(1, int(top_k))]

    def list_people(self) -> List[Dict[str, Any]]:
        return []

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"documents": len(self._docs), "path": str(self.path)}



def _self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="aura_kb_") as td:
        kb = ToolKnowledge(Path(td))
        a = kb.add_text("Papers de Poisson", "Poisson e escanteios no futebol.",
                        source="test")
        if not a.get("ok"):
            return 1
        hits = kb.query("escanteios futebol")
        if not hits or "Poisson" not in hits[0]["title"]:
            return 1
        kb2 = ToolKnowledge(Path(td))
        if not kb2.query("Poisson"):
            return 1
    print("ALL TESTS PASSED - web_knowledge.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
