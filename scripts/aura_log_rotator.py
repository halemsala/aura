#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Log Rotator v1.0
Rotação automática de logs com compressão gzip, limite de tamanho e retenção.
"""
import os, sys, gzip, shutil
from pathlib import Path
from datetime import datetime, timedelta

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
CONFIG = {
    "max_size_mb": 50,
    "max_age_days": 7,
    "max_files": 20,
    "compress": True,
    "directories": [LOGDIR, AURA_ROOT / "logs_instalacao", AURA_ROOT / "engine" / "data" / "logs"],
}


def rotate_file(filepath: Path, max_size_mb: int, compress: bool) -> bool:
    """Rotaciona um arquivo se exceder o tamanho máximo."""
    if not filepath.exists():
        return False

    size_mb = filepath.stat().st_size / (1024 * 1024)
    if size_mb < max_size_mb:
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rotated_name = f"{filepath.stem}.{timestamp}{filepath.suffix}"
    rotated_path = filepath.parent / rotated_name

    # Renomear arquivo atual
    shutil.copy2(filepath, rotated_path)
    filepath.write_text("")  # Limpar original

    # Comprimir
    if compress:
        gz_path = rotated_path.with_suffix(rotated_path.suffix + ".gz")
        with open(rotated_path, "rb") as f_in:
            with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
        rotated_path.unlink()
        print(f"  [ROTATE] {filepath.name} -> {gz_path.name} ({size_mb:.1f} MB)")
    else:
        print(f"  [ROTATE] {filepath.name} -> {rotated_path.name} ({size_mb:.1f} MB)")

    return True


def cleanup_old_files(directory: Path, max_age_days: int, max_files: int, pattern: str = "*"):
    """Remove arquivos antigos e limita a quantidade."""
    if not directory.exists():
        return

    files = sorted(directory.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    cutoff = datetime.now() - timedelta(days=max_age_days)

    removed = 0
    for i, f in enumerate(files):
        # Remover por idade
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff and f.is_file():
            f.unlink()
            removed += 1
            continue

        # Remover por quantidade (mantém os mais recentes)
        if i >= max_files and f.is_file():
            f.unlink()
            removed += 1

    if removed:
        print(f"  [CLEANUP] {directory.name}: {removed} arquivo(s) removido(s)")


def main():
    print("=" * 60)
    print("AURA Log Rotator v1.0")
    print(f"Max size: {CONFIG['max_size_mb']} MB | Max age: {CONFIG['max_age_days']} dias | Max files: {CONFIG['max_files']}")
    print("=" * 60)

    total_rotated = 0
    for directory in CONFIG["directories"]:
        if not directory.exists():
            continue

        print(f"\nProcessando: {directory}")

        # Rotacionar logs grandes
        for log_file in directory.glob("*.log"):
            if rotate_file(log_file, CONFIG["max_size_mb"], CONFIG["compress"]):
                total_rotated += 1

        # Limpar rotações antigas
        cleanup_old_files(directory, CONFIG["max_age_days"], CONFIG["max_files"], "*.log.gz")
        cleanup_old_files(directory, CONFIG["max_age_days"], CONFIG["max_files"], "*.log.*")

    print(f"\n[RESUMO] Total rotacionado: {total_rotated}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
