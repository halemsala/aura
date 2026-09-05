"""Ativa ou restaura o modo XTTS por referência do AURA.

O WAV é usado como speaker_wav somente quando o extra Coqui TTS está
instalado e o usuário confirmou a ativação. O arquivo de configuração recebe
backup antes da alteração e pode ser restaurado sem reinstalar o sistema.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "bridge" / "jarvis" / "config.yaml"
REFERENCE = ROOT / "bridge" / "jarvis" / "voices" / "voz_masculina_referencia.wav"
BACKUP = CONFIG.with_suffix(CONFIG.suffix + ".edge-backup")


def _replace_scalar(text: str, key: str, value: str) -> str:
    quoted = f'"{value}"'
    pattern = rf"(?m)^(\s*{re.escape(key)}:\s*).*$"
    updated, count = re.subn(pattern, rf"\g<1>{quoted}", text, count=1)
    if count != 1:
        raise RuntimeError(f"config_key_not_found:{key}")
    return updated


def enable() -> int:
    if not CONFIG.is_file():
        print(f"ERRO: configuração ausente: {CONFIG}")
        return 2
    if not REFERENCE.is_file() or REFERENCE.stat().st_size < 80:
        print(f"ERRO: WAV de referência ausente ou vazio: {REFERENCE}")
        return 3
    if importlib.util.find_spec("TTS") is None:
        print("ERRO: Coqui TTS não está instalado na venv do Voice.")
        print("AÇÃO: instale o extra compatível e execute novamente; a configuração não foi alterada.")
        return 4
    if not BACKUP.exists():
        shutil.copy2(CONFIG, BACKUP)
    text = CONFIG.read_text(encoding="utf-8")
    text = _replace_scalar(text, "preferred_engine", "xtts-reference")
    text = _replace_scalar(text, "reference_mode", "xtts-reference")
    text = _replace_scalar(text, "xtts_enabled", "true")
    text = _replace_scalar(text, "device", "cpu")
    CONFIG.write_text(text, encoding="utf-8", newline="\n")
    print("VOZ_REFERENCIA=ATIVADA")
    print(f"REFERENCE_WAV={REFERENCE}")
    print("ENGINE=xtts-reference")
    print("DEVICE=cpu")
    print(f"BACKUP={BACKUP}")
    print("Observação: a primeira fala pode baixar/carregar os pesos XTTS e demorar.")
    return 0


def restore() -> int:
    if not BACKUP.exists():
        print("RESTORE=NAO_NECESSARIO")
        return 0
    shutil.copy2(BACKUP, CONFIG)
    print("VOZ_REFERENCIA=DESATIVADA")
    print(f"CONFIG_RESTAURADA={CONFIG}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true")
    group.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    return enable() if args.enable else restore()


if __name__ == "__main__":
    raise SystemExit(main())
