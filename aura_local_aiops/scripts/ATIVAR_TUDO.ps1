# ============================================================
# AURA Local AIOps — Comando Único de Ativação (Windows)
# Integra: Neo4j (Docker) + Orchestrator (Harness local) +
#          Callback + Agente Ollama
# ============================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path "$Root\docker-compose.yml")) {
    $Root = Get-Location
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AURA Local AIOps — Ativacao Unica" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Pasta: $Root"
Write-Host ""

# --- 1. Docker / Neo4j ---
Write-Host "[1/5] Verificando Docker..." -ForegroundColor Yellow
try {
    docker version | Out-Null
} catch {
    Write-Host "ERRO: Docker Desktop nao esta rodando." -ForegroundColor Red
    Write-Host "Abra o Docker Desktop e espere 'Engine running', depois rode este script de novo."
    exit 1
}

Write-Host "[1/5] Subindo Neo4j (docker compose)..." -ForegroundColor Yellow
Set-Location $Root
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tentando docker-compose..." -ForegroundColor Yellow
    docker-compose up -d
}

Write-Host "Aguardando Neo4j ficar healthy (max 60s)..." -ForegroundColor Yellow
$ok = $false
for ($i = 1; $i -le 12; $i++) {
    Start-Sleep -Seconds 5
    $status = docker inspect --format='{{.State.Health.Status}}' neo4j-local 2>$null
    if ($status -eq "healthy") { $ok = $true; break }
    Write-Host "  ... tentativa $i (status=$status)"
}
if (-not $ok) {
    Write-Host "AVISO: Neo4j ainda nao reportou healthy. Continuando mesmo assim." -ForegroundColor Yellow
} else {
    Write-Host "  Neo4j OK (http://localhost:7474)" -ForegroundColor Green
}

# --- 2. Dependencias Python ---
Write-Host "[2/5] Verificando Python..." -ForegroundColor Yellow
python --version
pip install -q neo4j requests 2>$null

# --- 3. Callback ---
Write-Host "[3/5] Iniciando Callback (porta 8090)..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "$Root\agent\callback_server.py" -WindowStyle Minimized
Start-Sleep -Seconds 1

# --- 4. Orchestrator ---
Write-Host "[4/5] Iniciando Orchestrator / Harness local (porta 8095)..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "$Root\orchestrator\local_orchestrator.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# --- 5. Health checks ---
Write-Host "[5/5] Health checks..." -ForegroundColor Yellow
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8095/health" -TimeoutSec 3
    Write-Host "  Orchestrator: OK" -ForegroundColor Green
} catch {
    Write-Host "  Orchestrator: ainda subindo..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  SISTEMA ATIVO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Neo4j Browser : http://localhost:7474"
Write-Host "  Usuario/Senha : neo4j / aura_local_pass"
Write-Host "  Orchestrator  : http://127.0.0.1:8095/trigger"
Write-Host "  Callback      : http://127.0.0.1:8090/api/agent/callback"
Write-Host ""
Write-Host "  Para falar com o Agente (Ollama):" -ForegroundColor Cyan
Write-Host "    python agent\ollama_agent.py"
Write-Host ""
Write-Host "  Teste rapido do Orchestrator:" -ForegroundColor Cyan
Write-Host '    python agent\local_tool.py "RETURN 1 AS ok"'
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
