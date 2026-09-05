#!/usr/bin/env python3
"""Chama o Engine para diagnostico completo + LLM e imprime texto."""
import json, sys, urllib.request
url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/api/diagnostics/matrix-full?llm=true"
with urllib.request.urlopen(url, timeout=180) as r:
    data = json.loads(r.read().decode())
print(data.get("report_text") or json.dumps(data, indent=2, ensure_ascii=False))
print("\n--- badges ---")
print(json.dumps(data.get("matrix"), indent=2, ensure_ascii=False))
