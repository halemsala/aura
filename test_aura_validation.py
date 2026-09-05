#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostico AURA / Hermes — porta real 8777 (nao 8000)."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HERMES = ROOT / "hermes_v10"
for p in (HERMES, ROOT):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

def test_module_imports():
    print("[1/4] Importacoes...")
    try:
        from core.hermes_llm_engine import HermesLLMEngine  # noqa: F401
        print("  OK  core.hermes_llm_engine")
        return True
    except Exception as e:
        print(f"  FALHA core.hermes_llm_engine: {e}")
        return False

def test_sqlite_vec():
    print("\n[2/4] sqlite-vec...")
    try:
        import sqlite_vec  # noqa: F401
        print("  OK  sqlite_vec")
        return True
    except Exception:
        print("  AVISO sqlite_vec ausente (fallback text-only)")
        return False

def test_api(base="http://127.0.0.1:8777"):
    print(f"\n[3/4] API {base}...")
    try:
        import requests
    except ImportError:
        print("  FALHA: pip install requests")
        return False
    ok = True
    for ep in ("/health", "/api/system"):
        url = base + ep
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                print(f"  OK  GET {ep} -> 200 | keys={list(data)[:8] if isinstance(data, dict) else type(data)}")
                if isinstance(data, dict) and "glm_enabled" in data:
                    print(f"       glm_enabled={data.get('glm_enabled')} hermes_llm={data.get('hermes_llm')} ollama_ok={data.get('ollama_ok')}")
            else:
                print(f"  FALHA GET {ep} -> {r.status_code} {r.text[:120]}")
                ok = False
        except requests.exceptions.ConnectionError:
            print(f"  FALHA GET {ep} -> API offline em {base}")
            ok = False
        except Exception as e:
            print(f"  FALHA GET {ep} -> {e}")
            ok = False
    return ok

def test_ollama():
    print("\n[4/4] Ollama :11434...")
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
            print(f"  OK  Ollama HTTP {resp.status}")
            return True
    except Exception as e:
        print(f"  AVISO Ollama: {e}")
        return False

if __name__ == "__main__":
    print("==========================================")
    print("   DIAGNOSTICO AURA / HERMES LLM")
    print("==========================================\n")
    test_module_imports()
    test_sqlite_vec()
    test_api("http://127.0.0.1:8777")
    test_ollama()
    print("\n==========================================")
