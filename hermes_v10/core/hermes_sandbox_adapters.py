#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional sandboxes: E2B / Daytona — degrade gracefully if not installed.
Local fallback: subprocess with timeout in temp dir.
"""
from __future__ import annotations
import json, os, subprocess, tempfile, textwrap
from pathlib import Path
from typing import Any, Dict

def run_local_sandbox(code: str, timeout: int = 20) -> Dict[str, Any]:
    """Local snippet runner. Disabled unless AURA_HERMES_LOCAL_SANDBOX=1."""
    flag = (os.environ.get("AURA_HERMES_LOCAL_SANDBOX") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return {"backend": "local_temp", "error": "local_sandbox_disabled", "hint": "set AURA_HERMES_LOCAL_SANDBOX=1 to opt in"}
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "snippet.py"
        f.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run(
                [os.environ.get("PYTHON", "python"), str(f)],
                capture_output=True, text=True, timeout=timeout,
                cwd=td,
            )
            return {
                "backend": "local_temp",
                "rc": r.returncode,
                "stdout": (r.stdout or "")[-2000:],
                "stderr": (r.stderr or "")[-500:],
            }
        except subprocess.TimeoutExpired:
            return {"backend": "local_temp", "error": "timeout"}

def run_e2b(code: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore
    except ImportError:
        return {"backend": "e2b", "error": "not_installed", "hint": "pip install e2b_code_interpreter", "fallback": run_local_sandbox(code, timeout)}
    if not os.environ.get("E2B_API_KEY"):
        return {"backend": "e2b", "error": "E2B_API_KEY missing", "fallback": run_local_sandbox(code, timeout)}
    try:
        with Sandbox(timeout=timeout) as sbx:
            result = sbx.run_code(code)
            return {
                "backend": "e2b",
                "stdout": str(getattr(getattr(result, "logs", None), "stdout", ""))[:2000],
                "stderr": str(getattr(getattr(result, "logs", None), "stderr", ""))[:500],
            }
    except Exception as e:
        return {"backend": "e2b", "error": str(e), "fallback": run_local_sandbox(code, timeout)}

def run_daytona(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Daytona optional — if SDK missing, local fallback."""
    try:
        import daytona  # type: ignore  # noqa: F401
    except ImportError:
        return {"backend": "daytona", "error": "not_installed", "hint": "pip install daytona", "fallback": run_local_sandbox(code, timeout)}
    return {"backend": "daytona", "error": "sdk_present_but_not_wired", "fallback": run_local_sandbox(code, timeout)}

def run_sandbox(code: str, prefer: str = "auto") -> Dict[str, Any]:
    prefer = (prefer or "auto").lower()
    if prefer == "e2b":
        return run_e2b(code)
    if prefer == "daytona":
        return run_daytona(code)
    if prefer == "local":
        return run_local_sandbox(code)
    # auto: e2b if key else local
    if os.environ.get("E2B_API_KEY"):
        return run_e2b(code)
    return run_local_sandbox(code)

if __name__ == "__main__":
    print(json.dumps(run_sandbox("print(1+1)"), indent=2))
