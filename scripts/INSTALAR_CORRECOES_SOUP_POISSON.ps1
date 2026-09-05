# AURA QUANT-X — Instalador seguro Soup + Poisson/GLM
# Execute no PowerShell a partir da pasta extraída deste zip
# Uso: .\scripts\INSTALAR_NO_AURA.ps1

param(
    [string]$AURA_ROOT = "C:\aura"
)

$ErrorActionPreference = "Stop"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $AURA_ROOT "_backup_complete_$Timestamp"
$SoupTarget = Join-Path $AURA_ROOT "addons\installation_aura_soup_layer_streaming"
$PoissonTarget = Join-Path $AURA_ROOT "addons\installation_poisson_glm"
$EngineDir = Join-Path $AURA_ROOT "engine"

Write-Host "============================================================"
Write-Host " AURA QUANT-X — Instalacao Segura Soup + Poisson/GLM"
Write-Host " AURA_ROOT = $AURA_ROOT"
Write-Host "============================================================"

if (-not (Test-Path $AURA_ROOT)) {
    Write-Error "AURA_ROOT nao encontrado: $AURA_ROOT"
    exit 1
}

# Backup
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Write-Host "[OK] Backup criado: $BackupDir"

# Soup (namespace isolado)
New-Item -ItemType Directory -Force -Path $SoupTarget | Out-Null
$SourceSoup = Join-Path $PSScriptRoot "..\addons\installation_aura_soup_layer_streaming"
Copy-Item -Recurse -Force "$SourceSoup\*" $SoupTarget
Write-Host "[OK] Skill Soup instalada em: $SoupTarget"

# Poisson/GLM addon isolado
New-Item -ItemType Directory -Force -Path $PoissonTarget | Out-Null
$SourcePoisson = Join-Path $PSScriptRoot "..\addons\installation_poisson_glm"
Copy-Item -Force "$SourcePoisson\*" $PoissonTarget
Write-Host "[OK] Poisson/GLM addon em: $PoissonTarget"

# Poisson/GLM no engine (com backup dos originais se existirem)
foreach ($f in @("poisson_risk_engine.py", "agent_glm_runtime.py")) {
    $src = Join-Path $PSScriptRoot "..\engine\$f"
    $dst = Join-Path $EngineDir $f
    if (Test-Path $dst) {
        Copy-Item -Force $dst (Join-Path $BackupDir $f)
        Write-Host "[BACKUP] $f -> $BackupDir"
    }
    Copy-Item -Force $src $dst
    Write-Host "[OK] Engine atualizado: $f"
}

# Validacao offline
Write-Host ""
Write-Host "[..] Validando Soup bridge..."
Push-Location $SoupTarget
python -m py_compile .\aura_soup_bridge.py
if ($LASTEXITCODE -ne 0) { Write-Error "py_compile falhou"; exit 1 }
python -m unittest discover -s .\tests -q
if ($LASTEXITCODE -ne 0) { Write-Error "testes falharam"; exit 1 }
Pop-Location
Write-Host "[OK] Testes Soup passaram"

Write-Host ""
Write-Host "============================================================"
Write-Host " INSTALACAO CONCLUIDA"
Write-Host "============================================================"
Write-Host " Skill Soup     : $SoupTarget"
Write-Host " Poisson/GLM    : $PoissonTarget + engine\"
Write-Host " Backup         : $BackupDir"
Write-Host " Services       : 0"
Write-Host " Network calls  : 0"
Write-Host " execution_allowed : false"
Write-Host ""
Write-Host "Proximos passos:"
Write-Host "  1. RODAR_TESTE_AUTOMATICO.bat"
Write-Host "  2. (Opcional) Abrir Dashboard: interface\aura-quant-x-dashboard\ABRIR_INTERFACE.bat"
