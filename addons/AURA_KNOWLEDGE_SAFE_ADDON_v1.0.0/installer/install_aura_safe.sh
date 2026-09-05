#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:---plan}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/../addon/aura_maximizer" ]]; then
  SOURCE_DIR="$(cd "$SCRIPT_DIR/../addon" && pwd)"
else
  SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
TARGET_DIR="${AURA_ROOT:-}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="${AURA_INSTALL_REPORT_DIR:-$PWD/aura_install_reports/$STAMP}"
BACKUP_DIR=""

log(){ printf '[AURA-INSTALL] %s\n' "$*"; }
die(){ printf '[AURA-INSTALL][ERRO] %s\n' "$*" >&2; exit 1; }

usage(){
  cat <<'EOF'
Uso:
  ./install_aura_safe.sh --plan                 Apenas inspeciona e gera o plano.
  AURA_ROOT=/caminho/aura ./install_aura_safe.sh --stage   Copia para staging e testa.
  AURA_ROOT=/caminho/aura ./install_aura_safe.sh --install Instala sem sobrescrever arquivos existentes.
  AURA_ROOT=/caminho/aura ./install_aura_safe.sh --verify  Valida a instalação local.

Guardrails permanentes:
  nenhum serviço, rede, scheduler, voz, MCP, LLM, container ou processo externo é iniciado.
  execução financeira permanece bloqueada; arquivos existentes nunca são sobrescritos.
EOF
}

find_target(){
  if [[ -n "$TARGET_DIR" ]]; then return; fi
  for candidate in "$PWD" "$PWD/AURA" "$HOME/AURA" "$HOME/aura"; do
    if [[ -d "$candidate" && ( -f "$candidate/README.md" || -d "$candidate/engine" || -d "$candidate/config" ) ]]; then
      TARGET_DIR="$(cd "$candidate" && pwd)"; return
    fi
  done
}

manifest(){
  find "$SOURCE_DIR" -type f -print0 | sort -z | xargs -0 sha256sum
}

plan(){
  mkdir -p "$REPORT_DIR"
  find_target
  {
    echo "timestamp=$STAMP"
    echo "source=$SOURCE_DIR"
    echo "target=${TARGET_DIR:-UNRESOLVED}"
    echo "mode=$MODE"
    echo "paper_trade=true"
    echo "execution_allowed=false"
    echo "network_enabled=false"
    echo "scheduler_enabled=false"
    echo "tool_execution_enabled=false"
    echo "existing_files_are_never_overwritten=true"
  } > "$REPORT_DIR/plan.env"
  manifest > "$REPORT_DIR/source.sha256"
  if [[ -z "$TARGET_DIR" ]]; then
    log "Nenhum AURA_ROOT detectado. Isso é esperado no modo --plan."
  else
    log "AURA detectado em: $TARGET_DIR"
  fi
  log "Plano salvo em: $REPORT_DIR"
}

stage(){
  [[ -n "$TARGET_DIR" && -d "$TARGET_DIR" ]] || die "Defina AURA_ROOT apontando para a raiz do AURA."
  mkdir -p "$REPORT_DIR/staging"
  cp -a "$SOURCE_DIR/." "$REPORT_DIR/staging/"
  (cd "$REPORT_DIR/staging" && python3 -m compileall -q aura_maximizer tests)
  (cd "$REPORT_DIR/staging" && python3 -m unittest discover -s tests -q)
  log "Staging e self-test offline aprovados: $REPORT_DIR/staging"
}

install_safe(){
  [[ -n "$TARGET_DIR" && -d "$TARGET_DIR" ]] || die "Defina AURA_ROOT apontando para a raiz do AURA."
  stage
  BACKUP_DIR="$TARGET_DIR/addons/aura_maximizer_backup_$STAMP"
  mkdir -p "$BACKUP_DIR" "$TARGET_DIR/addons/aura_maximizer"
  find "$REPORT_DIR/staging" -type f -print0 | while IFS= read -r -d '' src; do
    rel="${src#"$REPORT_DIR/staging/"}"
    dst="$TARGET_DIR/addons/aura_maximizer/$rel"
    mkdir -p "$(dirname "$dst")"
    if [[ -e "$dst" ]]; then
      cp -a "$dst" "$BACKUP_DIR/$(echo "$rel" | tr '/' '__').existing"
      log "Preservado arquivo existente: $rel"
    else
      cp -a "$src" "$dst"
    fi
  done
  {
    echo "timestamp=$STAMP"
    echo "target=$TARGET_DIR"
    echo "backup=$BACKUP_DIR"
    echo "mode=installed_inert"
    echo "services_started=0"
    echo "network_calls=0"
    echo "files_overwritten=0"
  } > "$TARGET_DIR/addons/aura_maximizer/INSTALLATION_RECORD.env"
  cp "$REPORT_DIR/source.sha256" "$TARGET_DIR/addons/aura_maximizer/SOURCE.sha256"
  log "Addon instalado de forma não destrutiva em $TARGET_DIR/addons/aura_maximizer"
  log "Backup/arquivos conflitantes em $BACKUP_DIR"
}

verify(){
  [[ -n "$TARGET_DIR" && -d "$TARGET_DIR/addons/aura_maximizer" ]] || die "Addon não encontrado."
  (cd "$TARGET_DIR/addons/aura_maximizer" && python3 -m compileall -q aura_maximizer tests)
  (cd "$TARGET_DIR/addons/aura_maximizer" && python3 -m unittest discover -s tests -q)
  grep -Rqs 'execution_allowed=false' "$TARGET_DIR/addons/aura_maximizer" || die "Guardrail execution_allowed ausente."
  grep -Rqs 'paper_trade=true' "$TARGET_DIR/addons/aura_maximizer" || die "Guardrail paper_trade ausente."
  log "Verificação offline aprovada; nenhuma integração foi ativada."
}

case "$MODE" in
  --help|-h) usage;;
  --plan) plan;;
  --stage) plan; stage;;
  --install) plan; install_safe;;
  --verify) verify;;
  *) usage; die "Modo inválido: $MODE";;
esac
