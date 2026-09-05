"""Independent release verifier for an extracted AURA package or admin skill ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

REQUIRED = (
    "AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat",
    "AURA_ABRIR_DESKTOP_SEGURO.bat",
    "PACKAGE_RELEASE.txt",
    "desktop/Aura.Desktop.csproj",
    "desktop/ui/matriz_v22/index.html",
    "desktop/ui/matriz_v22/BUILD_INFO.json",
    "desktop/packaging/installer-manifest.json",
    "desktop/packaging/AURA_Setup.iss",
    "desktop/capture/aura-capture.js",
    "bridge/jarvis_voice_server.py",
    "engine/server.py",
)
OPTIONAL_SERVICE_FILES = ("engine/server.py", "bridge/server.py")
SKILL_REQUIRED = (
    "SKILL.md",
    "SHA256SUMS.txt",
    "scripts/aura_admin_core.py",
    "scripts/aura_admin_governance.py",
    "scripts/aura_admin_runtime.py",
    "scripts/aura_admin_config.py",
    "scripts/aura_release_verify.py",
)
FORBIDDEN_SUFFIXES = (".log", ".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3", ".jsonl", ".pyc", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm", ".session", ".session-journal")


def item(name: str, ok: bool, detail: str | dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _clean_distribution_checks(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    bad_artifacts = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if (path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES)
        or (path.is_dir() and path.name.lower() in {"__pycache__", "__manus__"})
    ]
    clean = item("clean_distribution", not bad_artifacts, ", ".join(bad_artifacts) if bad_artifacts else "clean")
    bad_bat: list[str] = []
    bat_count = 0
    for path in root.rglob("*.bat"):
        bat_count += 1
        raw = path.read_bytes()
        if b"\n" in raw.replace(b"\r\n", b"") or b"\r" in raw.replace(b"\r\n", b""):
            bad_bat.append(str(path.relative_to(root)))
    crlf = item("bat_crlf", not bad_bat, f"{bat_count} BAT(s)" if not bad_bat else ", ".join(bad_bat))
    return clean, crlf


def _hash_check(root: Path, *, require_hashes: bool) -> dict[str, Any]:
    sums = root / "SHA256SUMS.txt"
    hash_failures: list[str] = []
    hash_count = 0
    listed: set[str] = set()
    root_resolved = root.resolve()
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            digest, separator, relative = line.partition("  ")
            if not separator:
                hash_failures.append(f"malformed:{line}")
                continue
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                hash_failures.append(f"unsafe_path:{relative}")
                continue
            normalized = candidate.as_posix()
            if normalized in listed:
                hash_failures.append(f"duplicate:{normalized}")
                continue
            listed.add(normalized)
            hash_count += 1
            path = root / candidate
            try:
                path.resolve().relative_to(root_resolved)
            except ValueError:
                hash_failures.append(f"unsafe_path:{relative}")
                continue
            if not path.is_file():
                hash_failures.append(f"missing:{relative}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != digest.lower():
                hash_failures.append(f"mismatch:{relative}")
        if require_hashes and root.is_dir():
            expected = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt"}
            unlisted = sorted(expected - listed)
            hash_failures.extend(f"unlisted:{relative}" for relative in unlisted)
    elif require_hashes:
        hash_failures.append("SHA256SUMS.txt missing")
    return item("sha256", not hash_failures, f"{hash_count} hashes" if not hash_failures else ", ".join(hash_failures))


def _verify_required(root: Path, required: Iterable[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [item("root", root.is_dir(), str(root))]
    for relative in required:
        path = root / relative
        checks.append(item(f"required:{relative}", path.is_file(), "present" if path.is_file() else "missing"))
    return checks


def verify_root(root: Path, *, require_hashes: bool = False) -> list[dict[str, Any]]:
    """Verify the full AURA Windows distribution layout."""
    checks = _verify_required(root, REQUIRED)
    for relative in OPTIONAL_SERVICE_FILES:
        path = root / relative
        checks.append(item(f"optional:{relative}", True, "present" if path.is_file() else "not found in this layout"))
    clean, crlf = _clean_distribution_checks(root)
    checks.extend((clean, crlf, _hash_check(root, require_hashes=require_hashes)))
    return checks


def verify_skill_root(root: Path, *, require_hashes: bool = False) -> list[dict[str, Any]]:
    """Verify the reusable admin skill layout independently of Windows services."""
    checks = _verify_required(root, SKILL_REQUIRED)
    clean, crlf = _clean_distribution_checks(root)
    checks.extend((clean, crlf, _hash_check(root, require_hashes=require_hashes)))
    return checks


def _archive_hash_check(archive: zipfile.ZipFile, names: list[str], prefix: str) -> dict[str, Any]:
    sums_member = prefix + "SHA256SUMS.txt"
    failures: list[str] = []
    listed: set[str] = set()
    hash_count = 0
    normalized = {name.rstrip("/") for name in names}
    if sums_member not in normalized and "SHA256SUMS.txt" not in normalized:
        return {"ok": False, "detail": "SHA256SUMS.txt missing from archive"}
    actual_sums_member = sums_member if sums_member in normalized else "SHA256SUMS.txt"
    try:
        text = archive.read(actual_sums_member).decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        return {"ok": False, "detail": f"invalid SHA256SUMS.txt: {type(exc).__name__}"}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        digest, separator, relative = line.partition("  ")
        if not separator:
            failures.append(f"malformed:{line}")
            continue
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
            failures.append(f"unsafe_path:{relative}")
            continue
        normalized_relative = candidate.as_posix()
        if normalized_relative in listed:
            failures.append(f"duplicate:{normalized_relative}")
            continue
        listed.add(normalized_relative)
        hash_count += 1
        member = prefix + normalized_relative
        if member not in normalized and normalized_relative not in normalized:
            failures.append(f"missing:{relative}")
            continue
        actual_member = member if member in normalized else normalized_relative
        actual = hashlib.sha256(archive.read(actual_member)).hexdigest()
        if actual.lower() != digest.lower():
            failures.append(f"mismatch:{relative}")
    expected = {name[len(prefix):] if prefix and name.startswith(prefix) else name for name in names if not name.endswith("/") and name.rstrip("/") != actual_sums_member}
    failures.extend(f"unlisted:{relative}" for relative in sorted(expected - listed))
    return {"ok": not failures, "detail": f"{hash_count} hashes" if not failures else ", ".join(failures)}


def _verify_archive(path: Path, required: Iterable[str], *, strict_hashes: bool = False) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            names = archive.namelist()
            normalized = {name.rstrip("/") for name in names}
            prefixes = [""] + sorted({name.split("/", 1)[0] + "/" for name in names if "/" in name})
            prefix = next((candidate for candidate in prefixes if all(candidate + relative in normalized for relative in required)), "")
            missing = [relative for relative in required if prefix + relative not in normalized and relative not in normalized]
            forbidden = [name for name in names if name.lower().endswith(FORBIDDEN_SUFFIXES) or "/__pycache__/" in name.lower() or name.lower().endswith("/__pycache__")]
            unsafe_paths = [name for name in names if name.startswith(("/", "\\")) or "\\" in name or ".." in PurePosixPath(name).parts]
            hash_report = _archive_hash_check(archive, names, prefix) if strict_hashes else {"ok": True, "detail": "not required"}
            return {"name": "zip", "ok": bad is None and not missing and not forbidden and not unsafe_paths and hash_report["ok"], "detail": {"entries": len(names), "testzip": bad, "missing": missing, "forbidden": forbidden, "unsafe_paths": unsafe_paths, "sha256": hash_report["detail"]}}
    except (OSError, zipfile.BadZipFile) as exc:
        return {"name": "zip", "ok": False, "detail": str(exc)}


def verify_zip(path: Path) -> dict[str, Any]:
    """Verify a full AURA distribution ZIP; its SHA-256 is kept externally."""
    result = _verify_archive(path, REQUIRED, strict_hashes=False)
    detail = result["detail"]
    if isinstance(detail, dict):
        detail["has_root_bat"] = not detail["missing"]
    return result


def verify_skill_zip(path: Path) -> dict[str, Any]:
    """Verify an admin-skill ZIP contains the reusable core and a complete hash manifest."""
    return _verify_archive(path, ("SKILL.md", "SHA256SUMS.txt", "scripts/aura_admin_core.py"), strict_hashes=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--profile", choices=("full", "skill"), default="full")
    parser.add_argument("--require-hashes", action="store_true")
    args = parser.parse_args()
    if args.profile == "skill":
        checks = verify_skill_root(args.root.resolve(), require_hashes=args.require_hashes or bool(args.zip))
        if args.zip:
            checks.append(verify_skill_zip(args.zip.resolve()))
    else:
        checks = verify_root(args.root.resolve(), require_hashes=args.require_hashes or bool(args.zip))
        if args.zip:
            checks.append(verify_zip(args.zip.resolve()))
    ok = all(check["ok"] for check in checks)
    print(json.dumps({"ok": ok, "profile": args.profile, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
