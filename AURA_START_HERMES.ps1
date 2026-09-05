#Requires -Version 5.1
# AURA QUANT-X V37.3.48 — Start Hermes Chat :8777 (robusto)
# Preferir: AURA_REPARAR_E_SUBIR_HERMES.ps1 se houver erro de path/syntax
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$Root = $null
foreach ($c in @('C:\aura', 'C:\AURA_V25', (Split-Path -Parent $MyInvocation.MyCommand.Path))) {
  if ((Test-Path (Join-Path $c 'hermes_v10\core\hermes_llm_engine.py')) -or
      (Test-Path (Join-Path $c 'engine\server.py'))) {
    $Root = $c; break
  }
}
if (-not $Root) { Write-Host 'ROOT nao encontrado (C:\aura ou C:\AURA_V25)' -ForegroundColor Red; exit 1 }

$py = $null
foreach ($c in @(
  (Join-Path $Root 'engine\venv\Scripts\python.exe'),
  'C:\AURA_V25\engine\venv\Scripts\python.exe',
  'C:\aura\engine\venv\Scripts\python.exe'
)) {
  if (Test-Path $c) {
    $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($v -match '3\.11') { $py = $c; break }
    if (-not $py -and $v -match '3\.(9|10|11)') { $py = $c }
  }
}
if (-not $py) {
  try { & py -3.11 -c "print(1)" 2>$null; if ($LASTEXITCODE -eq 0) { $py = 'py' } } catch {}
}
if (-not $py) { Write-Host 'Python 3.11 nao encontrado' -ForegroundColor Red; exit 2 }

$LogDir = Join-Path $Root 'logs_supervisor'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'hermes_v10.log'

try {
  Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue
  }
} catch {}

$env:AURA_ROOT = $Root
$env:PYTHONPATH = "$Root;$Root\hermes_v10;$Root\engine;$Root\bridge"
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:PYTHONUTF8 = '1'

$Run = Join-Path $Root 'hermes_v10\AURA_RUN_HERMES.py'
$Chat = Join-Path $Root 'hermes_v10\scripts\hermes_v10_chat_api.py'
$Work = Join-Path $Root 'hermes_v10'

if (Test-Path $Run) {
  $entry = $Run
} elseif (Test-Path $Chat) {
  $entry = $Chat
} else {
  Write-Host "FALTA $Chat — extraia o ZIP completo" -ForegroundColor Red
  exit 3
}

Write-Host "ROOT=$Root  PY=$py  ENTRY=$entry"
Set-Location $Work

if ($py -eq 'py') {
  Start-Process -FilePath 'py.exe' -WorkingDirectory $Work -WindowStyle Minimized `
    -ArgumentList @('-3.11','-u', $entry) `
    -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
} else {
  Start-Process -FilePath $py -WorkingDirectory $Work -WindowStyle Minimized `
    -ArgumentList @('-u', $entry) `
    -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
}

Start-Sleep 8
try {
  $r = Invoke-WebRequest 'http://127.0.0.1:8777/health' -UseBasicParsing -TimeoutSec 4
  Write-Host "Hermes ON — $($r.StatusCode)" -ForegroundColor Green
} catch {
  Write-Host 'Hermes OFF — veja o log:' -ForegroundColor Yellow
  if (Test-Path $Log) { Get-Content $Log -Tail 20 }
  if (Test-Path "$Log.err") { Get-Content "$Log.err" -Tail 15 }
  Write-Host 'Tente: AURA_REPARAR_E_SUBIR_HERMES.ps1' -ForegroundColor Cyan
}
