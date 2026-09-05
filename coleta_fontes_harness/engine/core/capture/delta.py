from __future__ import annotations
from copy import deepcopy
import json
from typing import Any, Dict, Optional

def build_delta(previous: Optional[dict], current: dict) -> dict:
    if previous is None:
        return {"changed": deepcopy(current), "removed": []}
    changed: Dict[str, Any] = {}
    removed = []
    for key in set(previous) | set(current):
        if key not in current:
            removed.append(key)
        elif key not in previous or previous[key] != current[key]:
            changed[key] = current[key]
    return {"changed": changed, "removed": removed}

def build_budgeted_context(critical: dict, relevant: dict, optional: dict, max_bytes: int) -> dict:
    result = {"critical": critical, "relevant": {}, "optional": {}, "omitted": []}
    def size(value: object) -> int:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
    for group_name, group in (("relevant", relevant), ("optional", optional)):
        for key, value in group.items():
            candidate = deepcopy(result)
            candidate[group_name][key] = value
            if size(candidate) <= max_bytes:
                result = candidate
            else:
                result["omitted"].append(key)
    return result
