# ============================================================
# AURA QUANT-X - PIPELINE AUTOMATICO TOTAL (V25T15)
# Um comando: para -> repara o essencial -> sobe -> espera health
#            -> corre E2E captura + diagnostico inteligente
#            -> gera relatorio unico
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_PIPELINE_TOTAL.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_PIPELINE_TOTAL.ps1 -DeepAI
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_PIPELINE_TOTAL.ps1 -SkipStart
# ============================================================
param(
    [switch]$DeepAI,       # chama analysis + IA local no diag inteligente
    [switch]$SkipStart,    # nao mata/sobe servicos (so testa)
    [switch]$SkipDesktop,  # nao abre Desktop
    [int]$WaitSec = 75
)

$ErrorActionPreference = "Continue"
$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
Set-Location $Root
$LogDir = Join-Path $Root "logs_instalacao"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Master = Join-Path $LogDir "pipeline_auto_$Stamp.txt"
$lines = New-Object System.Collections.Generic.List[string]

function L([string]$m, [string]$c = "White") {
    $lines.Add($m)
    Write-Host $m -ForegroundColor $c
}
function Run-Ps1([string]$rel, [string]$extraArgs = "") {
    $p = Join-Path $Root $rel
    if (-not (Test-Path $p)) { L "  [SKIP] ausente: $rel" "Yellow"; return $null }
    L "  >> $rel $extraArgs" "Cyan"
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$p`" $extraArgs"
    $out = & powershell.exe $arg.Split(' ') 2>&1 | Out-String
    return $out
}

L "############################################################" "Cyan"
L "#  AURA AUTO PIPELINE TOTAL                               #" "Cyan"
L ("#  {0}  ROOT={1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Root) "Cyan"
L ("#  DeepAI={0} SkipStart={1} SkipDesktop={2}" -f $DeepAI, $SkipStart, $SkipDesktop) "Cyan"
L "############################################################" "Cyan"

# ---- 0 Ficheiros criticos ----
L "`n==== 0. FICHEIROS CRITICOS ====" "Cyan"
$need = @(
    "engine\server.py",
    "engine\working_memory.py",
    "desktop\capture\aura-capture.js",
    "scripts\AURA_E2E_CAPTURA_MATRIZ.ps1",
    "scripts\AURA_DIAG_INTELIGENTE_E2E.py",
    "AURA_TUDO_EM_UM.bat"
)
$missing = @()
foreach ($f in $need) {
    if (Test-Path (Join-Path $Root $f)) { L "  [OK] $f" "Green" }
    else { L "  [FAIL] $f" "Red"; $missing += $f }
}
if ($missing.Count -gt 0) {
    L "Faltam ficheiros do ZIP CORRIGIDO. Extraia o ZIP por cima e rode de novo." "Red"
    $lines | Set-Content $Master -Encoding UTF8
    exit 1
}

# Sync capture JS para bin/publish se necessario
$capSrc = Join-Path $Root "desktop\capture\aura-capture.js"
foreach ($dst in @(
    (Join-Path $Root "desktop\capture\aura-capture.js"),
    (Join-Path $Root "desktop\publish\capture\aura-capture.js")
)) {
    $dir = Split-Path $dst
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    try {
        Copy-Item $capSrc $dst -Force
        L "  [OK] sync capture -> $dst" "Green"
    } catch { L "  [WARN] sync $dst : $_" "Yellow" }
}

# ---- 1 Parar / subir ----
if (-not $SkipStart) {
    L "`n==== 1. PARAR PROCESSOS ANTIGOS ====" "Cyan"
    foreach ($im in @("Aura.QuantX.Desktop.exe", "python.exe", "pythonw.exe")) {
        & taskkill /F /IM $im 2>$null | Out-Null
    }
    Start-Sleep -Seconds 2
    L "  [OK] taskkill enviado" "Green"

    L "`n==== 2. SUBIR SISTEMA (AURA_TUDO_EM_UM) ====" "Cyan"
    $bat = Join-Path $Root "AURA_TUDO_EM_UM.bat"
    # Correr de forma nao interactiva: o bat tem pause no fim — usamos start services via scripts
    $venvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        L "  Venv ausente - a reparar..." "Yellow"
        $rep = Join-Path $Root "scripts\AURA_REPARAR_VENV_ENGINE.ps1"
        if (Test-Path $rep) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $rep 2>&1 | Out-Null
        }
    }
    if (Test-Path $venvPy) { L "  [OK] venv python" "Green" } else { L "  [FAIL] venv" "Red" }

    # Liberar portas se script existir
    $free = Join-Path $Root "scripts\AURA_FREE_PORTS_MELHORADO.ps1"
    if (Test-Path $free) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $free 2>&1 | Out-Null
        L "  [OK] free ports" "Green"
    }

    # Subir Bridge
    L "  A iniciar Bridge..." "Gray"
    $bridgePy = $null
    foreach ($c in @(
        (Join-Path $Root "engine\venv\Scripts\python.exe"),
        (Join-Path $Root "bridge\venv\Scripts\python.exe"),
        "python"
    )) {
        if ($c -eq "python" -or (Test-Path $c)) { $bridgePy = $c; break }
    }
    $env:PYTHONPATH = "$Root;$Root\engine;$Root\bridge"
    $bridgeScript = Join-Path $Root "bridge\server.py"
    if (Test-Path $bridgeScript) {
        Start-Process -FilePath $bridgePy -ArgumentList @("-u", $bridgeScript) -WorkingDirectory $Root -WindowStyle Minimized
        L "  [OK] Bridge process start" "Green"
    }

    # Subir Engine
    L "  A iniciar Engine..." "Gray"
    $engineScript = Join-Path $Root "engine\server.py"
    if (Test-Path $engineScript) {
        Start-Process -FilePath $venvPy -ArgumentList @("-u", $engineScript, "--host", "127.0.0.1", "--port", "8765") -WorkingDirectory $Root -WindowStyle Minimized
        L "  [OK] Engine process start" "Green"
    }

    # Desktop
    if (-not $SkipDesktop) {
        $exe = Join-Path $Root "desktop\publish\Aura.QuantX.Desktop.exe"
        if (-not (Test-Path $exe)) { $exe = Join-Path $Root "desktop\publish\Aura.QuantX.Desktop.exe" }
        if (Test-Path $exe) {
            Start-Process $exe
            L "  [OK] Desktop aberto: $exe" "Green"
        } else {
            L "  [WARN] Desktop EXE ausente - compile com AURA_TUDO_EM_UM.bat" "Yellow"
        }
    }

    L "`n==== 3. ESPERAR HEALTH (ate ${WaitSec}s) ====" "Cyan"
    $deadline = (Get-Date).AddSeconds($WaitSec)
    $bOk = $false; $eOk = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $h = Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 2
            $bOk = $true
        } catch { $bOk = $false }
        try {
            $h = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 2
            $eOk = $true
        } catch { $eOk = $false }
        if ($bOk -and $eOk) { break }
        Start-Sleep -Seconds 3
    }
    if ($bOk) { L "  [OK] Bridge health" "Green" } else { L "  [FAIL] Bridge sem health" "Red" }
    if ($eOk) { L "  [OK] Engine health" "Green" } else { L "  [FAIL] Engine sem health" "Red" }
} else {
    L "`n==== 1-3. SKIP START (so testes) ====" "Yellow"
}

