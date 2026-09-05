# AURA QUANT-X 12.7.0 V26-FULL - Instalacao limpa completa
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\AURA_INSTALACAO_LIMPA_V26_FULL.ps1

param(
  [switch]$ForceRecreateVenv,
  [switch]$StartServices,
  [switch]$SkipPip,
  [string]$Root = ""
)

if (-not $PSBoundParameters.ContainsKey("ForceRecreateVenv")) { $ForceRecreateVenv = $false }  # V26.3-FIX: idempotente por padrao
if (-not $PSBoundParameters.ContainsKey("StartServices")) { $StartServices = $true }
if (-not $PSBoundParameters.ContainsKey("SkipPip")) { $SkipPip = $false }

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-Step([string]$msg) { Write-Host "[..] $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "[OK]  $msg" -ForegroundColor Green }
function Write-ErrMsg([string]$msg)  { Write-Host "[ERR] $msg" -ForegroundColor Red }
function Write-WarnMsg([string]$msg) { Write-Host "[!!]  $msg" -ForegroundColor Yellow }

if (-not $Root) {
  if (Test-Path ".\engine") {
    $Root = (Resolve-Path ".").Path
  } elseif (Test-Path (Join-Path $PSScriptRoot "..\engine")) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
  } else {
    $Root = (Get-Location).Path
  }
}
Set-Location $Root

Write-Host "============================================================" -ForegroundColor Green
Write-Host " AURA QUANT-X 12.7.0 V26-FULL - INSTALACAO LIMPA" -ForegroundColor Green
Write-Host " Root: $Root" -ForegroundColor Green
Write-Host "============================================================"

Write-Step "Verificando estrutura..."
$missing = $false
foreach ($n in @("engine", "bridge", "requirements.txt")) {
  $p = Join-Path $Root $n
  if (-not (Test-Path $p)) {
    Write-ErrMsg "Falta $n - extraia o ZIP completo para esta pasta."
    $missing = $true
  }
}
if ($missing) { exit 1 }
Write-Ok "Estrutura base presente"

Write-Step "Localizando Python 3.10+..."
$py = $null
$candidates = New-Object System.Collections.Generic.List[string]

$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd -and $cmd.Source) { [void]$candidates.Add($cmd.Source) }

try {
  $pyLauncher = & py -3 -c "import sys; print(sys.executable)" 2>$null
  if ($pyLauncher) { [void]$candidates.Add($pyLauncher.ToString().Trim()) }
} catch {}

foreach ($c in @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
  "$env:ProgramFiles\Python312\python.exe",
  "$env:ProgramFiles\Python311\python.exe",
  "$env:ProgramFiles\Python310\python.exe"
)) {
  if ($c -and (Test-Path $c)) { [void]$candidates.Add($c) }
}

foreach ($c in $candidates) {
  if (-not $c) { continue }
  try {
    $ver = & $c -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))" 2>$null
    if ($ver -match '^3\.(1[0-9]|[2-9][0-9])') {
      $py = $c
      break
    }
  } catch {}
}

if (-not $py) {
  Write-ErrMsg "Python 3.10+ nao encontrado. Instale de python.org e marque Add to PATH."
  exit 1
}
$pyVer = & $py --version 2>&1
Write-Ok "Python: $py ($pyVer)"

$venvDir = Join-Path $Root "engine\venv"
$venvPy  = Join-Path $venvDir "Scripts\python.exe"
$venvCfg = Join-Path $venvDir "pyvenv.cfg"
$venvBroken = $false

if (Test-Path $venvPy) {
  if (-not (Test-Path $venvCfg)) {
    Write-WarnMsg "venv sem pyvenv.cfg - corrompido"
    $venvBroken = $true
  } else {
    try {
      $null = & $venvPy -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -ne 0) { $venvBroken = $true }
    } catch {
      $venvBroken = $true
    }
  }
} else {
  $venvBroken = $true
}

