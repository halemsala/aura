param([string]$AURA_ROOT = "C:\aura")
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "engine\agents\aura_hermes_router.py"
$dst = Join-Path $AURA_ROOT "engine\agents\aura_hermes_router.py"
$bak = Join-Path $AURA_ROOT "engine\agents\aura_hermes_router.py.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
if (-not (Test-Path $src)) { Write-Error "Fonte nao encontrada: $src"; exit 1 }
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
if (Test-Path $dst) { Copy-Item -Force $dst $bak; Write-Host "Backup: $bak" }
Copy-Item -Force $src $dst
Write-Host "[OK] Hermes router atualizado: $dst" -ForegroundColor Green
# copy start script
$ssrc = Join-Path $PSScriptRoot "scripts\INICIAR_SERVICOS_AURA.ps1"
$sdst = Join-Path $AURA_ROOT "scripts\INICIAR_SERVICOS_AURA.ps1"
New-Item -ItemType Directory -Force -Path (Split-Path $sdst) | Out-Null
Copy-Item -Force $ssrc $sdst
Write-Host "[OK] Script de start: $sdst" -ForegroundColor Green
Write-Host ""
Write-Host "Proximos passos:"
Write-Host "  powershell -ExecutionPolicy Bypass -File $sdst"
Write-Host "  cd $AURA_ROOT ; .\RODAR_TESTE_AUTOMATICO.bat"
