#!/usr/bin/env python3
"""
Gera ZIP de release do AURA LAB a cada atualização.

Uso:
  python3 tools/pack_release.py
  python3 tools/pack_release.py --version 0.2.0
  python3 tools/pack_release.py --out-dir /caminho/saida

Política: empacota só a pasta aura_lab (schemas, catálogo, agent, tools, records).
Não inclui segredos. Records jsonl entram para trilha de lab (podem ser omitidos com --no-records).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]  # aura_lab/
DEFAULT_OUT_DIR = ROOT.parent  # artifacts/
VERSION_FILE = ROOT / "VERSION"


def read_version(cli_version: str | None) -> str:
    if cli_version:
        return cli_version.strip()
    if VERSION_FILE.is_file():
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.1.0"


def write_version(version: str) -> None:
    VERSION_FILE.write_text(version.strip() + "\n", encoding="utf-8")


def should_skip(path: Path, include_records: bool) -> bool:
    skip_dirs = {".git", "__pycache__", ".venv", "venv", ".pytest_cache"}
    if any(part in skip_dirs for part in path.parts):
        return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    if not include_records and path.name == "lab_failures.jsonl":
        return True
    return False


def pack(
    version: str,
    out_dir: Path,
    include_records: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"AURA_LAB_v{version}_{stamp}.zip"

    files: list[str] = []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            if should_skip(path, include_records):
                continue
            # arcname relative to parent of aura_lab so zip roots at aura_lab/
            rel = path.relative_to(ROOT.parent)
            zf.write(path, arcname=rel.as_posix())
            files.append(rel.as_posix())

        manifest = {
            "product": "AURA LAB",
            "version": version,
            "built_utc": datetime.now(timezone.utc).isoformat(),
            "file_count": len(files),
            "files": files,
            "policy": {
                "paper_trade": True,
                "execution_allowed": False,
                "advisory_only": True,
            },
            "entrypoints": [
                "aura_lab/tools/lab_diagnose.py",
                "aura_lab/tools/catalog_loader.py",
                "aura_lab/tools/pack_release.py",
            ],
        }
        zf.writestr(
            "aura_lab/BUILD_MANIFEST.txt",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )

    write_version(version)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack AURA LAB release ZIP")
    parser.add_argument("--version", default=None, help="ex.: 0.1.1 (default: VERSION file or 0.1.0)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--no-records", action="store_true", help="Omitir lab_failures.jsonl")
    parser.add_argument("--bump-patch", action="store_true", help="Incrementa patch em VERSION")
    args = parser.parse_args()

    version = read_version(args.version)
    if args.bump_patch and args.version is None:
        parts = version.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
            version = ".".join(parts)
        except ValueError:
            version = version + ".1"

    out = pack(version, args.out_dir, include_records=not args.no_records)
    print(f"OK {out}")
    print(f"version={version} size={out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
