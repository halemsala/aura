# ============================================================
# AURA QUANT-X - AUTO DIAGNOSTICO TOTAL + RELATORIO
# Versao: V25T15-AUTO
# Um unico comando: testa tudo, tenta reparos seguros, gera relatorio
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_DIAGNOSTICO_TOTAL.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_DIAGNOSTICO_TOTAL.ps1 -Repair
# ============================================================
param(
    [switch]$Repair,          # tenta reparos seguros (venv, live_latest, portas)
    [switch]$StartEngine,     # tenta subir Engine se offline
    [switch]$Quiet            # menos cor no console
)

$ErrorActionPreference = "Continue"
$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
$VenvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
$EnginePy = Join-Path $Root "engine\server.py"
$BridgePy = Join-Path $Root "bridge\server.py"
$LatestPath = Join-Path $Root "bridge\live_latest.json"
$LogDir = Join-Path $Root "logs_instalacao"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ReportPath = Join-Path $LogDir "auto_diagnostico_$Stamp.txt"
$JsonReportPath = Join-Path $LogDir "auto_diagnostico_$Stamp.json"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$script:lines = New-Object System.Collections.Generic.List[string]
$script:checks = @{}
$script:problems = New-Object System.Collections.Generic.List[string]
$script:actions = New-Object System.Collections.Generic.List[string]
$script:okCount = 0
$script:failCount = 0

function L($msg, $color = "White") {
    $script:lines.Add($msg)
    if (-not $Quiet) { Write-Host $msg -ForegroundColor $color }
}

function Pass($name, $detail = "") {
    $script:checks[$name] = @{ ok = $true; detail = $detail }
    $script:okCount++
    L ("  [OK]   {0} {1}" -f $name, $detail) "Green"
}

function Fail($name, $detail = "", $action = "") {
    $script:checks[$name] = @{ ok = $false; detail = $detail }
    $script:failCount++
    $script:problems.Add("$name : $detail")
    if ($action) { $script:actions.Add($action) }
    L ("  [FAIL] {0} {1}" -f $name, $detail) "Red"
}

function Warn($name, $detail = "") {
    $script:checks[$name] = @{ ok = $null; detail = $detail }
    L ("  [WARN] {0} {1}" -f $name, $detail) "Yellow"
}

function Section($t) {
    L ""
    L ("==== {0} ====" -f $t) "Cyan"
}

# ---------- BANNER ----------
L ""
L "############################################################" "Cyan"
L "#  AURA QUANT-X - AUTO DIAGNOSTICO TOTAL                   #" "Cyan"
L ("#  {0}                                   #" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) "Cyan"
L ("#  ROOT = {0}" -f $Root) "Cyan"
L ("#  Repair={0}  StartEngine={1}" -f $Repair, $StartEngine) "Cyan"
L "############################################################" "Cyan"

# ============================================================
# 1. ESTRUTURA DO PACOTE
# ============================================================
Section "1. ESTRUTURA DO PACOTE"

$required = @(
    "AURA_TUDO_EM_UM.bat",
    "engine\server.py",
    "engine\working_memory.py",
    "engine\engine_core.py",
    "engine\pillar_runtime.py",
    "engine\agent_registry.py",
    "bridge\server.py",
    "desktop\Aura.Desktop.csproj",
    "scripts\AURA_REPARAR_VENV_ENGINE.ps1",
    "scripts\AURA_START_ENGINE_FORTE.ps1"
)

$missingFiles = @()
foreach ($rel in $required) {
    $p = Join-Path $Root $rel
    if (Test-Path $p) {
        Pass "arquivo:$rel"
    } else {
        Fail "arquivo:$rel" "AUSENTE" "Reextrair ZIP para C:\aura\AURA_QUANT_X_12.7.0 (substituir ficheiros)"
        $missingFiles += $rel
    }
}

# ============================================================
# 2. PYTHON / VENV / FASTAPI
# ============================================================
Section "2. PYTHON / VENV / FASTAPI"

try {
    $pyVer = & python --version 2>&1
    Pass "python_sistema" "$pyVer"
} catch {
    Fail "python_sistema" "nao encontrado no PATH" "Instalar Python 3.11 e marcar Add to PATH"
}

