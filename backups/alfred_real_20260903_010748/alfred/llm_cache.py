"""Cache em disco para respostas curtas repetidas do qwen3:8b. Não troca de modelo."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import paths

CACHE_DIR = paths.DATA_ROOT / "llm_cache"
TTL_S = 45.0
MAX_FILES = 80


def _key(messages: list) -> str:
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)[:4000]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def get(messages: list) -> str | None:
    if not messages:
        return None
    last = str((messages[-1] or {}).get("content") or "")
    if len(last) > 240:
        return None
    path = CACHE_DIR / f"{_key(messages)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(data.get("ts") or 0) > TTL_S:
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return str(data.get("text") or "") or None


def put(messages: list, text: str) -> None:
    if not text or not messages:
        return
    last = str((messages[-1] or {}).get("content") or "")
    if len(last) > 240 or len(text) > 2000:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_key(messages)}.json"
    path.write_text(json.dumps({"ts": time.time(), "text": text}, ensure_ascii=False), encoding="utf-8")
    files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[:-MAX_FILES]:
        try:
            old.unlink()
        except OSError:
            pass
