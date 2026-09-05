# AURA — Configura PYTHONPATH e integra Python com o engine
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\CONFIGURAR_PYTHON_AURA.ps1

param([string]$AURA_ROOT = "C:\aura")

$ErrorActionPreference = "Stop"
Write-Host "=== Configurando Python para AURA ===" -ForegroundColor Cyan
Write-Host "AURA_ROOT = $AURA_ROOT"

if (-not (Test-Path $AURA_ROOT)) {
    Write-Error "AURA_ROOT nao encontrado: $AURA_ROOT"
    exit 1
}

# PYTHONPATH persistente para o usuario (sessao atual + perfil)
$paths = @(
    $AURA_ROOT,
    (Join-Path $AURA_ROOT "engine"),
    (Join-Path $AURA_ROOT "addons\installation_aura_soup_layer_streaming")
) | Where-Object { Test-Path $_ }

$joined = ($paths -join ";")
$env:PYTHONPATH = $joined
$env:AURA_ROOT = $AURA_ROOT

# Garante pastas
New-Item -ItemType Directory -Force -Path (Join-Path $AURA_ROOT "engine\data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AURA_ROOT "logs_supervisor") | Out-Null

Write-Host "[OK] PYTHONPATH = $env:PYTHONPATH" -ForegroundColor Green
Write-Host "[OK] AURA_ROOT   = $env:AURA_ROOT" -ForegroundColor Green

# Teste rapido
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    Write-Host "[OK] Python: $($py.Source)" -ForegroundColor Green
    & python -c "import sys; print('sys.path[0:3]=', sys.path[:3])"
} else {
    Write-Host "[!!] Python nao encontrado no PATH" -ForegroundColor Yellow
}

# Roda integration checker se existir
$checker = Join-Path $AURA_ROOT "tools\python\AURA_PYTHON_INTEGRATION.py"
if (Test-Path $checker) {
    Write-Host ""
    Write-Host "Rodando integration checker..." -ForegroundColor Cyan
    & python $checker
}

Write-Host ""
Write-Host "=== Pronto. Use esta sessao do PowerShell para rodar o AURA. ===" -ForegroundColor Green
