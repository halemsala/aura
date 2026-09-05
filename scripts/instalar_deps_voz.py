"""Instala deps de voz com pins que funcionam no Windows do AURA.

Nao instala torchcodec (precisa FFmpeg full-shared e falha com torch 2.13+cpu).
Nao deixa transformers 5.x (remove isin_mps_friendly usado pelo Coqui).
tokenizers e escolhido pelo proprio transformers 4.57.x (>=0.22,<=0.23).
"""
from __future__ import annotations

import subprocess
import sys


BASE = [
    "edge-tts>=6.1.0",
    "aiofiles",
    "faster-whisper>=1.0.0",
    "soundfile",
    "librosa",
    "numpy",
]
COQUI = [
    "coqui-tts==0.27.5",
]
TF_PIN = [
    "transformers>=4.57.1,<5.0",
    "huggingface-hub>=0.26.0,<1.0",
    "tokenizers>=0.22.0,<0.24",
]


def _pip(args: list[str]) -> int:
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *args]
    print("RUN", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    print("PY", sys.executable)
    print("VER", sys.version.replace("\n", " "))
    subprocess.call([sys.executable, "-m", "pip", "uninstall", "-y", "torchcodec"])
    rc = _pip(BASE)
    if rc != 0:
        print("ERRO deps base voz")
        return rc
    rc = _pip(COQUI + TF_PIN)
    if rc != 0:
        print("AVISO install conjunto falhou; tentando em duas passagens")
        rc = _pip(COQUI)
        if rc != 0:
            print("ERRO pip coqui-tts")
            return rc
        rc = _pip(TF_PIN)
        if rc != 0:
            print("ERRO pin transformers 4.57.x")
            return rc
    # garante que um pip posterior nao deixou transformers 5.x
    rc = _pip(TF_PIN)
    if rc != 0:
        print("ERRO re-pin transformers")
        return rc
    try:
        from aura_xtts_compat import apply_all

        print("COMPAT", apply_all())
        import transformers

        print("transformers", transformers.__version__)
        try:
            import tokenizers

            print("tokenizers", tokenizers.__version__)
        except Exception:
            pass
        from TTS.api import TTS  # noqa: F401

        print("TTS_IMPORT=OK")
    except Exception as exc:
        print(f"TTS_IMPORT=FAIL {type(exc).__name__}: {exc}")
        return 3
    print("DEPS_VOZ=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
