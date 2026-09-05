#!/usr/bin/env python3
"""AURA QUANT-X health check. Read-only: does not install, download or modify anything."""
from __future__ import annotations
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def check(name, fn):
    try:
        value = fn()
        return {"status": "OK", "detail": value}
    except Exception as exc:
        return {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}

def module_version(name):
    mod = importlib.import_module(name)
    return getattr(mod, "__version__", "import OK")

def cuda_count():
    import ctranslate2
    return str(ctranslate2.get_cuda_device_count())

def whisper_gpu():
    from faster_whisper import WhisperModel
    WhisperModel("tiny", device="cuda", compute_type="float16")
    return "WhisperModel tiny / cuda / float16 inicializado"

def ollama():
    exe = shutil.which("ollama")
    if not exe:
        raise RuntimeError("ollama não encontrado no PATH")
    out = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=15)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip() or f"exit {out.returncode}")
    return exe

def essential_files():
    files = ["server.py", "jarvis_voice_server.py", "requirements_voice.txt", "jarvis/config.yaml"]
    missing = [f for f in files if not (ROOT / f).is_file()]
    if missing:
        raise RuntimeError("ausentes: " + ", ".join(missing))
    return "todos presentes"

def main():
    py_ok = sys.version_info[:2] == (3, 11)
    results = {
        "Python": {"status": "OK" if py_ok else "FAIL", "detail": sys.version.split()[0]},
        "NumPy": check("numpy", lambda: module_version("numpy")),
        "faster-whisper": check("faster_whisper", lambda: module_version("faster_whisper")),
        "CTranslate2": check("ctranslate2", lambda: module_version("ctranslate2")),
        "CUDA": check("cuda", cuda_count),
        "Whisper GPU": check("whisper", whisper_gpu),
        "Ollama": check("ollama", ollama),
        "Bridge files": check("files", essential_files),
        "Voice Server": {"status": "NOT TESTED", "detail": "health check não inicia o servidor"},
    }
    print("AURA QUANT-X HEALTH CHECK")
    print("=" * 26)
    for name, item in results.items():
        print(f"{name:<18} {item['status']:<10} {item['detail']}")
    print("\nJSON COMPACTO")
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
    return 0 if all(v["status"] in {"OK", "NOT TESTED"} for v in results.values()) else 1

if __name__ == "__main__":
    raise SystemExit(main())