if (Test-Path $VenvPy) {
    Pass "venv_python" $VenvPy
    $fa = & $VenvPy -c "import fastapi; print(fastapi.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Pass "fastapi" "v$fa"
    } else {
        Fail "fastapi" "$fa" "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1"
        if ($Repair) {
            L "  -> Repair: a reparar venv..." "Yellow"
            $repairScript = Join-Path $Root "scripts\AURA_REPARAR_VENV_ENGINE.ps1"
            if (Test-Path $repairScript) {
                & powershell -ExecutionPolicy Bypass -File $repairScript
                $fa2 = & $VenvPy -c "import fastapi; print(fastapi.__version__)" 2>&1
                if ($LASTEXITCODE -eq 0) { Pass "fastapi_apos_repair" "v$fa2" }
            }
        }
    }
    # imports extra
    foreach ($mod in @("uvicorn", "pydantic", "httpx")) {
        $out = & $VenvPy -c "import $mod; print('ok')" 2>&1
        if ($LASTEXITCODE -eq 0) { Pass "mod:$mod" } else { Fail "mod:$mod" "$out" }
    }
} else {
    Fail "venv_python" "ausente" "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1"
    if ($Repair) {
        $repairScript = Join-Path $Root "scripts\AURA_REPARAR_VENV_ENGINE.ps1"
        if (Test-Path $repairScript) {
            L "  -> Repair: a criar venv..." "Yellow"
            & powershell -ExecutionPolicy Bypass -File $repairScript
        }
    }
}

# ============================================================
# 3. PORTAS E PROCESSOS
# ============================================================
Section "3. PORTAS E PROCESSOS"

function Get-PortPid($port) {
    try {
        $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { return $c.OwningProcess }
    } catch {}
    try {
        $line = netstat -ano | Select-String (":$port\s+.*LISTENING") | Select-Object -First 1
        if ($line) {
            $parts = ($line.ToString() -split '\s+') | Where-Object { $_ -ne '' }
            return [int]$parts[-1]
        }
    } catch {}
    return $null
}

foreach ($port in @(8080, 8765, 8099)) {
    $pid_ = Get-PortPid $port
    if ($pid_) {
        $procName = "unknown"
        try { $procName = (Get-Process -Id $pid_ -ErrorAction SilentlyContinue).ProcessName } catch {}
        Pass "porta:$port" "LISTEN PID $pid_ ($procName)"
    } else {
        if ($port -eq 8765) {
            Fail "porta:$port" "LIVRE (Engine nao escuta)" "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_START_ENGINE_FORTE.ps1"
        } elseif ($port -eq 8080) {
            Fail "porta:$port" "LIVRE (Bridge nao escuta)" ".\AURA_TUDO_EM_UM.bat"
        } else {
            Warn "porta:$port" "LIVRE (Voice pode estar offline)"
        }
    }
}

# ============================================================
# 4. SAUDE HTTP DOS SERVICOS
# ============================================================
Section "4. SAUDE HTTP DOS SERVICOS"

$bridgeOk = $false
$engineOk = $false
$voiceOk = $false

try {
    $bh = Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 5
    $bridgeOk = $true
    $detail = ""
    if ($bh.feedLines -ne $null) { $detail += "feedLines=$($bh.feedLines) " }
    if ($bh.latestAgeSec -ne $null) { $detail += "latestAgeSec=$($bh.latestAgeSec) " }
    Pass "bridge_health" $detail.Trim()
} catch {
    Fail "bridge_health" $_.Exception.Message ".\AURA_TUDO_EM_UM.bat"
}

try {
    $eh = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 5
    $engineOk = $true
    Pass "engine_health" "status=$($eh.status) service=$($eh.service)"
} catch {
    Fail "engine_health" $_.Exception.Message "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_START_ENGINE_FORTE.ps1"
}

try {
    $vh = Invoke-RestMethod "http://127.0.0.1:8099/api/voice/health" -TimeoutSec 4 -ErrorAction Stop
    $voiceOk = $true
    Pass "voice_health" "OK"
} catch {
    try {
        $vh2 = Invoke-WebRequest "http://127.0.0.1:8099/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $voiceOk = $true
        Pass "voice_health" "OK (alt)"
    } catch {
        Warn "voice_health" "offline ou endpoint diferente"
    }
}

# ============================================================
# 5. IMPORT DO ENGINE (traceback se falhar)
# ============================================================
Section "5. IMPORT engine/server.py"

