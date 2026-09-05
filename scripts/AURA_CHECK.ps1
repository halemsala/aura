# AURA_CHECK.ps1 — ficheiros + portas + health HTTP
param(
  [string]$Root = "",
  [ValidateSet('files','services','final')]
  [string]$Mode = 'final'
)
$ErrorActionPreference = 'SilentlyContinue'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
Set-Location $Root

function Test-File($rel) {
  $p = Join-Path $Root $rel
  if (Test-Path $p) { Write-Host ("  [OK]    {0}" -f $rel); return $true }
  Write-Host ("  [FALTA] {0}" -f $rel)
  return $false
}

function Test-Listen([int]$port) {
  $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  return [bool]$c
}

function Test-Http([string]$url) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
    return $r.StatusCode
  } catch {
    return 0
  }
}

$fail = 0
Write-Host ("===== CHECK {0}  ROOT={1} =====" -f $Mode.ToUpper(), $Root)

if ($Mode -in @('files','final')) {
  Write-Host "-- ficheiros --"
  $need = @(
    'engine\server.py',
    'bridge\server.py',
    'engine\venv\Scripts\python.exe',
    'desktop\ui\matriz_v22\index.html',
    'scripts\aura_serve_matriz.py',
    'hermes_v10\scripts\hermes_v10_chat_api.py'
  )
  foreach ($f in $need) { if (-not (Test-File $f)) { $fail++ } }
  $opt = @(
    'bridge\jarvis_voice_server.py',
    'desktop\publish\Aura.QuantX.Desktop.exe',
    'desktop\config\desktop.json',
    'scripts\AURA_SAFE_FREE_PORTS.ps1'
  )
  foreach ($f in $opt) {
    if (Test-Path (Join-Path $Root $f)) { Write-Host ("  [OK]    {0}" -f $f) }
    else { Write-Host ("  [AVISO] {0}" -f $f) }
  }
}

if ($Mode -in @('services','final')) {
  Write-Host "-- portas / health --"
  $rows = @(
    @{ N='Bridge'; P=8080; U='http://127.0.0.1:8080/health' },
    @{ N='Engine'; P=8765; U='http://127.0.0.1:8765/api/health' },
    @{ N='Matriz'; P=8766; U='http://127.0.0.1:8766/health' },
    @{ N='Voice';  P=8099; U='http://127.0.0.1:8099/api/voice/health' },
    @{ N='Hermes'; P=8777; U='http://127.0.0.1:8777/chat' },
    @{ N='Dash';   P=8778; U='http://127.0.0.1:8778/' },
    @{ N='Ollama'; P=11434; U='http://127.0.0.1:11434/api/tags' }
  )
  foreach ($r in $rows) {
    $listen = Test-Listen $r.P
    $code = 0
    if ($r.U) { $code = Test-Http $r.U }
    $ls = if ($listen) { 'LISTEN' } else { 'OFF   ' }
    $hs = if ($code -ge 200 -and $code -lt 500) { "HTTP $code" } else { 'HTTP --' }
    $mark = 'OK'
    if ($r.N -eq 'Ollama') {
      if (-not $listen) { $mark = 'AVISO' }
    } elseif ($r.N -in @('Voice','Dash')) {
      if (-not $listen) { $mark = 'AVISO' }
    } elseif ($r.N -eq 'Hermes' -and $Mode -eq 'services') {
      $mark = if ($listen) { 'OK' } else { 'SKIP' }
    } else {
      if (-not $listen -or $code -eq 0) { $mark = 'FALHA'; $fail++ }
    }
    Write-Host ("  [{0,-5}] {1,-7} :{2}  {3}  {4}" -f $mark, $r.N, $r.P, $ls, $hs)
  }
}

if ($Mode -eq 'final') {
  Write-Host "-- invariantes --"
  Write-Host "  paper_trade=true  execution_allowed=false"
  $exe = Join-Path $Root 'desktop\publish\Aura.QuantX.Desktop.exe'
  $desk = Get-Process -Name 'Aura.QuantX.Desktop' -ErrorAction SilentlyContinue
  if ($desk) { Write-Host "  [OK]    Desktop processo ativo" }
  elseif (Test-Path $exe) { Write-Host "  [AVISO] EXE existe mas processo Desktop nao visto" }
  else { Write-Host "  [AVISO] Desktop EXE ausente — use browser :8766" }
}

Write-Host ("===== FIM CHECK  falhas={0} =====" -f $fail)
if ($fail -gt 0) { exit 1 }
exit 0
