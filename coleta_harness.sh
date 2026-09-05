#!/bin/bash
# =====================================================
# Coleta de informações para análise e criação de API de teste
# =====================================================

echo "=============================================="
echo "   COLETA DE INFORMAÇÕES - AMBIENTE HARNESS"
echo "=============================================="
echo ""

# 1. Informações do sistema
echo "### 1. SISTEMA OPERACIONAL ###"
uname -a
cat /etc/os-release 2>/dev/null | head -5
echo ""

echo "### 2. RECURSOS (CPU/MEMÓRIA) ###"
echo "CPUs: $(nproc)"
free -h | head -2
echo ""

# 3. Informações do Harness Delegate (se instalado)
echo "### 3. HARNESS DELEGATE ###"
if command -v harness-delegate &>/dev/null; then
    harness-delegate --version 2>/dev/null || echo "Versão não disponível"
    systemctl status harness-delegate --no-pager -l | head -20 2>/dev/null || echo "Não roda via systemd"
else
    echo "Delegate não encontrado no PATH. Verificando processos..."
    ps aux | grep -i delegate | grep -v grep | head -5
fi
echo ""

# 4. Localização da pasta aura (busca automática)
echo "### 4. LOCALIZAÇÃO DA PASTA 'aura' ###"
AURA_PATHS=$(find / -type d -name "aura" 2>/dev/null | head -5)
if [ -z "$AURA_PATHS" ]; then
    echo "Pasta 'aura' não encontrada automaticamente. Informe o caminho manualmente."
else
    echo "Candidatos encontrados:"
    echo "$AURA_PATHS"
fi
echo ""

# 5. Se a pasta aura existir, coletar detalhes
# Substitua /caminho/para/aura pelo caminho real se souber
if [ -n "$AURA_PATH" ]; then
    AURA_DIR="$AURA_PATH"
elif [ -n "$AURA_PATHS" ]; then
    AURA_DIR=$(echo "$AURA_PATHS" | head -1)
else
    AURA_DIR=""
fi

if [ -n "$AURA_DIR" ] && [ -d "$AURA_DIR" ]; then
    echo "### 5. CONTEÚDO DA PASTA AURA ($AURA_DIR) ###"
    echo "Tamanho total: $(du -sh "$AURA_DIR" 2>/dev/null | cut -f1)"
    echo "Número de arquivos: $(find "$AURA_DIR" -type f | wc -l)"
    echo "Número de diretórios: $(find "$AURA_DIR" -type d | wc -l)"
    echo ""
    echo "Arquivos principais (top 20 por tamanho):"
    find "$AURA_DIR" -type f -exec ls -lh {} \; 2>/dev/null | sort -k5 -hr | head -20
    echo ""
    echo "Estrutura de diretórios (nível 2):"
    find "$AURA_DIR" -maxdepth 2 -type d | sed "s|$AURA_DIR||" | sort
    echo ""
    echo "Permissões de arquivos/diretórios (amostra):"
    find "$AURA_DIR" -maxdepth 2 -exec stat -c "%A %U:%G %n" {} \; 2>/dev/null | head -30
    echo ""
    echo "Amostra de conteúdo (primeiras linhas de arquivos .log, .txt, .json, .xml):"
    find "$AURA_DIR" -type f \( -name "*.log" -o -name "*.txt" -o -name "*.json" -o -name "*.xml" \) -exec sh -c 'echo "--- $1"; head -5 "$1"' _ {} \; 2>/dev/null | head -100
else
    echo "### 5. PASTA AURA NÃO ACESSÍVEL ###"
    echo "Não foi possível acessar a pasta aura. Verifique o caminho e permissões."
fi
echo ""

# 6. Logs recentes do delegate (se souber onde estão)
echo "### 6. LOGS RECENTES DO DELEGATE ###"
DELEGATE_LOG_PATHS=(
    "$HOME/harness-delegate/logs/delegate.log"
    "/var/log/harness/delegate.log"
    "/opt/harness-delegate/logs/delegate.log"
)
for log in "${DELEGATE_LOG_PATHS[@]}"; do
    if [ -f "$log" ]; then
        echo "Arquivo de log: $log"
        tail -30 "$log"
        break
    fi
done
echo ""

# 7. Saída em JSON para facilitar análise (opcional)
echo "### 7. RESUMO EM JSON ###"
cat <<EOF
{
  "sistema": {
    "so": "$(uname -s)",
    "kernel": "$(uname -r)",
    "cpu": "$(nproc)",
    "memoria": "$(free -h | awk '/Mem:/ {print $2}')"
  },
  "delegate": {
    "processo": "$(ps aux | grep -i delegate | grep -v grep | head -1 | awk '{print $11, $12, $13}')",
    "status": "$(systemctl is-active harness-delegate 2>/dev/null || echo 'desconhecido')"
  },
  "pasta_aura": {
    "caminho": "$AURA_DIR",
    "tamanho": "$(du -sh "$AURA_DIR" 2>/dev/null | cut -f1)",
    "arquivos": "$(find "$AURA_DIR" -type f 2>/dev/null | wc -l)",
    "diretorios": "$(find "$AURA_DIR" -type d 2>/dev/null | wc -l)"
  }
}
EOF

echo ""
echo "=============================================="
echo " Fim da coleta. Copie e cole esta saída."
echo "=============================================="