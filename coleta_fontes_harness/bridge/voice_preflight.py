from __future__ import annotations

import importlib
import json
import os
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("fastapi", "uvicorn", "pydantic", "yaml", "requests", "numpy", "faster_whisper", "ctranslate2", "sounddevice", "edge_tts")
OPTIONAL = ("torch", "TTS")
REFERENCE_WAV = ROOT / "bridge" / "jarvis" / "voices" / "voz_masculina_referencia.wav"
PROFILE_FILE = ROOT / "voice_profiles" / "PERFIL_ASSISTENTE_ESPORTIVO_ANALITICO.md"
PROMPT_FILE = ROOT / "voice_profiles" / "PROMPT_GROK_VOZ_MASCULINA.md"
APPROVED_MALE_VOICES = {"pt-BR-HumbertoNeural", "pt-BR-NicolauNeural", "pt-BR-DonatoNeural", "hercules", "pt-BR-faber-medium"}


def probe(names: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        try:
            module = importlib.import_module(name)
            result[name] = str(getattr(module, "__version__", "ok"))
        except Exception as exc:  # pragma: no cover - depends on target venv
            result[name] = f"ERROR: {type(exc).__name__}: {exc}"
    return result


def inspect_reference_wav() -> dict[str, object]:
    result: dict[str, object] = {"path": str(REFERENCE_WAV), "present": REFERENCE_WAV.is_file(), "valid": False}
    if not REFERENCE_WAV.is_file():
        return result
    try:
        with wave.open(str(REFERENCE_WAV), "rb") as handle:
            duration = handle.getnframes() / max(1, handle.getframerate())
            result.update({
                "valid": handle.getnchannels() >= 1 and handle.getframerate() >= 8000 and duration >= 1.0,
                "channels": handle.getnchannels(),
                "sample_rate_hz": handle.getframerate(),
                "duration_seconds": round(duration, 3),
            })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    cfg = ROOT / "bridge" / "jarvis" / "config.yaml"
    try:
        import yaml
        with cfg.open("r", encoding="utf-8") as handle:
            yaml_cfg = yaml.safe_load(handle) or {}
    except Exception:
        yaml_cfg = {}
    tts_cfg = yaml_cfg.get("tts") or {}
    configured_voice = str(tts_cfg.get("voice_name") or "pt-BR-AntonioNeural")
    voice_policy_ok = configured_voice in APPROVED_MALE_VOICES
    required = probe(REQUIRED)
    optional = probe(OPTIONAL)
    missing = {name: value for name, value in required.items() if value.startswith("ERROR:")}
    reference = inspect_reference_wav()
    profile = {
        "reference_wav": reference,
        "profile_file": str(PROFILE_FILE),
        "profile_present": PROFILE_FILE.is_file(),
        "prompt_file": str(PROMPT_FILE),
        "prompt_present": PROMPT_FILE.is_file(),
        "reference_engine": "xtts/coqui disponível" if not optional["TTS"].startswith("ERROR:") else "somente referência; TTS não instalado",
        "mode": os.getenv("AURA_TTS_ENGINE", "edge"),
        "configured_voice": configured_voice,
        "voice_policy_ok": voice_policy_ok,
        "fallback_policy": "disabled; no female/browser/gTTS fallback",
    }
    requested_mode = os.getenv("AURA_TTS_ENGINE", "edge").strip().lower()
    reference_ok = bool(reference["present"] and reference["valid"])
    profile_ok = bool(profile["profile_present"] and profile["prompt_present"])
    xtts_ok = not (requested_mode in {"xtts", "xtts-reference", "reference"} and optional["TTS"].startswith("ERROR:"))
    report = {
        "ok": not missing and cfg.is_file() and reference_ok and profile_ok and xtts_ok and voice_policy_ok,
        "python": sys.executable,
        "python_version": sys.version,
        "config_exists": cfg.is_file(),
        "required": required,
        "optional": optional,
        "missing_required": missing,
        "voice_reference": profile,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not cfg.is_file():
        print(f"VOICE_PREFLIGHT_FAIL: configuração ausente: {cfg}")
        return 1
    if missing:
        print("VOICE_PREFLIGHT_FAIL: dependências ausentes na venv usada pelo Voice.")
        return 1
    if requested_mode in {"xtts", "xtts-reference", "reference"} and optional["TTS"].startswith("ERROR:"):
        print("VOICE_PREFLIGHT_FAIL: modo XTTS solicitado, mas coqui-tts/TTS não está instalado.")
        return 1
    if not voice_policy_ok:
        print(f"VOICE_PREFLIGHT_FAIL: voz não aprovada pela política masculina: {configured_voice}")
        return 1
    if not reference["present"] or not reference["valid"]:
        print("VOICE_PREFLIGHT_FAIL: WAV de referência ausente ou inválido.")
        return 1
    if not profile["profile_present"] or not profile["prompt_present"]:
        print("VOICE_PREFLIGHT_FAIL: perfil ou prompt de voz ausente.")
        return 1
    print("VOICE_PREFLIGHT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
