#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/engine/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[!] Create venv: python3 -m venv engine/venv && source engine/venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
fuser -k 8080/tcp 8765/tcp 2>/dev/null || true
export PAPER_TRADE=true EXECUTION_ALLOWED=false GLM_ADVISORY_ONLY=1
export PYTHONUNBUFFERED=1
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
echo "[*] Bridge :8080"
(cd "${ROOT}/bridge" && "$PY" -u server.py --host 127.0.0.1 --port 8080 >> "${ROOT}/bridge/runtime_bridge.log" 2>&1) &
echo "[*] Engine :8765"
(cd "${ROOT}/engine" && "$PY" -u server.py --host 127.0.0.1 --port 8765 >> "${ROOT}/engine/runtime_engine.log" 2>&1) &
sleep 3
curl -s -o /dev/null -w "bridge HTTP %{http_code}\n" http://127.0.0.1:8080/health || true
curl -s -o /dev/null -w "engine HTTP %{http_code}\n" http://127.0.0.1:8765/api/health || true
echo "[*] Stop: fuser -k 8080/tcp 8765/tcp"