if ((Test-Path $VenvPy) -and (Test-Path $EnginePy)) {
    $loadTest = @"
import sys, os, traceback
sys.path.insert(0, r'$Root')
sys.path.insert(0, r'$Root\engine')
sys.path.insert(0, r'$Root\bridge')
os.chdir(r'$Root\engine')
os.environ['PAPER_TRADE'] = 'true'
os.environ['EXECUTION_ALLOWED'] = 'false'
os.environ['GLM_ADVISORY_ONLY'] = '1'
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('aura_engine_server', r'$EnginePy')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print('IMPORT_OK')
    print('APP_OK' if hasattr(mod, 'app') else 'APP_MISSING')
except Exception:
    traceback.print_exc()
    sys.exit(3)
"@
    $tmp = Join-Path $env:TEMP "aura_auto_load_$Stamp.py"
    $loadTest | Set-Content $tmp -Encoding UTF8
    $loadOut = & $VenvPy $tmp 2>&1 | Out-String
    $loadCode = $LASTEXITCODE
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ($loadCode -eq 0 -and $loadOut -match "IMPORT_OK") {
        Pass "engine_import" "server.py importa sem erro"
    } else {
        Fail "engine_import" "falha no import" "Ver secao TRACEBACK no relatorio; copiar working_memory.py se faltar"
        L "--- TRACEBACK ---" "Yellow"
        foreach ($line in ($loadOut -split "`n")) {
            if ($line.Trim()) { L ("  " + $line.TrimEnd()) "DarkYellow" }
        }
        L "--- FIM TRACEBACK ---" "Yellow"
        # Detectar modulo em falta
        if ($loadOut -match "No module named '([^']+)'") {
            $miss = $Matches[1]
            Fail "modulo_em_falta" $miss "Reextrair ZIP ou copiar engine\$miss.py / engine\$(($miss -replace '^engine\.','').Replace('.','\')) "
            $script:actions.Add("Modulo em falta: $miss - reextrair pacote completo para C:\aura\AURA_QUANT_X_12.7.0")
        }
    }
} else {
    Warn "engine_import" "venv ou server.py ausente - skip"
}

# ============================================================
# 6. live_latest.json + Bridge /latest
# ============================================================
Section "6. FEED live_latest + /api/cornerai/latest"

if (Test-Path $LatestPath) {
    $len = (Get-Item $LatestPath).Length
    $age = [math]::Round(((Get-Date) - (Get-Item $LatestPath).LastWriteTime).TotalSeconds, 1)
    if ($len -gt 100) {
        Pass "live_latest_file" "size=$len ageSec=$age"
    } else {
        Fail "live_latest_file" "vazio/pequeno ($len bytes)"
    }
} else {
    Fail "live_latest_file" "ausente" "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_INJETAR_LATEST_VALIDO.ps1"
}

if ($bridgeOk) {
    try {
        $latest = Invoke-RestMethod "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 5
        $homeName = $null; $fid = $null
        if ($latest.view) {
            $homeName = $latest.view.home
            $fid = $latest.view.fixture_id
        }
        Pass "bridge_latest" "HTTP 200 home=$homeName fixture=$fid"
    } catch {
        $msg = $_.Exception.Message
        Fail "bridge_latest" $msg "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_INJETAR_LATEST_VALIDO.ps1"
        if ($Repair) {
            $inj = Join-Path $Root "scripts\AURA_INJETAR_LATEST_VALIDO.ps1"
            if (Test-Path $inj) {
                L "  -> Repair: a injetar live_latest valido..." "Yellow"
                & powershell -ExecutionPolicy Bypass -File $inj
            }
        }
    }
} else {
    Warn "bridge_latest" "Bridge offline - skip"
}

# ============================================================
# 7. ESTADO DO ENGINE (ui/state)
# ============================================================
Section "7. ESTADO DO ENGINE (/api/ui/state)"

