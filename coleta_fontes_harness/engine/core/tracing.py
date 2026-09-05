#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA V25 — Tracing leve (stdlib).
Compativel com correlacao span_id em logs; export JSONL opcional.
Nao exige OpenTelemetry SDK (pode ser trocado depois).
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

_lock = threading.Lock()
_current: Dict[int, Dict[str, Any]] = {}
_export_path: Optional[Path] = None


def configure(export_path: Optional[str] = "engine/data/traces.jsonl") -> None:
    global _export_path
    _export_path = Path(export_path) if export_path else None
    if _export_path:
        _export_path.parent.mkdir(parents=True, exist_ok=True)


def _tid() -> int:
    return threading.get_ident()


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Dict[str, Any]]:
    parent = _current.get(_tid())
    sp = {
        "span_id": uuid.uuid4().hex[:16],
        "parent_id": (parent or {}).get("span_id"),
        "name": name,
        "attrs": attrs,
        "t0": time.perf_counter(),
        "ts": time.time(),
    }
    _current[_tid()] = sp
    err = None
    try:
        yield sp
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        raise
    finally:
        sp["duration_us"] = (time.perf_counter() - sp["t0"]) * 1e6
        if err:
            sp["error"] = err
        _current.pop(_tid(), None)
        if parent is not None:
            _current[_tid()] = parent
        if _export_path is not None:
            try:
                line = json.dumps(
                    {
                        "span_id": sp["span_id"],
                        "parent_id": sp.get("parent_id"),
                        "name": sp["name"],
                        "duration_us": round(sp["duration_us"], 1),
                        "attrs": sp.get("attrs") or {},
                        "error": sp.get("error"),
                        "ts": sp["ts"],
                    },
                    ensure_ascii=False,
                )
                with _lock:
                    with _export_path.open("a", encoding="utf-8") as f:
                        f.write(line + "\n")
            except Exception:
                pass


def current_span_id() -> Optional[str]:
    sp = _current.get(_tid())
    return sp.get("span_id") if sp else None
