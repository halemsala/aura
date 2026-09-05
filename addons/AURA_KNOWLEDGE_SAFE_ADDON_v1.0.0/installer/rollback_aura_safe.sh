#!/usr/bin/env bash
set -Eeuo pipefail
TARGET_DIR="${AURA_ROOT:-}"
[[ -n "$TARGET_DIR" ]] || { echo 'Defina AURA_ROOT.' >&2; exit 1; }
[[ -d "$TARGET_DIR/addons/aura_maximizer" ]] || { echo 'Addon não encontrado.' >&2; exit 1; }
LATEST_BACKUP="$(find "$TARGET_DIR/addons" -maxdepth 1 -type d -name 'aura_maximizer_backup_*' | sort | tail -n 1)"
[[ -n "$LATEST_BACKUP" && -d "$LATEST_BACKUP" ]] || { echo 'Backup não encontrado; nada foi alterado.' >&2; exit 1; }
printf '[AURA-ROLLBACK] O backup mais recente é: %s\n' "$LATEST_BACKUP"
printf '[AURA-ROLLBACK] Para completar o rollback, mova o addon atual para um diretório de quarentena e restaure apenas os arquivos listados no backup.\n'
printf '[AURA-ROLLBACK] Nenhuma remoção automática foi executada para evitar perda de dados.\n'
