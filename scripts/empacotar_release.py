"""Empacotador oficial do AURA Quant-X.

A árvore que contém este script é a fonte canónica do ZIP. O empacotador
substitui o manifesto SHA256 dentro da árvore e grava o ZIP, o hash externo
e o manifesto de empacotamento numa pasta irmã, nunca dentro da distribuição.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSIENT_SUFFIXES = (".db", ".sqlite", ".jsonl", ".pyc", ".log")
TRANSIENT_NAMES = {"config.yaml.edge-backup"}


def is_transient(path: Path) -> bool:
    if "__pycache__" in path.parts or path.name in TRANSIENT_NAMES:
        return True
    if any(path.name.endswith(suffix) or f"{suffix}-" in path.name for suffix in TRANSIENT_SUFFIXES):
        return True
    return False


def check_bat_crlf() -> None:
    invalid = []
    for path in ROOT.rglob("*.bat"):
        if is_transient(path):
            continue
        data = path.read_bytes()
        normalised = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if data != normalised.replace(b"\n", b"\r\n"):
            invalid.append(path.relative_to(ROOT).as_posix())
    if invalid:
        raise SystemExit("BAT_NOT_CRLF:" + ",".join(invalid))


def distribution_files() -> list[Path]:
    files = [path for path in ROOT.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt" and not is_transient(path)]
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix().lower())


def write_hash_manifest(files: list[Path]) -> int:
    entries = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  ./{path.relative_to(ROOT).as_posix()}")
    entries.append(f"{hashlib.sha256(b'').hexdigest()}  ./SHA256SUMS.txt")
    manifest = ROOT / "SHA256SUMS.txt"
    # The manifest itself is intentionally excluded from its own digest list.
    manifest.write_text("\n".join(entries[:-1]) + "\n", encoding="utf-8", newline="\n")
    return len(entries) - 1


def marker_name() -> str:
    marker = (ROOT / "PACKAGE_RELEASE.txt").read_text(encoding="utf-8").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", marker)
    return safe[:100] or "AURA_RELEASE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-dir", type=Path, help="Pasta externa para pacotes e evidências")
    parser.add_argument("--name", help="Nome do ZIP sem extensão")
    parser.add_argument("--dry-run", action="store_true", help="Validar a árvore e mostrar o destino sem gravar ZIP")
    args = parser.parse_args()

    check_bat_crlf()
    files = distribution_files()
    if not files:
        raise SystemExit("DISTRIBUTION_EMPTY")
    external = args.external_dir or ROOT.parent.parent / "EXTERNO_RELATORIOS_EVIDENCIAS"
    packages = external / "pacotes"
    hashes = external / "hashes"
    manifests = external / "validacoes"
    packages.mkdir(parents=True, exist_ok=True)
    hashes.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    name = args.name or f"AURA_QUANT_X_{marker_name()}"
    zip_path = packages / f"{name}.zip"
    if args.dry_run:
        print(json.dumps({"root": str(ROOT), "files": len(files), "zip": str(zip_path), "external": str(external)}, ensure_ascii=False))
        return 0

    count = write_hash_manifest(files)
    files = distribution_files()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(ROOT / "SHA256SUMS.txt", f"{ROOT.name}/SHA256SUMS.txt")
        for path in files:
            archive.write(path, f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}")
    zip_digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    hash_path = hashes / f"{zip_path.stem}.sha256"
    hash_path.write_text(f"{zip_digest}  {zip_path.name}\n", encoding="utf-8", newline="\n")
    manifest_path = manifests / f"{zip_path.stem}_manifest.json"
    manifest_path.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "root": str(ROOT), "zip": str(zip_path), "sha256": zip_digest, "file_count": count, "transients_excluded": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "zip": str(zip_path), "sha256": zip_digest, "file_count": count, "external": str(external)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
