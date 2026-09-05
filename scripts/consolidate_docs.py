#!/usr/bin/env python3
"""Consolida markdowns em docs/MANUAL_UNIFICADO_V23.md"""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "MANUAL_UNIFICADO_V23.md"
SKIP_DIRS = {"venv", "node_modules", "ARQUIVO_LEGADO", "_ARQUIVO_LEGADO", ".git", "__pycache__", ".github"}


def consolidate() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with OUTPUT.open("w", encoding="utf-8") as outfile:
        outfile.write("# MANUAL UNIFICADO AURA QUANT-X V23\n\n")
        outfile.write("> Gerado automaticamente. Fonte unica de verdade operacional.\n\n---\n\n")
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for file in sorted(files):
                if not file.endswith(".md"):
                    continue
                if file == "MANUAL_UNIFICADO_V23.md":
                    continue
                filepath = Path(root) / file
                rel = filepath.relative_to(ROOT).as_posix()
                outfile.write(f"## Arquivo: `{rel}`\n\n")
                try:
                    outfile.write(filepath.read_text(encoding="utf-8", errors="replace"))
                except Exception as e:
                    outfile.write(f"(erro ao ler: {e})\n")
                outfile.write("\n\n---\n\n")
                count += 1
    print(f"Documentacao consolidada: {OUTPUT} ({count} arquivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(consolidate())
