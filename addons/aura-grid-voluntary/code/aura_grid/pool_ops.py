"""Picklable workers for ProcessPoolExecutor — fixed ops only."""
from __future__ import annotations

from typing import Any

from .ops import run_fixed_op


def process_batch_item(item: dict[str, Any]) -> dict[str, Any]:
    """item = {"op": str, "data": Any, "id": optional}"""
    op = str(item.get("op") or "sha256")
    data = item.get("data")
    out = run_fixed_op(op, data)
    out["id"] = item.get("id")
    return out
