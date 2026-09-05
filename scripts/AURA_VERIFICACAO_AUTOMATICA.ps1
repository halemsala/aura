# ============================================================
# AURA QUANT-X - Verificação Automática (atualizada)
# Versão: V25T15-CORRECAO-VENV
# ============================================================

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " AURA QUANT-X - VERIFICAÇÃO AUTOMÁTICA" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

$problems = @()
$okCount = 0

# 1. Bridge
Write-Host "[1] Bridge (porta 8080)..." -NoNewline
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 5
    if ($health.ok -eq $true) {
        Write-Host " OK" -ForegroundColor Green
        Write-Host "     feedLines     = $($health.feedLines)"
        Write-Host "     latestAgeSec  = $($health.latestAgeSec)"
        $okCount++
        if ($null -ne $health.latestAgeSec -and $health.latestAgeSec -gt 90) {
            $problems += "FEED STALE: latestAgeSec = $($health.latestAgeSec)s"
            Write-Host "     >>> ALERTA: Feed envelhecendo!" -ForegroundColor Red
        }
    } else {
        Write-Host " FALHOU" -ForegroundColor Red
        $problems += "Bridge ok=false"
    }
} catch {
    Write-Host " OFFLINE" -ForegroundColor Red
    $problems += "Bridge offline"
}

# 2. Engine
Write-Host "[2] Engine (porta 8765)..." -NoNewline
try {
    $ui = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
    if ($ui.ok -eq $true) {
        Write-Host " OK" -ForegroundColor Green
        Write-Host "     fixtureId     = $($ui.fixtureId)"
        Write-Host "     source        = $($ui.source)"
        Write-Host "     paper_trade   = $($ui.paper_trade)"
        Write-Host "     jarvis_state  = $($ui.jarvis_state)"
        Write-Host "     capture_stale = $($ui.capture_stale)"
        $okCount++

        if ($ui.jarvis_state -eq "BLOCKED_BY_DATA") {
            $problems += "Engine em BLOCKED_BY_DATA (provável venv/FastAPI ou captura)"
            Write-Host "     >>> CRÍTICO: BLOCKED_BY_DATA" -ForegroundColor Red
        }
        if (-not $ui.fixtureId) {
            $problems += "fixtureId vazio - Engine não engatou na partida"
            Write-Host "     >>> ALERTA: sem fixtureId" -ForegroundColor Yellow
        }
    } else {
        Write-Host " FALHOU" -ForegroundColor Red
        $problems += "Engine ok=false"
    }
} catch {
    Write-Host " OFFLINE ou erro" -ForegroundColor Red
    $problems += "Engine offline ou com erro de import (FastAPI?)"
    Write-Host "     >>> Verifique se o venv tem FastAPI instalado" -ForegroundColor Yellow
}

# 3. Testar se FastAPI importa no venv
Write-Host "[3] Testando FastAPI no venv do Engine..." -NoNewline
$venvPy = "C:\aura\AURA_QUANT_X_12.7.0\engine\venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $check = & $venvPy -c "import fastapi; print(fastapi.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK (v$check)" -ForegroundColor Green
        $okCount++
    } else {
        Write-Host " FALHOU" -ForegroundColor Red
        $problems += "FastAPI NÃO instalado no venv → rode AURA_REPARAR_VENV_ENGINE.ps1"
        Write-Host "     $check" -ForegroundColor Red
    }
} else {
    Write-Host " VENV AUSENTE" -ForegroundColor Red
    $problems += "Pasta engine\venv não existe"
}

# 4. live_latest.json
Write-Host "[4] Arquivo live_latest.json..." -NoNewline
$latestFile = "C:\aura\AURA_QUANT_X_12.7.0\bridge\live_latest.json"
if (Test-Path $latestFile) {
    $info = Get-Item $latestFile
    $age = [math]::Round(((Get-Date) - $info.LastWriteTime).TotalSeconds, 1)
    Write-Host " OK" -ForegroundColor Green
    Write-Host "     Tamanho       = $($info.Length) bytes"
    Write-Host "     Idade         = ${age}s"
    $okCount++
    if ($age -gt 120) {
        $problems += "live_latest.json com mais de 2 minutos de idade"
        Write-Host "     >>> ALERTA: arquivo antigo" -ForegroundColor Yellow
    }
} else {
    Write-Host " AUSENTE" -ForegroundColor Red
    $problems += "live_latest.json não existe"
}

# Resumo
Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RESUMO" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

if ($problems.Count -eq 0) {
    Write-Host ""
    Write-Host "  SISTEMA SAUDÁVEL" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  PROBLEMAS ($($problems.Count)):" -ForegroundColor Red
    foreach ($p in $problems) {
        Write-Host "   • $p" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "  AÇÕES RECOMENDADAS:" -ForegroundColor Yellow
    if ($problems -match "FastAPI|venv") {
        Write-Host "   1. powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1"
        Write-Host "   2. .\AURA_TUDO_EM_UM.bat"
    } else {
        Write-Host "   1. Abra uma partida AO VIVO no SokkerPRO (ponto vermelho)"
        Write-Host "   2. Aguarde 20-30 segundos"
        Write-Host "   3. Rode esta verificação novamente"
    }
    Write-Host ""
}

Write-Host "Checks OK: $okCount" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