if ($ForceRecreateVenv -or $venvBroken) {
  Write-Step "Recriando engine\venv ..."
  if (Test-Path $venvDir) {
    try {
      Remove-Item -Recurse -Force $venvDir -ErrorAction Stop
    } catch {
      Write-WarnMsg "Nao consegui apagar venv antigo. Tentando de novo..."
      Start-Sleep -Seconds 2
      Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
    }
  }
  & $py -m venv $venvDir
  if (-not (Test-Path $venvCfg)) {
    Write-ErrMsg "Falha ao criar venv (pyvenv.cfg ausente)."
    exit 1
  }
  if (-not (Test-Path $venvPy)) {
    Write-ErrMsg "Falha ao criar venv (python.exe ausente)."
    exit 1
  }
  Write-Ok "venv criado: $venvPy"
} else {
  Write-Ok "venv ja funcional: $venvPy"
}

# V26.3-FIX: hash de requirements para evitar reinstall desnecessario
$reqHashFile = Join-Path $venvDir ".req_hash"
$req = Join-Path $Root "requirements.txt"
$needPip = -not $SkipPip
if ($needPip -and (Test-Path $req) -and (Test-Path $reqHashFile) -and -not $ForceRecreateVenv -and -not $venvBroken) {
  try {
    $cur = (Get-FileHash -Path $req -Algorithm SHA256).Hash
    $oldH = (Get-Content $reqHashFile -Raw).Trim()
    if ($cur -eq $oldH) {
      Write-Ok "requirements.txt inalterado (hash match) - checando imports criticos..."
      $needPip = $false
    }
  } catch {}
}
# V26.4-FIX: nunca pular pip se faltarem pacotes criticos (pydantic etc.)
$critical = @("pydantic", "fastapi", "uvicorn", "httpx", "numpy")
$missing = @()
foreach ($mod in $critical) {
  & $venvPy -c "import $mod" 2>$null
  if ($LASTEXITCODE -ne 0) { $missing += $mod }
}
if ($missing.Count -gt 0) {
  Write-WarnMsg ("Pacotes criticos ausentes: " + ($missing -join ", ") + " - forcando pip install")
  $needPip = $true
}

if ($needPip) {
  Write-Step "pip install (pode demorar)..."
  & $venvPy -m pip install --upgrade pip setuptools wheel
  if (Test-Path $req) {
    & $venvPy -m pip install -r $req
    if ($LASTEXITCODE -ne 0) {
      Write-WarnMsg "pip retornou codigo $LASTEXITCODE - verifique erros acima"
    } else {
      Write-Ok "requirements.txt instalado"
      try {
        $cur = (Get-FileHash -Path $req -Algorithm SHA256).Hash
        Set-Content -Path $reqHashFile -Value $cur -Encoding ASCII
      } catch {}
    }
  } else {
    Write-WarnMsg "requirements.txt nao encontrado"
  }
  & $venvPy -m pip install "python-multipart>=0.0.9" "pynvml>=11.5.0"
  # V26.4-FIX: garante pydantic mesmo se requirements falhou parcialmente
  & $venvPy -m pip install "pydantic>=2.8,<3" "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1"
  & $venvPy -c "import pydantic, fastapi; print('CRITICAL_IMPORTS_OK', pydantic.__version__)"
  if ($LASTEXITCODE -ne 0) { Write-ErrMsg "Imports criticos falharam apos pip"; exit 1 }
}

$configDir = Join-Path $Root "config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$envFile = Join-Path $configDir "AURA_RUNTIME.env"
if (-not (Test-Path $envFile)) {
  @(
    "AURA_PAPER_TRADE=1",
    "AURA_EXECUTION_ALLOWED=0",
    "AURA_UNLOCK_LIVE=0",
    "AURA_E_ENABLE_SKILL_EXECUTION=1",
    "AURA_HERMES_PRIMARY=1",
    "AURA_GLM_ENABLED=0"
  ) | Set-Content -Encoding ASCII $envFile
  Write-Ok "config\AURA_RUNTIME.env criado (paper)"
}

Write-Step "Liberando portas 8080/8765/8099..."
foreach ($port in @(8080, 8765, 8099)) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "  matou PID $($c.OwningProcess) na porta $port"
      }
    }
  } catch {}
}
Start-Sleep -Seconds 2

$logDir = Join-Path $Root "logs_supervisor"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:PYTHONPATH = "$Root;$Root\engine;$Root\bridge"
$env:PYTHONUNBUFFERED = "1"
$env:AURA_PAPER_ONLY = "1"
$env:PAPER_TRADE = "true"
$env:CORNERAI_BRIDGE_REQUIRE_TOKEN = "0"

