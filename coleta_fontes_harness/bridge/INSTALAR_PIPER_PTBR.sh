#!/usr/bin/env bash
set -euo pipefail
PIPER_DIR="${HOME}/.local/share/piper"
MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
CFG_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json"
MODEL_PATH="${PIPER_DIR}/pt_BR-faber-medium.onnx"
CFG_PATH="${PIPER_DIR}/pt_BR-faber-medium.onnx.json"
mkdir -p "${PIPER_DIR}"
echo "Baixando Piper pt-BR (faber medium)..."
curl -L --fail -o "${MODEL_PATH}" "${MODEL_URL}"
curl -L --fail -o "${CFG_PATH}" "${CFG_URL}"
echo "Modelo em ${MODEL_PATH}"
if ! command -v piper >/dev/null 2>&1; then
  echo "AVISO: binario piper nao esta no PATH. Instale: https://github.com/rhasspy/piper/releases"
fi
echo "export AURA_PIPER_MODEL=${MODEL_PATH}"
echo "export AURA_PIPER_BIN=piper"