# ---- 4 extras opcionais (faster-whisper) ----
L "`n==== 4. EXTRAS OPCIONAIS ====" "Cyan"
$venvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $chk = & $venvPy -c "import faster_whisper; print('ok')" 2>$null
    if ($chk -match "ok") {
        L "  [OK] faster_whisper ja instalado" "Green"
    } else {
        L "  [..] a instalar faster-whisper (pode demorar)..." "Yellow"
        & $venvPy -m pip install faster-whisper -q 2>&1 | Out-Null
        L "  [OK] pip faster-whisper terminou" "Green"
    }
}

# ---- 5 E2E captura ----
L "`n==== 5. E2E CAPTURA + MATRIZ ====" "Cyan"
$e2e = Join-Path $Root "scripts\AURA_E2E_CAPTURA_MATRIZ.ps1"
$e2eOut = ""
if (Test-Path $e2e) {
    $e2eOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $e2e 2>&1 | Out-String
    $e2eOut -split "`n" | ForEach-Object { L $_ $(if ($_ -match "\[FAIL\]") { "Red" } elseif ($_ -match "\[OK\]") { "Green" } elseif ($_ -match "\[WARN\]") { "Yellow" } else { "Gray" }) }
} else {
    L "  [FAIL] E2E script ausente" "Red"
}

# ---- 6 Diagnostico inteligente ----
L "`n==== 6. DIAGNOSTICO INTELIGENTE ====" "Cyan"
$pyDiag = Join-Path $Root "scripts\AURA_DIAG_INTELIGENTE_E2E.py"
$diagOut = ""
if ((Test-Path $pyDiag) -and (Test-Path $venvPy)) {
    $dargs = @($pyDiag)
    if ($DeepAI) { $dargs += "--deep" }
    $diagOut = & $venvPy @dargs 2>&1 | Out-String
    $diagOut -split "`n" | ForEach-Object { L $_ $(if ($_ -match "\[FAIL\]") { "Red" } elseif ($_ -match "\[OK\]") { "Green" } elseif ($_ -match "\[AI\]") { "Cyan" } elseif ($_ -match "\[WARN\]") { "Yellow" } else { "Gray" }) }
} else {
    L "  [WARN] diag inteligente indisponivel" "Yellow"
}

# ---- 7 Snapshot final APIs ----
L "`n==== 7. SNAPSHOT FINAL ====" "Cyan"
try {
    $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
    L ("  ui/state: ok={0} fixture={1} home={2} away={3} minute={4} jarvis={5}" -f $ui.ok, $ui.fixtureId, $ui.home, $ui.away, $ui.minute, $ui.jarvis_state) "White"
} catch { L "  ui/state: $($_.Exception.Message)" "Red" }
try {
    $bh = Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 4
    L ("  bridge: feedLines={0} latestAgeSec={1}" -f $bh.feedLines, $bh.latestAgeSec) "White"
} catch { L "  bridge health fail" "Red" }

L "`n==== 8. O QUE FALTA (AUTOMATICO NAO FAZ) ====" "Yellow"
L "  - Login SokkerPRO na pane DIREITA do Desktop" "Yellow"
L "  - Abrir partida AO VIVO (ponto vermelho)" "Yellow"
L "  - Clicar Mesa live + Iniciar" "Yellow"
L "  - Extensao Chrome (skill v3 + charts) para ~100 parametros" "Yellow"
L "  Depois: .\AURA_AUTO_TOTAL.bat -SkipStart -DeepAI" "Yellow"

L "`n############################################################" "Cyan"
L "#  FIM PIPELINE - relatorio: $Master" "Cyan"
L "############################################################" "Cyan"

$lines | Set-Content $Master -Encoding UTF8
# exit code: 0 se bridge+engine ok
try {
    Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 2 | Out-Null
    Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 2 | Out-Null
    exit 0
} catch { exit 2 }