if ($engineOk) {
    try {
        $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
        Pass "engine_ui_state" "ok=$($ui.ok) fixtureId=$($ui.fixtureId) jarvis=$($ui.jarvis_state)"
        L ("         home={0} away={1} minute={2} paper_trade={3} capture_stale={4}" -f `
            $ui.home, $ui.away, $ui.minute, $ui.paper_trade, $ui.capture_stale) "Gray"
        if ($ui.fixtureId) {
            Pass "engine_fixture" $ui.fixtureId
        } else {
            Warn "engine_fixture" "sem fixtureId - abra partida AO VIVO no SokkerPRO + Mesa live + Iniciar"
        }
    } catch {
        Fail "engine_ui_state" $_.Exception.Message
    }
} else {
    Fail "engine_ui_state" "Engine offline"
}

# ============================================================
# 8. TENTAR SUBIR ENGINE (opcional)
# ============================================================
if ($StartEngine -and -not $engineOk) {
    Section "8. START ENGINE (pedido com -StartEngine)"
    $startScript = Join-Path $Root "scripts\AURA_START_ENGINE_FORTE.ps1"
    if (Test-Path $startScript) {
        L "  A executar AURA_START_ENGINE_FORTE.ps1 ..." "Yellow"
        & powershell -ExecutionPolicy Bypass -File $startScript
        Start-Sleep -Seconds 2
        try {
            $eh2 = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 4
            Pass "engine_health_apos_start" "status=$($eh2.status)"
            $engineOk = $true
        } catch {
            Fail "engine_health_apos_start" $_.Exception.Message
        }
    } else {
        Fail "start_engine_script" "AURA_START_ENGINE_FORTE.ps1 ausente"
    }
}

# ============================================================
# 9. RESUMO + RELATORIO
# ============================================================
Section "RESUMO FINAL"

$total = $script:okCount + $script:failCount
L ("Checks OK:   {0}" -f $script:okCount) "Green"
L ("Checks FAIL: {0}" -f $script:failCount) $(if ($script:failCount -gt 0) { "Red" } else { "Green" })
L ("Score:       {0} / {1}" -f $script:okCount, $total) "Cyan"

if ($script:problems.Count -gt 0) {
    L ""
    L "PROBLEMAS:" "Red"
    foreach ($p in $script:problems) { L ("  - {0}" -f $p) "Red" }
}

if ($script:actions.Count -gt 0) {
    L ""
    L "ACOES RECOMENDADAS (em ordem):" "Yellow"
    $i = 1
    $uniq = $script:actions | Select-Object -Unique
    foreach ($a in $uniq) {
        L ("  {0}. {1}" -f $i, $a) "Yellow"
        $i++
    }
}

L ""
L "COMANDOS UTEIS:" "Cyan"
L "  .\AURA_TUDO_EM_UM.bat"
L "  powershell -ExecutionPolicy Bypass -File .\scripts\AURA_START_ENGINE_FORTE.ps1"
L "  powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1"
L "  powershell -ExecutionPolicy Bypass -File .\scripts\AURA_INJETAR_LATEST_VALIDO.ps1"
L "  powershell -ExecutionPolicy Bypass -File .\scripts\AURA_AUTO_DIAGNOSTICO_TOTAL.ps1 -Repair -StartEngine"

# Status operacional resumido
L ""
$statusLine = "Bridge={0} | Engine={1} | Voice={2}" -f `
    $(if ($bridgeOk) { "UP" } else { "DOWN" }), `
    $(if ($engineOk) { "UP" } else { "DOWN" }), `
    $(if ($voiceOk) { "UP" } else { "DOWN/SKIP" })
L ("STATUS: {0}" -f $statusLine) $(if ($bridgeOk -and $engineOk) { "Green" } else { "Yellow" })

# Gravar relatorio texto
$script:lines | Set-Content $ReportPath -Encoding UTF8
L ""
L ("Relatorio TXT:  {0}" -f $ReportPath) "Cyan"

# Gravar relatorio JSON
$jsonObj = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    root = $Root
    okCount = $script:okCount
    failCount = $script:failCount
    bridgeOk = $bridgeOk
    engineOk = $engineOk
    voiceOk = $voiceOk
    problems = @($script:problems)
    actions = @($script:actions | Select-Object -Unique)
    checks = $script:checks
}
$jsonObj | ConvertTo-Json -Depth 6 | Set-Content $JsonReportPath -Encoding UTF8
L ("Relatorio JSON: {0}" -f $JsonReportPath) "Cyan"

L ""
L "############################################################" "Cyan"
L "#  FIM DO AUTO DIAGNOSTICO                                  #" "Cyan"
L "############################################################" "Cyan"
L ""
L "Copie o ficheiro TXT ou JSON e envie se precisar de suporte." "Gray"

# Exit code
if ($script:failCount -gt 0) { exit 1 } else { exit 0 }
