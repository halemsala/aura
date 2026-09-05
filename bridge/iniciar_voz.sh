#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[ERRO] Ambiente .venv não encontrado. Crie-o com Python 3.11 e instale requirements_voice.txt." >&2
  exit 1
fi
if ! "$PY" -c 'import numpy, faster_whisper, ctranslate2, requests, yaml' >/dev/null 2>&1; then
  echo "[ERRO] Dependências FAST ausentes no .venv. Instale: $PY -m pip install -r requirements_voice.txt" >&2
  exit 1
fi
exec "$PY" jarvis_voice_server.py --port 8099 "$@"
