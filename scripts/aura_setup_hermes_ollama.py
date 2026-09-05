#!/usr/bin/env python3
"""Verifica Ollama + preferencia Hermes (sem GLM)."""
import json, os, urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("AURA_ROOT", Path(__file__).resolve().parents[1]))
PREF = ROOT / "engine" / "data" / "llm_preference.json"

def main():
    pref = {
        "backend": "hermes",
        "provider": "ollama",
        "base_url": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "model": os.environ.get("CORNERAI_CHAT_MODEL", "llama3.2:3b"),
        "fallback_model": os.environ.get("AURA_OLLAMA_FALLBACK", "llama3.2:1b"),
        "glm_enabled": False,
    }
    PREF.parent.mkdir(parents=True, exist_ok=True)
    PREF.write_text(json.dumps(pref, indent=2), encoding="utf-8")
    print("preference written", PREF)
    try:
        with urllib.request.urlopen(pref["base_url"] + "/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
        names = [m.get("name") for m in data.get("models") or []]
        print("ollama models:", names)
        ok = any("llama3.2" in (n or "") for n in names)
        print("hermes_model_present:", ok)
        return 0 if ok else 2
    except Exception as e:
        print("ollama unreachable:", e)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
