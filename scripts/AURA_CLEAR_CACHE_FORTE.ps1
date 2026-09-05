# ============================================================
# AURA QUANT-X - Limpeza Agressiva de Cache + Estado
# Versão: V25T15-CORRECAO
# Resolve: engine_cache preso em fixture errado + dados stale
# ============================================================

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path "$Root\AURA_TUDO_EM_UM.bat")) {
    $Root = "C:\aura\AURA_QUANT_X_12.7.0"
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " AURA QUANT-X - LIMPEZA FORTE DE CACHE" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "ROOT = $Root"
Write-Host ""

# 1. Matar processos e liberar portas
Write-Host "[1/6] Matando processos AURA e liberando portas..." -ForegroundColor Yellow
$ports = @(8080, 8765, 8099)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess -gt 0) {
            try {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
                Write-Host "      Kill PID $($c.OwningProcess) on :$port"
            } catch {}
        }
    }
}
Start-Sleep -Seconds 2
Write-Host "      OK" -ForegroundColor Green

# 2. Limpar caches locais do usuário
Write-Host "[2/6] Limpando caches do usuário (LOCALAPPDATA / TEMP)..." -ForegroundColor Yellow
$paths = @(
    "$env:LOCALAPPDATA\Aura*",
    "$env:LOCALAPPDATA\AURA*",
    "$env:TEMP\Aura*",
    "$env:TEMP\AURA*",
    "$env:TEMP\aura*"
)
foreach ($p in $paths) {
    Get-ChildItem $p -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "      OK" -ForegroundColor Green

# 3. Limpar pastas de cache do próprio pacote
Write-Host "[3/6] Limpando cache interno do pacote..." -ForegroundColor Yellow
$cacheDirs = @(
    "$Root\engine\cache",
    "$Root\engine\state",
    "$Root\engine\tmp",
    "$Root\bridge\cache",
    "$Root\bridge\state",
    "$Root\bridge\tmp",
    "$Root\desktop\cache",
    "$Root\data\cache",
    "$Root\data\state"
)
foreach ($dir in $cacheDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "      Limpo: $dir"
    }
}
Write-Host "      OK" -ForegroundColor Green

# 4. Tentar limpar estado via API (se ainda estiver de pé)
Write-Host "[4/6] Tentando limpar estado via API (se disponível)..." -ForegroundColor Yellow
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ui/clear" -Method Post -TimeoutSec 3 -ErrorAction SilentlyContinue
    Write-Host "      Chamou /api/ui/clear" -ForegroundColor Green
} catch {
    Write-Host "      Engine offline (normal após kill) - ok"
}
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/cache/clear" -Method Post -TimeoutSec 3 -ErrorAction SilentlyContinue
    Write-Host "      Chamou /api/cache/clear" -ForegroundColor Green
} catch {
    Write-Host "      Bridge offline (normal) - ok"
}

# 5. Remover possíveis arquivos de estado soltos
Write-Host "[5/6] Removendo arquivos de estado soltos..." -ForegroundColor Yellow
$stateFiles = @(
    "$Root\engine\*.json",
    "$Root\bridge\*.json",
    "$Root\*.state",
    "$Root\engine\working_memory*",
    "$Root\bridge\working_memory*"
)
foreach ($f in $stateFiles) {
    Get-ChildItem $f -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}
Write-Host "      OK" -ForegroundColor Green

# 6. Resumo
Write-Host ""
Write-Host "[6/6] Limpeza concluída." -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Agora execute:  .\AURA_TUDO_EM_UM.bat" -ForegroundColor White
Write-Host " Depois rode o script de verificação." -ForegroundColor White
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
