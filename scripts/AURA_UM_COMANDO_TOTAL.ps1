# AURA QUANT-X — UM COMANDO TOTAL (Windows PowerShell 5.1 compatible)
# Para tudo, libera portas, garante deps, sobe Bridge+Engine, publica Desktop se preciso, health, feedback IA
param(
  [switch]$SkipDesktop,
  [switch]$SkipPublish
)

$ErrorActionPreference = "Continue"
$Root = $null
if (Test-Path ".\engine\server.py") {
  $Root = (Resolve-Path ".").Path
} else {
  $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location $Root
$env:PYTHONPATH = "$Root;$Root\engine;$Root\bridge"
$env:PYTHONUNBUFFERED = "1"
$env:PAPER_TRADE = "true"
$env:EXECUTION_ALLOWED = "false"
$env:GLM_ADVISORY_ONLY = "true"
$env:CORNERAI_BRIDGE_REQUIRE_TOKEN = "0"
$env:AURA_PAPER_ONLY = "1"

$logDir = Join-Path $Root "logs_instalacao"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$masterLog = Join-Path $logDir ("UM_COMANDO_" + $ts + ".txt")

function W {
  param([string]$m, [string]$c = "White")
  Write-Host $m -ForegroundColor $c
  Add-Content -Path $masterLog -Value $m -Encoding UTF8
}
function Ok([string]$m) { W ("[OK]  " + $m) "Green" }
function Fail([string]$m) { W ("[ERR] " + $m) "Red" }
function Info([string]$m) { W ("[..]  " + $m) "Cyan" }
function Warn([string]$m) { W ("[!!]  " + $m) "Yellow" }

W "============================================================"
W " AURA UM COMANDO TOTAL  V26"
W (" Inicio: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
W (" Root: " + $Root)
W (" Log: " + $masterLog)
W "============================================================"

# ---- 1) Kill + free ports ----
Info "1/8 Parar processos e liberar portas"
foreach ($name in @("Aura.QuantX.Desktop", "python", "pythonw")) {
  Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$freePs1 = Join-Path $Root "scripts\AURA_FREE_PORTS.ps1"
if (Test-Path $freePs1) {
  try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $freePs1 2>&1 | Out-Null
  } catch {}
}
foreach ($port in @(8080, 8765, 8099)) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      if ($c.OwningProcess) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {}
}
Start-Sleep -Seconds 1
Ok "Processos/portas limpos"

# ---- 2) Venv ----
Info "2/8 Venv Python"
$venvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Info "Criando venv..."
  $pyCmd = $null
  if (Get-Command python -ErrorAction SilentlyContinue) { $pyCmd = "python" }
  elseif (Get-Command py -ErrorAction SilentlyContinue) { $pyCmd = "py" }
  if (-not $pyCmd) {
    Fail "Python nao encontrado no PATH"
    W "Instale Python 3.10+ (marque Add to PATH) e rode de novo"
    exit 1
  }
  $venvDir = Join-Path $Root "engine\venv"
  & $pyCmd -m venv $venvDir
}
if (-not (Test-Path $venvPy)) {
  Fail "venv falhou"
  exit 1
}
Ok ("venv: " + $venvPy)

# ---- 3) Deps ----
Info "3/8 Dependencias (fastapi uvicorn pydantic httpx ...)"
& $venvPy -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
$req = Join-Path $Root "engine\requirements.txt"
$pipLog = Join-Path $logDir ("pip_requirements_" + $ts + ".log")
if (Test-Path $req) {
  Info "pip install -r engine\requirements.txt (pode demorar)..."
  & $venvPy -m pip install -r $req 2>&1 | Tee-Object -FilePath $pipLog | Out-Null
} else {
  & $venvPy -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8" "requests" "httpx" "pyyaml" "psutil" "aiohttp" "websockets" 2>&1 | Out-Null
}
$importTest = & $venvPy -c "import fastapi,uvicorn,pydantic; print('DEPS_OK')" 2>&1
if (("$importTest") -match "DEPS_OK") {
  Ok "Deps Python OK"
} else {
  Warn ("Import deps: " + $importTest)
}

# ---- 4) Preflight ----
Info "4/8 Preflight bridge file"
$bridgePy = Join-Path $Root "bridge\server.py"
$enginePy = Join-Path $Root "engine\server.py"
if (Test-Path $bridgePy) { Ok "bridge\server.py presente" } else { Fail "Falta bridge\server.py"; exit 1 }
if (Test-Path $enginePy) { Ok "engine\server.py presente" } else { Fail "Falta engine\server.py"; exit 1 }

# ---- 5) Start Bridge via helper bat (PS 5.1 safe) ----
Info "5/8 Subindo Bridge :8080"
$bridgeLog = Join-Path $Root "bridge\runtime_bridge.log"
if (Test-Path $bridgeLog) { Remove-Item $bridgeLog -Force -ErrorAction SilentlyContinue }

