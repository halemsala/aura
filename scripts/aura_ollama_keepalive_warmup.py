#!/usr/bin/env python3
"""Warm-up Ollama com keep_alive real (API)."""
import json, os, sys
from urllib.request import Request, urlopen
model = os.environ.get("CORNERAI_CHAT_MODEL", "llama3.2:3b")
keep = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
body = json.dumps({"model": model, "prompt": "ok", "stream": False, "keep_alive": keep, "options": {"num_predict": 4}}).encode()
try:
    req = Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as r:
        print(r.read().decode()[:200])
    print("OK keep_alive=", keep, "model=", model)
except Exception as e:
    print("FAIL", e)
    sys.exit(1)
