#Requires -Version 5.1
# AURA QUANT-X HERMES V37.3.38 — instalacao via PowerShell (sem BAT quebrado)
# paper_trade=true | execution_allowed=false
$ErrorActionPreference = 'Continue'
$Root = 'C:\aura'
$LogDir = Join-Path $Root 'logs_supervisor'
$Log = Join-Path $LogDir 'instalar_agora.log'

function Write-Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  AVISO  $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  ERRO  $msg" -ForegroundColor Red }

# --- 0. Localizar / copiar pacote ---
Write-Step '0/11' 'Localizar pacote'
$here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$candidates = @(
  $here,
  (Join-Path $here 'AURA_COMPLETE_V37.3.38'),
  (Join-Path $here 'AURA_QUANT_X_HERMES_INTEGRADO'),
  $Root
)
$Src = $null
foreach ($c in $candidates) {
  if (Test-Path (Join-Path $c 'engine\server.py')) { $Src = (Resolve-Path $c).Path; break }
}
if (-not $Src) {
  Write-Err 'engine\server.py nao encontrado. Extraia o ZIP e rode este script de dentro da pasta.'
  exit 1
}
Write-Ok "Fonte: $Src"

if (-not (Test-Path $Root)) { New-Item -ItemType Directory -Path $Root | Out-Null }
if ($Src -ne $Root) {
  Write-Host "  A copiar para $Root (preserva venv)..."
  $null = robocopy $Src $Root /E /R:2 /W:1 /NFL /NDL /NJH /NJS /XD engine\venv venv node_modules .git __pycache__ /XF *.pyc
  if ($LASTEXITCODE -ge 8) { Write-Err "robocopy falhou codigo $LASTEXITCODE"; exit 1 }
}
Set-Location $Root
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
"==== INSTALAR_AGORA $(Get-Date) Root=$Root ====" | Out-File -FilePath $Log -Append -Encoding utf8

# --- 1. Auditoria leve ---
Write-Step '1/11' 'Auditoria ficheiros'
@('engine\server.py','bridge\server.py','desktop\ui\matriz_v22\index.html','scripts\aura_serve_matriz.py') | ForEach-Object {
  if (Test-Path (Join-Path $Root $_)) { Write-Ok $_ } else { Write-Warn "falta $_" }
}

# --- 2. Preparacao / portas ---
Write-Step '2/11' 'Libertar portas AURA'
$ports = 8080,8765,8766,8777,8778,8099,8790
foreach ($p in $ports) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      Write-Host "  Porta $p PID $($c.OwningProcess) — a terminar"
      Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
  } catch {}
}
Start-Sleep -Seconds 2
Write-Ok 'portas livres'