$bridgeHelper = Join-Path $logDir "start_bridge_helper.bat"
@(
  "@echo off",
  "cd /d `"$Root`"",
  "set PYTHONPATH=$Root;$Root\engine;$Root\bridge",
  "set PYTHONUNBUFFERED=1",
  "set PAPER_TRADE=true",
  "set CORNERAI_BRIDGE_REQUIRE_TOKEN=0",
  "`"$venvPy`" -u `"$Root\bridge\server.py`" --host 127.0.0.1 --port 8080 >> `"$bridgeLog`" 2>&1"
) | Set-Content -Path $bridgeHelper -Encoding ASCII
Start-Process -FilePath $bridgeHelper -WindowStyle Minimized
Start-Sleep -Seconds 3

# ---- 6) Start Engine ----
Info "6/8 Subindo Engine :8765"
$engineLog = Join-Path $Root "engine\runtime_engine.log"
if (Test-Path $engineLog) { Remove-Item $engineLog -Force -ErrorAction SilentlyContinue }

$engineHelper = Join-Path $logDir "start_engine_helper.bat"
@(
  "@echo off",
  "cd /d `"$Root`"",
  "set PYTHONPATH=$Root;$Root\engine;$Root\bridge",
  "set PYTHONUNBUFFERED=1",
  "set PAPER_TRADE=true",
  "set EXECUTION_ALLOWED=false",
  "set GLM_ADVISORY_ONLY=true",
  "`"$venvPy`" -u `"$Root\engine\server.py`" --host 127.0.0.1 --port 8765 >> `"$engineLog`" 2>&1"
) | Set-Content -Path $engineHelper -Encoding ASCII
Start-Process -FilePath $engineHelper -WindowStyle Minimized

# ---- Wait health ----
Info "Aguardando health (ate 50s)..."
function Test-Url([string]$url) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
  } catch {
    return $false
  }
}

$bridgeOk = $false
$engineOk = $false
for ($i = 1; $i -le 25; $i++) {
  if (-not $bridgeOk) { $bridgeOk = Test-Url "http://127.0.0.1:8080/health" }
  if (-not $engineOk) { $engineOk = Test-Url "http://127.0.0.1:8765/api/health" }
  if ($bridgeOk -and $engineOk) { break }
  Start-Sleep -Seconds 2
}

if ($bridgeOk) {
  Ok "Bridge :8080 UP"
} else {
  Fail "Bridge NAO subiu"
  if (Test-Path $bridgeLog) {
    W "--- ultimas linhas bridge\runtime_bridge.log ---" "Yellow"
    Get-Content $bridgeLog -Tail 40 -ErrorAction SilentlyContinue | ForEach-Object { W $_ "Yellow" }
  } else {
    Warn "Log bridge ainda nao existe (processo morreu na hora)"
  }
}

if ($engineOk) {
  Ok "Engine :8765 UP"
} else {
  Fail "Engine NAO subiu"
  if (Test-Path $engineLog) {
    W "--- ultimas linhas engine\runtime_engine.log ---" "Yellow"
    Get-Content $engineLog -Tail 40 -ErrorAction SilentlyContinue | ForEach-Object { W $_ "Yellow" }
  } else {
    Warn "Log engine ainda nao existe (processo morreu na hora)"
  }
}

# Fallback emergency bridge
if (-not $bridgeOk) {
  Info "Tentando emergency_bridge.py na :8080..."
  $em = Join-Path $Root "bridge\emergency_bridge.py"
  if (Test-Path $em) {
    $emHelper = Join-Path $logDir "start_emergency_bridge.bat"
    @(
      "@echo off",
      "cd /d `"$Root`"",
      "set PYTHONPATH=$Root;$Root\engine;$Root\bridge",
      "`"$venvPy`" -u `"$em`""
    ) | Set-Content -Path $emHelper -Encoding ASCII
    Start-Process -FilePath $emHelper -WindowStyle Minimized
    Start-Sleep -Seconds 4
    $bridgeOk = Test-Url "http://127.0.0.1:8080/health"
    if ($bridgeOk) { Ok "Emergency Bridge UP" } else { Fail "Emergency Bridge tambem falhou" }
  }
}

# ---- 7) Desktop ----
Info "7/8 Desktop EXE"
$exeCandidates = @(
  (Join-Path $Root "desktop\bin\Aura.QuantX.Desktop.exe"),
  (Join-Path $Root "desktop\publish\Aura.QuantX.Desktop.exe"),
  (Join-Path $Root "desktop\publish\Aura.Desktop.exe")
)
$exe = $null
foreach ($c in $exeCandidates) {
  if (Test-Path $c) { $exe = $c; break }
}

