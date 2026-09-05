# AURA motor autonomo - ASCII + UTF-8 BOM (Windows PS 5.1)
param([string]$Root = '')
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Say([string]$Color, [string]$Msg) { Write-Host $Msg -ForegroundColor $Color }
function Ok([string]$Msg)   { Say 'Green'  ("[OK]    " + $Msg) }
function Warn([string]$Msg) { Say 'Yellow' ("[WARN]  " + $Msg) }
function Fail([string]$Msg) { Say 'Red'    ("[FAIL]  " + $Msg) }
function Info([string]$Msg) { Say 'Cyan'   ("[INFO]  " + $Msg) }

if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not (Test-Path (Join-Path $Root 'engine\server.py'))) {
  if (Test-Path 'C:\AURA_V25\engine\server.py') { $Root = 'C:\AURA_V25' }
  elseif (Test-Path 'C:\aura\engine\server.py') { $Root = 'C:\aura' }
}
Set-Location $Root
$LogDir = Join-Path $Root 'logs_supervisor'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Report = Join-Path $LogDir 'MOTOR_AUTONOMO_LATEST.txt'

$env:AURA_ROOT = $Root
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:AURA_EXECUTION_ALLOWED = '0'
$env:AURA_UNLOCK_LIVE = '0'
$env:GLM_ADVISORY_ONLY = 'true'
$env:CORNERAI_BRIDGE_REQUIRE_TOKEN = '0'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = ($Root + ';' + (Join-Path $Root 'hermes_v10') + ';' + (Join-Path $Root 'engine') + ';' + (Join-Path $Root 'bridge'))

Info ('ROOT=' + $Root)

function PyVer([string]$Exe, [string]$Arg) {
  try {
    if ($Arg) { return & $Exe $Arg -c "import sys; print('%d.%d' % sys.version_info[:2])" }
    return & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])"
  } catch { return '' }
}

$py = $null
$pyLauncher = $null
$cands = @(
  (Join-Path $Root 'engine\venv\Scripts\python.exe'),
  'C:\AURA_V25\engine\venv\Scripts\python.exe',
  'C:\aura\engine\venv\Scripts\python.exe'
)
foreach ($c in $cands) {
  if (Test-Path $c) {
    $v = (PyVer $c '').Trim()
    Info ('cand ' + $c + ' ver=' + $v)
    if ($v -eq '3.10' -or $v -eq '3.11') { $py = $c; break }
  }
}
if (-not $py) {
  foreach ($tag in @('-3.11','-3.10')) {
    $v = (PyVer 'py' $tag).Trim()
    if ($v -eq '3.10' -or $v -eq '3.11') { $pyLauncher = 'py'; $py = $tag; break }
  }
}
if (-not $py) {
  Fail 'Python 3.10/3.11 nao encontrado. Nao uses 3.12+ / 3.14 para o Hermes.'
  exit 2
}

if ($pyLauncher) {
  Info ('PY=py ' + $py + ' (3.10/3.11)')
  & py $py -c "import sys; print(sys.version)"
} else {
  Info ('PY=' + $py)
  & $py -c "import sys; print(sys.version)"
}

function Find-OnDisk([string]$relPath) {
  # Only copy an exact relative path from known AURA roots. Never pick a random
  # server.py from Desktop/Downloads (that can overwrite engine with bridge).
  $roots = @($Root, 'C:\AURA_V25', 'C:\aura', 'C:\AURA')
  foreach ($r in $roots) {
    if (-not (Test-Path $r)) { continue }
    $candidate = Join-Path $r $relPath
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  return $null
}

$need = @(
  @{ Key='engine'; Path='engine\server.py'; Name='server.py' },
  @{ Key='bridge'; Path='bridge\server.py'; Name='server.py' },
  @{ Key='matriz'; Path='scripts\aura_serve_matriz.py'; Name='aura_serve_matriz.py' },
  @{ Key='hermes'; Path='hermes_v10\scripts\hermes_v10_chat_api.py'; Name='hermes_v10_chat_api.py' },
  @{ Key='hcore';  Path='hermes_v10\core\hermes_llm_engine.py'; Name='hermes_llm_engine.py' },
  @{ Key='hrun';   Path='hermes_v10\AURA_RUN_HERMES.py'; Name='AURA_RUN_HERMES.py' },
  @{ Key='voice';  Path='bridge\jarvis_voice_server.py'; Name='jarvis_voice_server.py' },
  @{ Key='smoke';  Path='scripts\smoke_test.py'; Name='smoke_test.py' },
  @{ Key='report'; Path='scripts\AURA_RELATORIO_GERAL_COMPLETO.py'; Name='AURA_RELATORIO_GERAL_COMPLETO.py' },
  @{ Key='clean';  Path='AURA_LIMPEZA_E_INSTALACAO_COMPLETA.bat'; Name='AURA_LIMPEZA_E_INSTALACAO_COMPLETA.bat' }
)

$have = @{}
foreach ($n in $need) {
  $dest = Join-Path $Root $n.Path
  if (Test-Path $dest) { $have[$n.Key] = $true; Ok $n.Path; continue }
  $found = Find-OnDisk $n.Path
  if ($found) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item $found $dest -Force
    $have[$n.Key] = $true
    Warn ('curado ' + $n.Path + ' <- ' + $found)
  } else {
    $have[$n.Key] = $false
    Fail ('em falta ' + $n.Path)
  }
}

function Is-Listen([int]$Port) {
  $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  return ($null -ne $c)
}