# --- 3-4. Python / venv ---
Write-Step '3-4/11' 'Python + venv + deps'
$py = $null
foreach ($cmd in @('py -3.11','py -3.10','python')) {
  try {
    $null = Invoke-Expression "$cmd -c `"import sys; assert sys.version_info>=(3,10)`""
    if ($LASTEXITCODE -eq 0 -or $?) { $py = $cmd; break }
  } catch {}
}
# fallback test
if (-not $py) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $ver = & py -3.11 -c "import sys; print(sys.version)" 2>$null
    if ($ver) { $py = 'py -3.11' }
  }
}
if (-not $py) {
  if (Get-Command python -ErrorAction SilentlyContinue) { $py = 'python' }
}
if (-not $py) {
  Write-Err 'Python 3.10/3.11 nao encontrado. Instale e marque Add to PATH.'
  exit 2
}
Write-Ok "Host: $py"

$venvDir = Join-Path $Root 'engine\venv'
$vpy = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
  Write-Host '  A criar venv...'
  Invoke-Expression "$py -m venv `"$venvDir`"" | Out-File -FilePath $Log -Append
  if (-not (Test-Path $vpy)) { Write-Err 'falha ao criar venv'; exit 2 }
}
Write-Host '  A instalar deps base...'
& $vpy -m pip install -U pip wheel setuptools 2>&1 | Out-File -FilePath $Log -Append
& $vpy -m pip install --disable-pip-version-check fastapi 'uvicorn[standard]' pydantic httpx requests psutil websockets python-dotenv pyyaml aiofiles numpy 2>&1 | Out-File -FilePath $Log -Append
$req = Join-Path $Root 'requirements.txt'
if (Test-Path $req) {
  & $vpy -m pip install --disable-pip-version-check -r $req 2>&1 | Out-File -FilePath $Log -Append
}
Write-Ok 'venv pronto'

# --- 5. Env comum ---
$env:AURA_ROOT = $Root
$env:PYTHONPATH = "$Root;$Root\engine;$Root\bridge"
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:AURA_EXECUTION_ALLOWED = '0'
$env:AURA_UNLOCK_LIVE = '0'
$env:GLM_ADVISORY_ONLY = 'true'
$env:AURA_PAPER_ONLY = '1'

function Start-AuraService {
  param([string]$Name, [string]$WorkDir, [string]$Arguments, [string]$LogFile)
  $logPath = Join-Path $LogDir $LogFile
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $vpy
  $psi.Arguments = $Arguments
  $psi.WorkingDirectory = $WorkDir
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.Environment['AURA_ROOT'] = $Root
  $psi.Environment['PYTHONPATH'] = "$Root;$Root\engine;$Root\bridge;$WorkDir"
  $psi.Environment['PYTHONUTF8'] = '1'
  $psi.Environment['PYTHONUNBUFFERED'] = '1'
  $psi.Environment['PAPER_TRADE'] = 'true'
  $psi.Environment['EXECUTION_ALLOWED'] = 'false'
  $psi.Environment['AURA_EXECUTION_ALLOWED'] = '0'
  $psi.Environment['AURA_UNLOCK_LIVE'] = '0'
  $psi.Environment['GLM_ADVISORY_ONLY'] = 'true'
  try {
    $p = [System.Diagnostics.Process]::Start($psi)
    # async log drain minimal
    Start-Job -ScriptBlock {
      param($proc, $log)
      while (-not $proc.HasExited) {
        $line = $proc.StandardOutput.ReadLine()
        if ($null -ne $line) { Add-Content -Path $log -Value $line }
      }
    } -ArgumentList $p, $logPath | Out-Null
    Write-Ok "$Name PID=$($p.Id) log=$LogFile"
    return $p
  } catch {
    Write-Err "$Name falhou: $_"
    return $null
  }
}

# --- 6. Servicos ---
Write-Step '6/11' 'Subir servicos (sem janela)'
Start-AuraService -Name 'Bridge:8080' -WorkDir $Root -Arguments '-u bridge\server.py --host 127.0.0.1 --port 8080' -LogFile 'bridge.log' | Out-Null
Start-AuraService -Name 'Engine:8765' -WorkDir $Root -Arguments '-u engine\server.py --host 127.0.0.1 --port 8765' -LogFile 'engine.log' | Out-Null
if (Test-Path (Join-Path $Root 'scripts\aura_serve_matriz.py')) {
  Start-AuraService -Name 'Matriz:8766' -WorkDir $Root -Arguments '-u scripts\aura_serve_matriz.py' -LogFile 'matriz8766.log' | Out-Null
}
if (Test-Path (Join-Path $Root 'scripts\aura_tools_control_api.py')) {
  Start-AuraService -Name 'Control:8790' -WorkDir $Root -Arguments '-u scripts\aura_tools_control_api.py' -LogFile 'tools_control.log' | Out-Null
}
if (Test-Path (Join-Path $Root 'bridge\jarvis_voice_server.py')) {
  Start-AuraService -Name 'Voice:8099' -WorkDir $Root -Arguments '-u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy' -LogFile 'voice.log' | Out-Null
}

Write-Host '  A aguardar 10s...'
Start-Sleep -Seconds 10

# --- 7. Check portas ---
Write-Step '7/11' 'Check portas'
foreach ($p in @(8080,8765,8766,8790)) {
  $up = $false
  try { $up = [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) } catch {}
  if ($up) { Write-Ok "LISTEN $p" } else { Write-Warn "OFF $p" }
}

# --- 8. Hermes ---
Write-Step '8/11' 'Hermes Chat'
$hermesDir = $null
if (Test-Path (Join-Path $Root 'hermes_v10\scripts\hermes_v10_chat_api.py')) {
  $hermesDir = Join-Path $Root 'hermes_v10'
} elseif (Test-Path (Join-Path $Root 'scripts\hermes_v10_chat_api.py')) {
  $hermesDir = $Root
}
if ($hermesDir) {
  & $vpy -m pip install --disable-pip-version-check -q fastapi 'uvicorn[standard]' pydantic httpx structlog prometheus-client python-dotenv pyyaml aiofiles websockets numpy psutil 2>&1 | Out-File -FilePath $Log -Append
  Start-AuraService -Name 'Hermes:8777' -WorkDir $hermesDir -Arguments '-u scripts\hermes_v10_chat_api.py' -LogFile 'hermes_v10.log' | Out-Null
  Start-Sleep -Seconds 4
} else {
  Write-Warn 'Hermes API nao encontrada'
}

# --- 9. Check Hermes ---
Write-Step '9/11' 'Check Hermes'
$h = $false
try { $h = [bool](Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue) } catch {}
if ($h) { Write-Ok 'LISTEN 8777' } else { Write-Warn 'OFF 8777' }

# --- 10. Desktop / browser ---
Write-Step '10/11' 'Abrir UI'
$exe = Join-Path $Root 'desktop\publish\Aura.QuantX.Desktop.exe'
if (Test-Path $exe) {
  Start-Process $exe
  Write-Ok 'Desktop EXE'
} else {
  Start-Process 'http://127.0.0.1:8766/index.html'
  Write-Ok 'Matriz browser'
}
Start-Process 'http://127.0.0.1:8766/tools-hub.html'
Start-Process 'http://127.0.0.1:8777/chat'

# --- 11. Metricas ---
Write-Step '11/11' 'Metricas'
if (Test-Path (Join-Path $Root 'scripts\aura_ops_status_write.py')) {
  & $vpy -u (Join-Path $Root 'scripts\aura_ops_status_write.py') 2>&1 | Out-File -FilePath $Log -Append
}
if (Test-Path (Join-Path $Root 'scripts\aura_system_metrics.py')) {
  & $vpy -u (Join-Path $Root 'scripts\aura_system_metrics.py') 2>&1 | Out-File (Join-Path $LogDir 'system_metrics_latest.json')
}
Write-Ok 'fim'

Write-Host "`n================================================================"
Write-Host "  INSTALACAO CONCLUIDA  (paper_trade only)"
Write-Host "  Log: $Log"
Write-Host "  Bridge   http://127.0.0.1:8080/health"
Write-Host "  Engine   http://127.0.0.1:8765/api/health"
Write-Host "  Matriz   http://127.0.0.1:8766/index.html"
Write-Host "  Tools    http://127.0.0.1:8766/tools-hub.html"
Write-Host "  Hermes   http://127.0.0.1:8777/chat"
Write-Host "  Control  http://127.0.0.1:8790/health"
Write-Host "================================================================`n"
