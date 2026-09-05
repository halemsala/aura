#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integrity manifest SHA-256 — build / verify."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

ALLOWED_EXT = {".py", ".bat", ".json", ".md", ".ps1"}
SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".twin_shadow", "logs_ultra", "logs_supervisor"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def build_manifest(root: Path, out: Path) -> int:
    manifest = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in ALLOWED_EXT:
            continue
        if any(part in SKIP for part in p.parts):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        manifest[rel] = sha256(p)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"manifest entries={len(manifest)} -> {out}")
    return 0

def verify(root: Path, manifest_path: Path) -> int:
    if not manifest_path.exists():
        print("[WARN] manifest ausente — rode --build")
        return 0  # soft on first run
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = 0
    for rel, expected in manifest.items():
        p = root / rel
        if not p.exists():
            print(f"[MISSING] {rel}")
            failures += 1
            continue
        actual = sha256(p)
        if actual != expected:
            print(f"[TAMPERED] {rel}")
            failures += 1
    return 1 if failures else 0

if __name__ == "__main__":
    root = Path(sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else ".")
    out = root / "security" / "allowed_hashes.sha256"
    # also support package-local
    pkg = Path(__file__).resolve().parents[1]
    if "--build" in sys.argv:
        # build for package directory if hermes_v10 structure
        target = pkg if (pkg / "core").exists() else root
        out = target / "security" / "allowed_hashes.sha256"
        sys.exit(build_manifest(target, out))
    target = pkg if (pkg / "core").exists() else root
    man = target / "security" / "allowed_hashes.sha256"
    sys.exit(verify(target, man))