function Start-Svc {
  param([string]$Name, [string]$Workdir, [string]$ArgLine, [string]$LogName, [int]$Port)
  if (Is-Listen $Port) { Ok ($Name + ' ja LISTEN :' + $Port); return $true }
  if (-not (Test-Path $Workdir)) { Fail ($Name + ' workdir ausente ' + $Workdir); return $false }
  $logFile = Join-Path $LogDir $LogName
  if ($pyLauncher) {
    $exeLine = 'py ' + $py + ' ' + $ArgLine
  } else {
    $exeLine = '"' + $py + '" ' + $ArgLine
  }
  $cmd = 'set AURA_ROOT=' + $Root + '&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& set PYTHONPATH=' + $env:PYTHONPATH + '&& ' + $exeLine + ' >> "' + $logFile + '" 2>&1'
  Info ('start ' + $Name + ' :' + $Port)
  Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Workdir -WindowStyle Minimized -ArgumentList @('/c', $cmd) | Out-Null
  $i = 0
  while ($i -lt 15) {
    Start-Sleep -Seconds 2
    if (Is-Listen $Port) { Ok ($Name + ' LISTEN :' + $Port); return $true }
    $i++
  }
  Warn ($Name + ' nao abriu :' + $Port + ' - tail log')
  if (Test-Path $logFile) { Get-Content $logFile -Tail 30 | ForEach-Object { Write-Host ('    ' + $_) } }
  else { Warn ('sem log ' + $logFile) }
  return $false
}

$okB = $false; $okE = $false; $okM = $false; $okH = $false; $okV = $false
if ($have['bridge']) { $okB = Start-Svc -Name 'Bridge' -Workdir $Root -ArgLine '-u bridge\server.py --host 127.0.0.1 --port 8080' -LogName 'bridge.log' -Port 8080 }
if ($have['engine']) { $okE = Start-Svc -Name 'Engine' -Workdir $Root -ArgLine '-u engine\server.py --host 127.0.0.1 --port 8765' -LogName 'engine.log' -Port 8765 }
if ($have['matriz']) { $okM = Start-Svc -Name 'Matriz' -Workdir $Root -ArgLine '-u scripts\aura_serve_matriz.py' -LogName 'matriz8766.log' -Port 8766 } else { Warn 'Matriz skip' }
if ($have['hermes'] -and $have['hcore'] -and $have['hrun']) {
  $okH = Start-Svc -Name 'Hermes' -Workdir (Join-Path $Root 'hermes_v10') -ArgLine '-u AURA_RUN_HERMES.py' -LogName 'hermes_v10.log' -Port 8777
} else {
  Warn 'Hermes skip - falta scripts ou core\hermes_llm_engine.py (copia a pasta hermes_v10 COMPLETA)'
}
if ($have['voice']) { $okV = Start-Svc -Name 'Voice' -Workdir $Root -ArgLine '-u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy' -LogName 'voice.log' -Port 8099 }

if (Is-Listen 11434) { Ok 'Ollama LISTEN :11434' } else { Warn 'Ollama OFF :11434' }

function Probe([string]$N, [string]$U) {
  try {
    $r = Invoke-WebRequest -Uri $U -UseBasicParsing -TimeoutSec 4
    Ok ($N + ' HTTP ' + $r.StatusCode)
    return $true
  } catch { Fail ($N + ' OFF ' + $U); return $false }
}

Info '===== HEALTH ====='
$hb = Probe 'Bridge' 'http://127.0.0.1:8080/health'
$he = Probe 'Engine' 'http://127.0.0.1:8765/api/health'
$hm = Probe 'Matriz' 'http://127.0.0.1:8766/health'
$hh = Probe 'Hermes' 'http://127.0.0.1:8777/health'
$hv = Probe 'Voice'  'http://127.0.0.1:8099/api/voice/health'

$smokeTxt = 'skip'
if ($have['smoke']) {
  Info '===== SMOKE ====='
  try {
    if ($pyLauncher) { $smokeTxt = & py $py (Join-Path $Root 'scripts\smoke_test.py') 2>&1 | Out-String }
    else { $smokeTxt = & $py (Join-Path $Root 'scripts\smoke_test.py') 2>&1 | Out-String }
    Write-Host $smokeTxt
  } catch { $smokeTxt = [string]$_ }
}

if ($have['report']) {
  Info '===== RELATORIO GERAL ====='
  try {
    if ($pyLauncher) { & py $py (Join-Path $Root 'scripts\AURA_RELATORIO_GERAL_COMPLETO.py') }
    else { & $py (Join-Path $Root 'scripts\AURA_RELATORIO_GERAL_COMPLETO.py') }
  } catch { Warn ([string]$_) }
}

$summary = @(
  ('ROOT=' + $Root),
  ('PY=' + $py),
  ('HERMES_CORE=' + $have['hcore']),
  ('LISTEN B=' + $okB + ' E=' + $okE + ' M=' + $okM + ' H=' + $okH + ' V=' + $okV),
  ('HTTP B=' + $hb + ' E=' + $he + ' M=' + $hm + ' H=' + $hh + ' V=' + $hv),
  'PAPER_TRADE=true EXECUTION_ALLOWED=false'
) -join "`r`n"
[System.IO.File]::WriteAllText($Report, $summary)
Info ('Guardado ' + $Report)

if ($hb -and $he) { Ok 'CORE OK (Bridge+Engine).'; exit 0 }
Fail 'CORE DOWN - Bridge ou Engine falhou.'
exit 2
