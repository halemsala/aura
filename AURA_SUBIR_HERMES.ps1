# Sobe so o Hermes Chat :8777 (PowerShell nativo) — V37.3.48
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $Root 'hermes_v10\core\hermes_llm_engine.py'))) {
  if (Test-Path 'C:\aura\hermes_v10\core\hermes_llm_engine.py') { $Root = 'C:\aura' }
  elseif (Test-Path 'C:\AURA_V25\hermes_v10\core\hermes_llm_engine.py') { $Root = 'C:\AURA_V25' }
}
Set-Location $Root
$py = $null
foreach ($c in @(
  (Join-Path $Root 'engine\venv\Scripts\python.exe'),
  'C:\AURA_V25\engine\venv\Scripts\python.exe',
  'C:\aura\engine\venv\Scripts\python.exe'
)) {
  if (Test-Path $c) {
    $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($v -match '3\.11') { $py = $c; break }
    if (-not $py) { $py = $c }
  }
}
if (-not $py) { $py = 'py'; $use311 = $true } else { $use311 = $false }

$env:AURA_ROOT = $Root
$env:PYTHONPATH = "$Root;$Root\hermes_v10;$Root\engine;$Root\bridge"
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:PYTHONUTF8 = '1'

$Run = Join-Path $Root 'hermes_v10\AURA_RUN_HERMES.py'
$Chat = Join-Path $Root 'hermes_v10\scripts\hermes_v10_chat_api.py'
if (-not (Test-Path $Run) -and -not (Test-Path $Chat)) {
  Write-Host "FALTA hermes_v10 — extraia o ZIP por cima de $Root" -ForegroundColor Red
  exit 1
}
Write-Host "ROOT=$Root PY=$py"
Set-Location (Join-Path $Root 'hermes_v10')
if ($use311) {
  & py -3.11 -u $(if (Test-Path $Run) { $Run } else { 'scripts\hermes_v10_chat_api.py' })
} else {
  & $py -u $(if (Test-Path $Run) { $Run } else { 'scripts\hermes_v10_chat_api.py' })
}