if ((-not $exe) -and (-not $SkipPublish) -and (-not $SkipDesktop)) {
  $dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
  if ($dotnet) {
    Info "dotnet encontrado - publicando Desktop (pode demorar)..."
    $pub = Join-Path $Root "desktop\packaging\PUBLISH_WINDOWS.ps1"
    $comp = Join-Path $Root "AURA_COMPILAR_DESKTOP.bat"
    $pubLog = Join-Path $logDir ("publish_desktop_" + $ts + ".log")
    try {
      if (Test-Path $pub) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $pub 2>&1 | Tee-Object -FilePath $pubLog
      } elseif (Test-Path $comp) {
        & cmd.exe /c $comp 2>&1 | Tee-Object -FilePath $pubLog
      }
    } catch {
      Warn ("Publish falhou: " + $_.Exception.Message)
    }
    foreach ($c in $exeCandidates) {
      if (Test-Path $c) { $exe = $c; break }
    }
    if (-not $exe) {
      $found = Get-ChildItem -Path (Join-Path $Root "desktop") -Filter "Aura*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "Desktop|QuantX" } | Select-Object -First 1
      if ($found) { $exe = $found.FullName }
    }
  } else {
    Warn "dotnet SDK nao encontrado - nao e possivel compilar Desktop nesta maquina"
    Warn "Instale .NET 8 SDK se precisar do Desktop EXE"
  }
}

if ($exe) {
  Ok ("Desktop EXE: " + $exe)
  if (-not $SkipDesktop) {
    Info "Abrindo Desktop..."
    Start-Process -FilePath $exe
  }
} else {
  Warn "Desktop EXE ausente - use Chrome + SokkerPRO + pasta extensao"
}

# ---- 8) Voice optional ----
Info "8/8 Voice (opcional)"
$voiceOk = Test-Url "http://127.0.0.1:8099/api/voice/health"
if ($voiceOk) {
  Ok "Voice ja UP"
} else {
  $voiceBat = Join-Path $Root "AURA_RUN_VOICE_SEGURO.bat"
  if (Test-Path $voiceBat) {
    $vHelper = Join-Path $logDir "start_voice_helper.bat"
    @(
      "@echo off",
      "cd /d `"$Root`"",
      "call `"$voiceBat`""
    ) | Set-Content -Path $vHelper -Encoding ASCII
    Start-Process -FilePath $vHelper -WindowStyle Minimized
    Start-Sleep -Seconds 2
  }
}

# ---- Feedback IA ----
$statusStr = "CRITICAL"
if ($bridgeOk -and $engineOk) { $statusStr = "CORE_UP" }
elseif ($bridgeOk -or $engineOk) { $statusStr = "PARTIAL" }

$feedback = @{
  version     = "26.0-UM-COMANDO"
  timestamp   = (Get-Date).ToUniversalTime().ToString("o")
  bridge_ok   = $bridgeOk
  engine_ok   = $engineOk
  desktop_exe = $exe
  status      = $statusStr
  message_for_ia = ("Um-comando: bridge=" + $bridgeOk + " engine=" + $engineOk + " desktop=" + [bool]$exe)
  log         = $masterLog
}
$fbPath = Join-Path $Root "engine\data\system_health_feedback.json"
$dir = Split-Path $fbPath -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$feedback | ConvertTo-Json -Depth 6 | Set-Content -Path $fbPath -Encoding UTF8

W ""
W "============================================================"
W " RESUMO"
if ($bridgeOk) { W " Bridge:  UP    http://127.0.0.1:8080/health" "Green" } else { W " Bridge:  DOWN  http://127.0.0.1:8080/health" "Red" }
if ($engineOk) { W " Engine:  UP    http://127.0.0.1:8765/api/health" "Green" } else { W " Engine:  DOWN  http://127.0.0.1:8765/api/health" "Red" }
if ($exe) { W (" Desktop: " + $exe) "Green" } else { W " Desktop: AUSENTE" "Yellow" }
W (" Log:     " + $masterLog)
W "============================================================"
if ($bridgeOk -and $engineOk) {
  Ok "CORE PRONTO. Abra SokkerPRO AO VIVO (pane direita ou Chrome+extensao)."
  Ok "Depois: .\RODAR_TESTE_AUTOMATICO.bat"
} else {
  Fail "CORE incompleto. Veja logs acima e em logs_instalacao"
  W "Diagnostico rapido:"
  W "  .\AURA_SUBIR_BRIDGE_VISIVEL.bat"
  W "  .\AURA_SUBIR_ENGINE_VISIVEL.bat"
}

if (-not ($bridgeOk -and $engineOk)) { exit 1 } else { exit 0 }
