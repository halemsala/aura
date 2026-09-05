# engine/core/jsonl_rotator.py — V23 rotacao de logs JSONL (max 5MB x 3)
from __future__ import annotations
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


def make_jsonl_logger(
    name: str,
    filename: str,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        handler = RotatingFileHandler(
            filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def write_jsonl(logger: logging.Logger, payload: Any) -> None:
    try:
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False, default=str)
        logger.info(payload)
    except Exception:
        pass