if ($StartServices) {
  Write-Step "Subindo Bridge :8080 ..."
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $bridgeOut = Join-Path $logDir ("bridge_install_" + $stamp + ".out.log")
  $bridgeErr = Join-Path $logDir ("bridge_install_" + $stamp + ".err.log")
  $bridgeCmd = "`"$venvPy`" -u bridge\server.py --host 127.0.0.1 --port 8080"
  Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $bridgeCmd) -WorkingDirectory $Root -WindowStyle Minimized -RedirectStandardOutput $bridgeOut -RedirectStandardError $bridgeErr

  Write-Step "Subindo Engine :8765 ..."
  $engineOut = Join-Path $logDir ("engine_install_" + $stamp + ".out.log")
  $engineErr = Join-Path $logDir ("engine_install_" + $stamp + ".err.log")
  # Mesmo comando do AURA_SUBIR_ENGINE_VISIVEL.bat
  $engineCmd = "`"$venvPy`" -u engine\server.py --host 127.0.0.1 --port 8765"
  Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $engineCmd) -WorkingDirectory $Root -WindowStyle Minimized -RedirectStandardOutput $engineOut -RedirectStandardError $engineErr

  if (Test-Path $engineErr) {
    Start-Sleep -Seconds 2
    $errTail = Get-Content $engineErr -Tail 30 -ErrorAction SilentlyContinue
    if ($errTail) {
      Write-Host "--- engine err log (tail) ---" -ForegroundColor Yellow
      $errTail | ForEach-Object { Write-Host $_ -ForegroundColor DarkYellow }
      Write-Host "--- fim err log ---" -ForegroundColor Yellow
    }
  }
}

# V26.3-FIX: polling ativo em vez de Start-Sleep fixo
function Test-Url([string]$url) {
  try {
    Invoke-RestMethod -Uri $url -TimeoutSec 3 -ErrorAction Stop | Out-Null
    return $true
  } catch {
    return $false
  }
}
function Wait-Url([string]$url, [int]$TimeoutSec = 60, [string]$Label = "service") {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    if (Test-Url $url) { $ok = $true; break }
    Start-Sleep -Seconds 2
  }
  return $ok
}

Write-Step "Checando health (polling ate 60s)..."
$bridgeOk = Wait-Url "http://127.0.0.1:8080/health" 40 "Bridge"
$engineOk = Wait-Url "http://127.0.0.1:8765/api/health" 60 "Engine"

if ($bridgeOk) { Write-Ok "Bridge :8080 UP" } else { Write-ErrMsg "Bridge :8080 DOWN - rode .\AURA_SUBIR_BRIDGE_VISIVEL.bat" }
if ($engineOk) { Write-Ok "Engine :8765 UP" } else { Write-ErrMsg "Engine :8765 DOWN - rode .\AURA_SUBIR_ENGINE_VISIVEL.bat" }

$dataDir = Join-Path $Root "engine\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$status = @{
  build = "V26.3-FULL-FIXED"
  installed_at = (Get-Date).ToString("o")
  venv_py = $venvPy
  pyvenv_cfg = (Test-Path $venvCfg)
  bridge_up = $bridgeOk
  engine_up = $engineOk
  paper_trade = $true
  hermes_primary = $true
  glm_enabled = $false
}
$status | ConvertTo-Json | Set-Content -Encoding ASCII (Join-Path $dataDir "install_status.json")

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
if ($bridgeOk -and $engineOk) {
  Write-Host " INSTALACAO OK - Bridge + Engine no ar" -ForegroundColor Green
  Write-Host " Proximo:" -ForegroundColor Green
  Write-Host "   1. Desktop: pane DIREITA = SokkerPRO AO VIVO" -ForegroundColor Green
  Write-Host "   2. .\RODAR_TESTE_AUTOMATICO.bat" -ForegroundColor Green
  Write-Host "   3. (opcional) .\RODAR_MONITOR_CONTINUO_IA.bat" -ForegroundColor Green
  exit 0
} else {
  Write-Host " INSTALACAO PARCIAL - suba manualmente o que falhou" -ForegroundColor Yellow
  Write-Host "   .\AURA_SUBIR_BRIDGE_VISIVEL.bat" -ForegroundColor Yellow
  Write-Host "   .\AURA_SUBIR_ENGINE_VISIVEL.bat" -ForegroundColor Yellow
  exit 2
}
