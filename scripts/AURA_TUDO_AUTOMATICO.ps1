# AURA - UM COMANDO: venv + Bridge + Engine + Desktop + Monitor  V26.2-FIX
# Correções:
#  - Desktop: prioriza AURA_ABRIR_DESKTOP_SEGURO / EXE direto (nao usa launcher bloqueado)
#  - Espera health real antes de reportar OK
#  - Detecta processo Desktop corretamente

param([string]$Root = "")

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function W($m,$c="White"){ Write-Host $m -ForegroundColor $c }

if (-not $Root) {
  if (Test-Path ".\engine\server.py") { $Root = (Resolve-Path ".").Path }
  elseif (Test-Path (Join-Path $PSScriptRoot "..\engine\server.py")) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
  else { $Root = (Get-Location).Path }
}
Set-Location $Root
W "============================================================" "Green"
W " AURA QUANT-X - TUDO AUTOMATICO (1 comando) V26.2-FIX" "Green"
W " Root: $Root" "Green"
W "============================================================" "Green"

# 1) Garantir venv via instalacao limpa
$installPs1 = Join-Path $Root "scripts\AURA_INSTALACAO_LIMPA_V26_FULL.ps1"
if (Test-Path $installPs1) {
  W "[..] Instalacao/venv/Bridge/Engine..." "Cyan"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $installPs1
} else {
  W "[!!] Falta scripts\AURA_INSTALACAO_LIMPA_V26_FULL.ps1 - tentando subir servicos direto" "Yellow"
}

