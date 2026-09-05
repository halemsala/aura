# ============================================================
# AURA QUANT-X - Forçar Sincronização Engine ← Bridge
# Versão: V25T15-CORRECAO
# Tenta fazer o Engine abandonar o cache antigo e puxar
# o fixture atual do CornerAI / Bridge
# ============================================================

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " AURA QUANT-X - FORCE SYNC (Engine ← Bridge)" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Ler o que o Bridge está vendo agora
Write-Host "[1] Lendo CornerAI latest..." -NoNewline
try {
    $latest = (Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 5).latest
    $fid = $latest.view.fixture_id
    $home = $latest.view.home
    $away = $latest.view.away
    Write-Host " OK" -ForegroundColor Green
    Write-Host "     Fixture atual no Bridge: $fid"
    Write-Host "     $home  x  $away  (min $($latest.view.minute))"
} catch {
    Write-Host " FALHOU" -ForegroundColor Red
    Write-Host "     Bridge offline ou sem dados. Aborte." -ForegroundColor Red
    exit 1
}

# 2. Tentar endpoints de force / switch (vários nomes comuns)
Write-Host ""
Write-Host "[2] Tentando forçar o Engine a trocar de fixture..." -ForegroundColor Yellow

$endpoints = @(
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/ui/force_fixture"; Body = @{ fixtureId = $fid } },
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/ui/set_fixture"; Body = @{ fixture_id = $fid } },
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/ui/switch"; Body = @{ fixtureId = $fid } },
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/cache/invalidate"; Body = @{} },
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/ui/clear"; Body = @{} },
    @{ Method = "POST"; Uri = "http://127.0.0.1:8765/api/ui/refresh"; Body = @{} }
)

$success = $false
foreach ($ep in $endpoints) {
    try {
        $bodyJson = $ep.Body | ConvertTo-Json -Compress
        $null = Invoke-RestMethod -Uri $ep.Uri -Method $ep.Method -Body $bodyJson -ContentType "application/json" -TimeoutSec 4 -ErrorAction Stop
        Write-Host "     Sucesso em $($ep.Uri)" -ForegroundColor Green
        $success = $true
    } catch {
        # silencioso - endpoint pode não existir
    }
}

if (-not $success) {
    Write-Host "     Nenhum endpoint de force encontrado (normal em algumas builds)." -ForegroundColor Yellow
    Write-Host "     Use a limpeza forte de cache + restart." -ForegroundColor Yellow
}

# 3. Verificar resultado
Write-Host ""
Write-Host "[3] Verificando estado após tentativa..." -NoNewline
Start-Sleep -Seconds 2
try {
    $ui = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
    Write-Host " OK" -ForegroundColor Green
    Write-Host "     Engine fixtureId agora = $($ui.fixtureId)"
    Write-Host "     source                 = $($ui.source)"

    if ($ui.fixtureId -eq $fid) {
        Write-Host ""
        Write-Host "  SINCRONIZADO COM SUCESSO!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "  Ainda em mismatch. Rode a limpeza forte:" -ForegroundColor Red
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\AURA_CLEAR_CACHE_FORTE.ps1" -ForegroundColor White
        Write-Host "  Depois: .\AURA_TUDO_EM_UM.bat" -ForegroundColor White
    }
} catch {
    Write-Host " Engine offline" -ForegroundColor Red
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
