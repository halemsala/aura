#!/usr/bin/env python3
"""Run a local, deterministic quality audit for the AURA administrator package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
    "SKILL.md",
    "SHA256SUMS.txt",
    "scripts/__init__.py",
    "scripts/aura_admin_core.py",
    "scripts/aura_admin_governance.py",
    "scripts/aura_admin_runtime.py",
    "scripts/aura_admin_config.py",
    "scripts/aura_admin_manifest_validate.py",
    "scripts/aura_quality_audit.py",
    "scripts/aura_static_security_audit.py",
    "scripts/aura_admin_benchmark.py",
    "scripts/aura_release_verify.py",
    "scripts/aura_preflight.py",
    "scripts/test_aura_admin_core.py",
    "scripts/test_aura_release_verify.py",
    "scripts/test_aura_admin_advanced.py",
    "scripts/test_aura_preflight.py",
    "templates/aura-admin-manifest.json",
    "templates/aura-admin-plan.schema.json",
    "templates/aura-admin-schema.sql",
    "templates/aura-admin-config.json",
    "templates/aura-evolution-checkpoint.md",
    "templates/aura-evolution-log.md",
)


def check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "status": "PASS" if ok else "BLOCKED", "detail": detail})


def run_command(root: Path, args: list[str]) -> tuple[bool, str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(args, cwd=root, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, check=False)
    output = result.stdout.strip()
    return result.returncode == 0, output[-2_000:]


def _runtime_artifacts(root: Path) -> set[Path]:
    """Return release-forbidden runtime files so tests can be cleaned safely."""
    result: set[Path] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".db", ".sqlite", ".jsonl", ".log", ".pyc"} or path.name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
            result.add(path)
    return result


def _remove_transient_bytecode(root: Path) -> None:
    for path in root.rglob("*.pyc"):
        path.unlink(missing_ok=True)
    for path in sorted(root.rglob("__pycache__"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _remove_new_runtime_artifacts(root: Path, before: set[Path]) -> None:
    """Remove only artifacts created during this audit, never pre-existing user data."""
    for path in _runtime_artifacts(root) - before:
        path.unlink(missing_ok=True)


def _audit_full_profile_fixture(root: Path) -> tuple[bool, str]:
    """Exercise the full Windows layout verifier without treating the skill as Windows payload."""
    required = (
        "AURA_INSTALAR_E_INICIAR_TUDO.bat",
        "PACKAGE_RELEASE.txt",
        "desktop/aura_self_test.py",
        "bridge/jarvis_voice_server.py",
    )
    with tempfile.TemporaryDirectory(prefix="aura-full-profile-") as directory:
        fixture = Path(directory)
        for relative in required:
            path = fixture / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() == ".bat":
                path.write_bytes(b"@echo off\r\nrem PAPER TRADE ONLY\r\n")
            else:
                path.write_text("# deterministic full-profile fixture\n", encoding="utf-8")
        entries = [f"{hashlib.sha256((fixture / relative).read_bytes()).hexdigest()}  ./{relative}" for relative in required]
        (fixture / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
        return run_command(root, [sys.executable, str(root / "scripts/aura_release_verify.py"), "--root", str(fixture), "--profile", "full", "--require-hashes"])


def audit(root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing = [item for item in REQUIRED_FILES if not (root / item).is_file()]
    check(checks, "required_files", not missing, "missing=" + ",".join(missing) if missing else "all required files present")
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").is_file() else ""
    check(checks, "skill_end_marker", skill_text.count("<!-- End of skill -->") == 1, "exactly one end marker")
    check(checks, "skill_size", len(skill_text.splitlines()) < 500, f"lines={len(skill_text.splitlines())}")
    for relative in ("templates/aura-admin-manifest.json", "templates/aura-admin-plan.schema.json", "templates/aura-admin-config.json"):
        try:
            json.loads((root / relative).read_text(encoding="utf-8"))
            check(checks, f"json:{relative}", True, "valid JSON")
        except (OSError, json.JSONDecodeError) as exc:
            check(checks, f"json:{relative}", False, type(exc).__name__)
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.executescript((root / "templates/aura-admin-schema.sql").read_text(encoding="utf-8"))
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        expected_tables = {"aura_audit_events", "aura_episodic_memory", "aura_performance_metrics", "aura_admin_schema_meta"}
        expected_triggers = {"trg_aura_audit_no_update", "trg_aura_audit_no_delete"}
        check(checks, "sql_schema", expected_tables <= tables and expected_triggers <= triggers, "tables/triggers present")
    except (OSError, sqlite3.Error) as exc:
        check(checks, "sql_schema", False, type(exc).__name__)
    runtime_before_tests = _runtime_artifacts(root)
    compile_ok, compile_output = run_command(root, [sys.executable, "-m", "py_compile", *(str(root / item) for item in REQUIRED_FILES if item.endswith(".py"))])
    check(checks, "python_compile", compile_ok, compile_output or "compiled")
    tests_ok, tests_output = run_command(root, [sys.executable, "-m", "unittest", "-q", "scripts.test_aura_admin_core", "scripts.test_aura_admin_advanced", "scripts.test_aura_release_verify", "scripts.test_aura_preflight"])
    check(checks, "unit_tests", tests_ok, tests_output or "tests passed")
    _remove_new_runtime_artifacts(root, runtime_before_tests)
    manifest_ok, manifest_output = run_command(root, [sys.executable, "scripts/aura_admin_manifest_validate.py", "templates/aura-admin-manifest.json"])
    check(checks, "manifest_validator", manifest_ok, manifest_output or "manifest accepted")
    config_ok, config_output = run_command(root, [sys.executable, "scripts/aura_admin_config.py", "templates/aura-admin-config.json"])
    check(checks, "config_validator", config_ok, config_output or "configuration accepted")
    security_ok, security_output = run_command(root, [sys.executable, "scripts/aura_static_security_audit.py"])
    check(checks, "static_security_audit", security_ok, security_output or "no unsafe primitives")
    _remove_transient_bytecode(root)
    release_ok, release_output = run_command(root, [sys.executable, "scripts/aura_release_verify.py", "--root", str(root), "--profile", "skill", "--require-hashes"])
    check(checks, "independent_release_verifier", release_ok, release_output or "skill release accepted")
    try:
        full_ok, full_output = _audit_full_profile_fixture(root)
        check(checks, "independent_full_profile_fixture", full_ok, full_output or "full profile fixture accepted")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        check(checks, "independent_full_profile_fixture", False, type(exc).__name__)
    checksum_ok, checksum_output = run_command(root, ["sha256sum", "-c", "SHA256SUMS.txt"])
    check(checks, "release_checksums", checksum_ok, checksum_output or "all release hashes match")
    blocking = [item for item in checks if item["status"] != "PASS"]
    return {"status": "PASS" if not blocking else "BLOCKED", "root": str(root), "checks": checks, "blocking_count": len(blocking)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = audit(args.root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
