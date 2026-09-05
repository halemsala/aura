# AURA QUANT-X — Instalacao completa + integracao Python
# powershell -ExecutionPolicy Bypass -File .\scripts\INSTALAR_COMPLETO_AURA.ps1

param([string]$AURA_ROOT = "C:\aura")

$ErrorActionPreference = "Continue"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " AURA QUANT-X — Instalacao Completa + Python Integration" -ForegroundColor Cyan
Write-Host "============================================================"

# 1) Stop
Get-Process | Where-Object { $_.ProcessName -match "Aura\.QuantX|python|node|ollama" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2) Backup
if (Test-Path $AURA_ROOT) {
    $bak = "C:\aura_backup_$ts"
    try {
        Rename-Item $AURA_ROOT $bak -ErrorAction Stop
        Write-Host "[OK] Backup: $bak" -ForegroundColor Green
    } catch {
        Write-Host "[!!] Nao foi possivel renomear C:\aura (em uso?). Continuando com merge." -ForegroundColor Yellow
    }
}

# 3) Localizar fonte
$zip = Get-ChildItem -Path "$env:USERPROFILE\Downloads","$env:USERPROFILE\Desktop","C:\" -Filter "*FULL_SYSTEM*SOUP*.zip" -Recurse -ErrorAction SilentlyContinue -Depth 4 | Select-Object -First 1
$folder = Get-ChildItem -Path "$env:USERPROFILE\Downloads","$env:USERPROFILE\Desktop","C:\" -Filter "AURA_QUANT_X_12.7.46" -Directory -Recurse -ErrorAction SilentlyContinue -Depth 5 | Select-Object -First 1

if ($folder) {
    $SRC = $folder.FullName
    Write-Host "[OK] Pasta: $SRC" -ForegroundColor Green
} elseif ($zip) {
    $extractTo = "$env:TEMP\AURA_INSTALL_$ts"
    Expand-Archive -Path $zip.FullName -DestinationPath $extractTo -Force
    $SRC = (Get-ChildItem -Path $extractTo -Filter "AURA_QUANT_X_12.7.46" -Directory -Recurse | Select-Object -First 1).FullName
    Write-Host "[OK] Extraido: $SRC" -ForegroundColor Green
} else {
    Write-Host "ERRO: Baixe e extraia AURA_QUANT_X_12.7.60_FULL_SYSTEM_WITH_SOUP_POISSON.zip" -ForegroundColor Red
    exit 1
}

# 4) Copiar
New-Item -ItemType Directory -Force -Path $AURA_ROOT | Out-Null
Copy-Item -Recurse -Force "$SRC\*" $AURA_ROOT
Write-Host "[OK] Sistema em $AURA_ROOT" -ForegroundColor Green

# 5) PYTHONPATH
$env:AURA_ROOT = $AURA_ROOT
$env:PYTHONPATH = "$AURA_ROOT;$AURA_ROOT\engine;$AURA_ROOT\addons\installation_aura_soup_layer_streaming"
Write-Host "[OK] PYTHONPATH configurado nesta sessao" -ForegroundColor Green

# 6) Checker
$checker = Join-Path $AURA_ROOT "tools\python\AURA_PYTHON_INTEGRATION.py"
if (Test-Path $checker) {
    Write-Host ""
    & python $checker
}

# 7) Iniciar
Write-Host ""
Write-Host "Iniciando AURA..." -ForegroundColor Yellow
cd $AURA_ROOT
if (Test-Path ".\INICIAR_TUDO.bat") {
    Start-Process -FilePath ".\INICIAR_TUDO.bat" -WorkingDirectory $AURA_ROOT
    Start-Sleep -Seconds 40
}

# 8) Teste
if (Test-Path ".\RODAR_TESTE_AUTOMATICO.bat") {
    & .\RODAR_TESTE_AUTOMATICO.bat
}

Write-Host ""
Write-Host "=== INSTALACAO COMPLETA FINALIZADA ===" -ForegroundColor Green
