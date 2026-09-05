#!/usr/bin/env python3
"""Static fail-closed audit for unsafe execution primitives in AURA admin modules."""
from __future__ import annotations

import ast
import argparse
import json
from pathlib import Path
from typing import Any


TARGETS = (
    "scripts/aura_admin_core.py",
    "scripts/aura_admin_governance.py",
    "scripts/aura_admin_runtime.py",
    "scripts/aura_admin_config.py",
)
FORBIDDEN_IMPORTS = {"subprocess", "os", "socket", "pty", "shlex"}
FORBIDDEN_BUILTINS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_PROCESS_MODULES = {"os", "subprocess", "socket", "pty", "shlex"}
FORBIDDEN_PROCESS_CALLS = {"system", "popen", "Popen", "run", "call", "check_call", "check_output"}


def audit_file(path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [{"file": str(path), "line": 0, "kind": "parse_error", "detail": type(exc).__name__}]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    findings.append({"file": str(path), "line": node.lineno, "kind": "forbidden_import", "detail": alias.name})
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
            findings.append({"file": str(path), "line": node.lineno, "kind": "forbidden_import", "detail": node.module})
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
                findings.append({"file": str(path), "line": node.lineno, "kind": "forbidden_call", "detail": node.func.id})
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_PROCESS_CALLS:
                root = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                if root in FORBIDDEN_PROCESS_MODULES:
                    findings.append({"file": str(path), "line": node.lineno, "kind": "arbitrary_execution", "detail": f"{root}.{node.func.attr}"})
    return findings


def audit(root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in TARGETS:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        else:
            findings.extend(audit_file(path))
    if missing:
        findings.extend({"file": item, "line": 0, "kind": "missing_file", "detail": item} for item in missing)
    return {"status": "PASS" if not findings else "BLOCKED", "targets": list(TARGETS), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = audit(args.root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