# 2) Health helpers
function Up($url) {
  try { Invoke-RestMethod -Uri $url -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

$venvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
$env:PYTHONPATH = "$Root;$Root\engine;$Root\bridge"
$env:PYTHONUNBUFFERED = "1"
$env:AURA_PAPER_ONLY = "1"
$env:PAPER_TRADE = "true"
$env:CORNERAI_BRIDGE_REQUIRE_TOKEN = "0"
$env:AURA_EXECUTION_ALLOWED = "0"
$env:GLM_ADVISORY_ONLY = "1"
$env:EXECUTION_ALLOWED = "false"

if (-not (Test-Path $venvPy)) {
  W "[ERR] venv Python ausente: $venvPy" "Red"
  W "Rode AURA_CRIAR_VENV.bat ou AURA_INSTALACAO_LIMPA_E_INICIAR.bat" "Yellow"
}

# Liberar portas se ocupadas por processo morto
try {
  $freePs1 = Join-Path $Root "scripts\AURA_FREE_PORTS.ps1"
  if (Test-Path $freePs1) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $freePs1 2>$null
  }
} catch {}

if (-not (Up "http://127.0.0.1:8080/health")) {
  W "[..] Subindo Bridge :8080 ..." "Cyan"
  if (Test-Path $venvPy) {
    $cmd = "`"$venvPy`" -u bridge\server.py --host 127.0.0.1 --port 8080"
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c",$cmd) -WorkingDirectory $Root -WindowStyle Minimized
    Start-Sleep -Seconds 6
  }
}

if (-not (Up "http://127.0.0.1:8765/api/health")) {
  W "[..] Subindo Engine :8765 ..." "Cyan"
  if (Test-Path $venvPy) {
    $cmd = "`"$venvPy`" -u engine\server.py --host 127.0.0.1 --port 8765"
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c",$cmd) -WorkingDirectory $Root -WindowStyle Minimized
    Start-Sleep -Seconds 10
  }
}

# Retry Engine uma vez (startup lento com MCGrid)
if (-not (Up "http://127.0.0.1:8765/api/health")) {
  W "[..] Engine ainda down - nova tentativa..." "Yellow"
  if (Test-Path $venvPy) {
    $cmd = "`"$venvPy`" -u engine\server.py --host 127.0.0.1 --port 8765"
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c",$cmd) -WorkingDirectory $Root -WindowStyle Minimized
    Start-Sleep -Seconds 12
  }
}

$b = Up "http://127.0.0.1:8080/health"
$e = Up "http://127.0.0.1:8765/api/health"
if ($b) { W "[OK] Bridge :8080" "Green" } else { W "[ERR] Bridge DOWN - rode AURA_SUBIR_BRIDGE_VISIVEL.bat" "Red" }
if ($e) { W "[OK] Engine :8765" "Green" } else { W "[ERR] Engine DOWN - rode AURA_SUBIR_ENGINE_VISIVEL.bat" "Red" }

# 3) Desktop - ordem correta (seguro / EXE / legado)
W "[..] Abrindo Desktop..." "Cyan"
$opened = $false

# Preferencia 1: launcher seguro
$safeBat = Join-Path $Root "AURA_ABRIR_DESKTOP_SEGURO.bat"
if (Test-Path $safeBat) {
  Start-Process -FilePath $safeBat -WorkingDirectory $Root
  $opened = $true
  W "[OK] Desktop via AURA_ABRIR_DESKTOP_SEGURO.bat" "Green"
}

# Preferencia 2: ABRIR_DESKTOP.bat corrigido (V26.2)
if (-not $opened) {
  $deskBat = Join-Path $Root "ABRIR_DESKTOP.bat"
  if (Test-Path $deskBat) {
    # Verificar se nao e o legado bloqueado
    $content = Get-Content $deskBat -Raw -ErrorAction SilentlyContinue
    if ($content -and ($content -notmatch "LAUNCHER LEGADO DESATIVADO") -and ($content -notmatch "BLOCKED")) {
      Start-Process -FilePath $deskBat -WorkingDirectory $Root
      $opened = $true
      W "[OK] Desktop via ABRIR_DESKTOP.bat" "Green"
    }
  }
}

# Preferencia 3: EXE direto
if (-not $opened) {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\portable\desktop\publish\Aura.QuantX.Desktop.exe"),
    (Join-Path $Root "desktop\publish\Aura.QuantX.Desktop.exe"),
    (Join-Path $Root "desktop\bin\Aura.QuantX.Desktop.exe")
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) {
      Start-Process -FilePath $c
      $opened = $true
      W "[OK] Desktop EXE: $c" "Green"
      break
    }
  }
}

# Preferencia 4: busca recursiva
if (-not $opened) {
  $exe = Get-ChildItem -Path (Join-Path $Root "desktop") -Recurse -Filter "Aura.QuantX.Desktop.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($exe) {
    Start-Process -FilePath $exe.FullName
    $opened = $true
    W "[OK] Desktop EXE (busca): $($exe.FullName)" "Green"
  }
}

if (-not $opened) {
  W "[!!] Desktop nao encontrado. Compile com AURA_COMPILAR_DESKTOP.bat ou PUBLISH_WINDOWS.ps1" "Yellow"
}

# 4) Monitor continuo IA
$mon = Join-Path $Root "RODAR_MONITOR_CONTINUO_IA.bat"
if (Test-Path $mon) {
  Start-Process -FilePath $mon -WorkingDirectory $Root
  W "[OK] Monitor continuo IA iniciado" "Green"
} else {
  $monPs1 = Join-Path $Root "scripts\AURA_MONITOR_FEEDBACK_IA.ps1"
  if (Test-Path $monPs1) {
    Start-Process powershell -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",$monPs1,"-IntervalSec","10") -WorkingDirectory $Root
    W "[OK] Monitor PS1 iniciado" "Green"
  }
}

W ""
W "============================================================" "Green"
W " PRONTO. Pane DIREITA do Desktop = SokkerPRO AO VIVO" "Green"
W " Teste opcional: .\RODAR_TESTE_AUTOMATICO.bat" "Green"
W " Health: http://127.0.0.1:8080/health  |  http://127.0.0.1:8765/api/health" "Green"
W "============================================================" "Green"
