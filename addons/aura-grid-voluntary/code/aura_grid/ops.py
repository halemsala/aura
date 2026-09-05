"""Fixed mathematical operations only — Master cannot send executable code."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

def _op_sha256(data: Any) -> dict[str, Any]:
    raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return {"op": "sha256", "digest": hashlib.sha256(raw).hexdigest()}

def _op_sha256_iter(data: Any) -> dict[str, Any]:
    """CPU-bound iterative hash (still fixed function)."""
    rounds = 1000
    if isinstance(data, dict) and "rounds" in data:
        rounds = max(1, min(int(data.get("rounds", 1000)), 50_000))
        payload = data.get("payload", data)
    else:
        payload = data
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode())
    for _ in range(rounds):
        h = hashlib.sha256(h.digest())
    return {"op": "sha256_iter", "rounds": rounds, "digest": h.hexdigest()}

def _op_matrix_dot_small(data: Any) -> dict[str, Any]:
    """Small matrix multiply — data only, size capped."""
    if not isinstance(data, dict):
        return {"op": "matrix_dot_small", "error": "expected_object"}
    a = data.get("a")
    b = data.get("b")
    if not isinstance(a, list) or not isinstance(b, list):
        return {"op": "matrix_dot_small", "error": "invalid_matrices"}
    if len(a) > 32 or len(b) > 32:
        return {"op": "matrix_dot_small", "error": "matrix_too_large"}
    try:
        n = len(a)
        m = len(b[0]) if b and isinstance(b[0], list) else 0
        k = len(b)
        if not a or not b or len(a[0]) != k:
            return {"op": "matrix_dot_small", "error": "shape_mismatch"}
        out = []
        for i in range(n):
            row = []
            for j in range(m):
                s = 0.0
                for t in range(k):
                    s += float(a[i][t]) * float(b[t][j])
                row.append(s)
            out.append(row)
        return {"op": "matrix_dot_small", "result": out}
    except (TypeError, ValueError, IndexError) as e:
        return {"op": "matrix_dot_small", "error": str(e)}

FIXED_OPS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "sha256": _op_sha256,
    "sha256_iter": _op_sha256_iter,
    "matrix_dot_small": _op_matrix_dot_small,
}

def run_fixed_op(op: str, data: Any) -> dict[str, Any]:
    fn = FIXED_OPS.get(op)
    if fn is None:
        return {"status": "BLOCKED", "error": f"unknown_or_forbidden_op:{op}", "executed": False}
    try:
        result = fn(data)
        return {"status": "SUCCESS", "result": result, "executed": True, "remote_code": False}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "executed": False, "remote_code": False}
