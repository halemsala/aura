# Inicia Bridge, Engine, Ollama, Voice (ordem segura)
param([string]$AURA_ROOT = "C:\aura")
$ErrorActionPreference = "Continue"
cd $AURA_ROOT
$env:AURA_ROOT = $AURA_ROOT
$env:PYTHONPATH = "$AURA_ROOT;$AURA_ROOT\engine;$AURA_ROOT\addons\installation_aura_soup_layer_streaming"

Write-Host "=== Iniciando servicos AURA ===" -ForegroundColor Cyan

# Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized -ErrorAction SilentlyContinue
    Write-Host "[OK] Ollama serve" -ForegroundColor Green
} else {
    Write-Host "[!!] ollama nao no PATH" -ForegroundColor Yellow
}

Start-Sleep -Seconds 3

# INICIAR_TUDO se existir
if (Test-Path ".\INICIAR_TUDO.bat") {
    Start-Process -FilePath ".\INICIAR_TUDO.bat" -WorkingDirectory $AURA_ROOT
    Write-Host "[OK] INICIAR_TUDO.bat" -ForegroundColor Green
} elseif (Test-Path ".\AURA_TUDO_EM_UM.bat") {
    Start-Process -FilePath ".\AURA_TUDO_EM_UM.bat" -WorkingDirectory $AURA_ROOT
    Write-Host "[OK] AURA_TUDO_EM_UM.bat" -ForegroundColor Green
} else {
    Write-Host "[!!] Nenhum bat de inicio encontrado" -ForegroundColor Yellow
}

Write-Host "Aguarde 45s e rode: .\RODAR_TESTE_AUTOMATICO.bat"
