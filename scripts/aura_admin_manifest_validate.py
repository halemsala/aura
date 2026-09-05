#!/usr/bin/env python3
"""Validate an AURA administrator tool manifest without executing the tool."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROHIBITED_NAME = re.compile(r"(live[_-]?order|real[_-]?order|send[_-]?order|financial[_-]?order|place[_-]?order|shell|run[_-]?command|credential|secret|token)", re.I)

REQUIRED = (
    "name",
    "version",
    "description",
    "risk_level",
    "input_schema",
    "output_schema",
    "allowed_agents",
    "allowed_modes",
    "side_effects",
    "timeout_s",
    "idempotency",
    "rollback",
    "requires_approval",
    "audit_events",
)
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "PROHIBITED"}
MODES = {"OBSERVE", "PLAN_ONLY", "DRY_RUN", "SUPERVISED", "GUARDED_AUTONOMY", "DISABLED"}
IDEMPOTENCY = {"idempotent", "keyed", "non_idempotent"}
ALLOWED_FIELDS = frozenset(REQUIRED) | {"$schema", "rollback_tool"}


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if ok else "BLOCKED", "detail": detail}


def validate(data: Any) -> tuple[list[dict[str, Any]], int]:
    checks: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [check("root_object", False, "manifest must be a JSON object")], 1

    missing = [key for key in REQUIRED if key not in data]
    checks.append(check("required_fields", not missing, "all required fields present" if not missing else f"missing: {missing}"))
    unknown = sorted((key for key in data if key not in ALLOWED_FIELDS), key=repr)
    checks.append(check("unknown_fields", not unknown, "no unknown authority fields" if not unknown else f"unknown: {unknown}"))

    name = data.get("name")
    checks.append(check("name", isinstance(name, str) and bool(re.fullmatch(r"[a-z][a-z0-9_]{2,63}", name)), "lowercase snake_case name"))
    checks.append(check("version", isinstance(data.get("version"), str) and bool(data.get("version")), "non-empty version"))
    checks.append(check("description", isinstance(data.get("description"), str) and bool(data.get("description")), "non-empty description"))
    risk_level = data.get("risk_level")
    risk_valid = isinstance(risk_level, str) and risk_level in RISK_LEVELS and risk_level != "PROHIBITED"
    checks.append(check("risk_level", risk_valid, "LOW, MEDIUM or HIGH; PROHIBITED tools are never registerable"))
    name = data.get("name")
    checks.append(check("prohibited_name", isinstance(name, str) and not PROHIBITED_NAME.search(name), "tool name does not imply shell, secret or live-order authority"))

    for field in ("input_schema", "output_schema"):
        schema = data.get(field)
        valid = (
            isinstance(schema, dict)
            and schema.get("type") == "object"
            and isinstance(schema.get("properties"), dict)
            and isinstance(schema.get("required"), list)
            and schema.get("additionalProperties") is False
        )
        checks.append(check(field, valid, "object schema with explicit required fields and additionalProperties=false"))
        if isinstance(schema, dict):
            properties = schema.get("properties")
            required = schema.get("required")
            checks.append(check(f"{field}_members", isinstance(properties, dict) and all(isinstance(key, str) and bool(key) for key in properties) and isinstance(required, list) and all(isinstance(key, str) and bool(key) for key in required), "schema members are non-empty strings"))

    for field in ("allowed_agents", "allowed_modes", "side_effects", "audit_events"):
        value = data.get(field)
        non_empty = field != "side_effects"
        valid = isinstance(value, list) and (not non_empty or bool(value)) and all(isinstance(item, str) and bool(item.strip()) for item in value)
        checks.append(check(field, valid, "string array"))

    allowed_modes = data.get("allowed_modes")
    modes_valid = isinstance(allowed_modes, list) and bool(allowed_modes) and all(isinstance(item, str) for item in allowed_modes) and set(allowed_modes).issubset(MODES)
    checks.append(check("allowed_modes_values", modes_valid, f"non-empty subset of {sorted(MODES)}"))
    timeout = data.get("timeout_s")
    checks.append(check("timeout_s", isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and 0 < timeout <= 300, "positive timeout up to 300 seconds"))
    idempotency = data.get("idempotency")
    checks.append(check("idempotency", isinstance(idempotency, str) and idempotency in IDEMPOTENCY, f"one of {sorted(IDEMPOTENCY)}"))
    checks.append(check("rollback", isinstance(data.get("rollback"), str) and bool(data.get("rollback")), "rollback declared"))
    checks.append(check("requires_approval", isinstance(data.get("requires_approval"), bool), "boolean approval flag"))

    if data.get("risk_level") == "HIGH":
        checks.append(check("high_risk_approval", data.get("requires_approval") is True, "high risk requires explicit approval"))
    if data.get("side_effects"):
        rollback_tool = data.get("rollback_tool")
        has_rollback_tool = isinstance(rollback_tool, str) and bool(re.fullmatch(r"[a-z][a-z0-9_]{2,63}", rollback_tool)) and not PROHIBITED_NAME.search(rollback_tool)
        checks.append(check("side_effect_rollback", has_rollback_tool and data.get("rollback") not in {"not_applicable_read_only", "none"}, "side effects require rollback and rollback_tool"))
    elif "rollback_tool" in data:
        checks.append(check("read_only_rollback_tool", data.get("rollback_tool") is None or isinstance(data.get("rollback_tool"), str), "read-only rollback_tool is null or string"))

    blocking = [item for item in checks if item["status"] == "BLOCKED"]
    return checks, 1 if blocking else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"cannot read manifest: {type(exc).__name__}"}, ensure_ascii=False, indent=2))
        return 1
    checks, rc = validate(data)
    print(json.dumps({"ok": rc == 0, "checks": checks}, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
