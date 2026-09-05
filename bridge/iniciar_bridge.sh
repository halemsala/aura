#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[ERRO] Ambiente .venv não encontrado. Crie-o com Python 3.11 e instale requirements_voice.txt." >&2
  exit 1
fi
exec "$PY" server.py "$@"
