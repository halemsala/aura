# Arranque + health + smoke + relatorio (PowerShell nativo)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $Root 'engine\server.py'))) { $Root = 'C:\AURA_V25' }
Set-Location $Root
$py = Join-Path $Root 'engine\venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'py' }

$env:AURA_ROOT = $Root
$env:PYTHONPATH = "$Root;$Root\hermes_v10;$Root\engine;$Root\bridge"
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:AURA_EXECUTION_ALLOWED = '0'
$env:GLM_ADVISORY_ONLY = 'true'
$env:CORNERAI_BRIDGE_REQUIRE_TOKEN = '0'
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs_supervisor') | Out-Null

Write-Host "ROOT = $Root"
Write-Host "PY   = $py"
& $py -c "import sys; print(sys.version)"

function Is-Listen([int]$port) {
  $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

if (-not (Is-Listen 8080) -and (Test-Path "$Root\bridge\server.py")) {
  Start-Process $py -WorkingDirectory $Root -WindowStyle Minimized -ArgumentList @('-u','bridge\server.py','--host','127.0.0.1','--port','8080')
  Write-Host 'start Bridge'
}
if (-not (Is-Listen 8765) -and (Test-Path "$Root\engine\server.py")) {
  Start-Process $py -WorkingDirectory $Root -WindowStyle Minimized -ArgumentList @('-u','engine\server.py','--host','127.0.0.1','--port','8765')
  Write-Host 'start Engine'
}
if (-not (Is-Listen 8766) -and (Test-Path "$Root\scripts\aura_serve_matriz.py")) {
  Start-Process $py -WorkingDirectory $Root -WindowStyle Minimized -ArgumentList @('-u','scripts\aura_serve_matriz.py')
  Write-Host 'start Matriz'
}
if (-not (Is-Listen 8777) -and (Test-Path "$Root\hermes_v10\scripts\hermes_v10_chat_api.py")) {
  Start-Process $py -WorkingDirectory (Join-Path $Root 'hermes_v10') -WindowStyle Minimized -ArgumentList @('-u','scripts\hermes_v10_chat_api.py')
  Write-Host 'start Hermes'
} elseif (-not (Test-Path "$Root\hermes_v10\scripts\hermes_v10_chat_api.py")) {
  Write-Host 'FALTA hermes_v10 — ZIP extraido no sitio errado' -ForegroundColor Red
}

Start-Sleep -Seconds 12

function Test-Url($n,$u){
  try {
    $r = Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 4
    Write-Host ("{0,-8} {1}" -f $n, $r.StatusCode) -ForegroundColor Green
  } catch { Write-Host ("{0,-8} OFF" -f $n) -ForegroundColor Yellow }
}
Write-Host "`n===== HEALTH ====="
Test-Url Bridge 'http://127.0.0.1:8080/health'
Test-Url Engine 'http://127.0.0.1:8765/api/health'
Test-Url Matriz 'http://127.0.0.1:8766/health'
Test-Url Hermes 'http://127.0.0.1:8777/health'
Test-Url Voice  'http://127.0.0.1:8099/api/voice/health'

Write-Host "`n===== PORTAS ====="
foreach ($p in 8080,8765,8766,8777,8099,11434) {
  if (Is-Listen $p) { Write-Host "LISTEN $p" } else { Write-Host "OFF    $p" }
}

Write-Host "`n===== SMOKE ====="
if (Test-Path "$Root\scripts\smoke_test.py") { & $py "$Root\scripts\smoke_test.py" }

Write-Host "`n===== RELATORIO ====="
if (Test-Path "$Root\scripts\AURA_RELATORIO_GERAL_COMPLETO.py") { & $py "$Root\scripts\AURA_RELATORIO_GERAL_COMPLETO.py" }

Write-Host "`nFIM  logs_supervisor\RELATORIO_GERAL_LATEST.txt"
Write-Host 'paper_trade=true execution_allowed=false'
