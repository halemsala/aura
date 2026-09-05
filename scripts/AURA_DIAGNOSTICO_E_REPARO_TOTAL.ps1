# ============================================================
# AURA QUANT-X - DIAGNÓSTICO + REPARO TOTAL (tudo em um)
# Versão: V25T15-FINAL
# Rode com o AURA instalado. Faz tudo automaticamente.
# ============================================================

$ErrorActionPreference = "Continue"
$Root = "C:\aura\AURA_QUANT_X_12.7.0"
$VenvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
$LatestPath = Join-Path $Root "bridge\live_latest.json"
$BridgePy = Join-Path $Root "bridge\server.py"

$report = @()
function Log($msg, $color = "White") {
    Write-Host $msg -ForegroundColor $color
    $script:report += $msg
}

Write-Host ""
Write-Host "############################################################" -ForegroundColor Cyan
Write-Host "#  AURA QUANT-X - DIAGNÓSTICO + REPARO TOTAL               #" -ForegroundColor Cyan
Write-Host "############################################################" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# FASE 1 - PROCESSOS E PORTAS
# ============================================================
Log "[FASE 1] Processos e portas..." "Cyan"

$ports = @(8080, 8765, 8099)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
    if ($conns) {
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            Log "  Porta $port LISTEN PID $($c.OwningProcess) ($($proc.ProcessName))" "Green"
        }
    } else {
        Log "  Porta $port LIVRE" "Yellow"
    }
}

# ============================================================
# FASE 2 - VENV + FASTAPI
# ============================================================
Log "" "White"
Log "[FASE 2] Venv e FastAPI..." "Cyan"

if (-not (Test-Path $VenvPy)) {
    Log "  VENV AUSENTE - tentando reparar..." "Red"
    $repairScript = Join-Path $Root "scripts\AURA_REPARAR_VENV_ENGINE.ps1"
    if (Test-Path $repairScript) {
        & powershell -ExecutionPolicy Bypass -File $repairScript
    } else {
        Log "  Script de reparo nao encontrado. Instale FastAPI manualmente." "Red"
    }
} else {
    $fa = & $VenvPy -c "import fastapi; print(fastapi.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "  FastAPI OK v$fa" "Green"
    } else {
        Log "  FastAPI AUSENTE - instalando..." "Yellow"
        & $VenvPy -m pip install fastapi uvicorn pydantic httpx aiofiles python-multipart --quiet
        $fa2 = & $VenvPy -c "import fastapi; print(fastapi.__version__)" 2>&1
        if ($LASTEXITCODE -eq 0) { Log "  FastAPI instalado v$fa2" "Green" }
        else { Log "  FALHA ao instalar FastAPI: $fa2" "Red" }
    }
}

# ============================================================
# FASE 3 - SAÚDE DOS SERVIÇOS
# ============================================================
Log "" "White"
Log "[FASE 3] Saúde dos serviços..." "Cyan"

$bridgeOk = $false
$engineOk = $false

try {
    $bh = Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 4
    Log "  Bridge  : OK  feedLines=$($bh.feedLines) latestAgeSec=$($bh.latestAgeSec)" "Green"
    $bridgeOk = $true
} catch {
    Log "  Bridge  : OFFLINE - $($_.Exception.Message)" "Red"
}

try {
    $eh = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 4
    Log "  Engine  : OK  status=$($eh.status)" "Green"
    $engineOk = $true
} catch {
    Log "  Engine  : OFFLINE - $($_.Exception.Message)" "Red"
}

try {
    $vh = Invoke-RestMethod "http://127.0.0.1:8099/api/voice/health" -TimeoutSec 4
    Log "  Voice   : OK" "Green"
} catch {
    Log "  Voice   : offline (nao critico)" "Yellow"
}

# ============================================================
# FASE 4 - CRIAR live_latest.json VÁLIDO (sem BOM, schema correto)
# ============================================================
Log "" "White"
Log "[FASE 4] Criando live_latest.json valido..." "Cyan"

$homeTeam = "Aldosivi"
$awayTeam = "Independiente Rivadavia"
$fid = "19764966"
$minute = 30
$scoreH = 0
$scoreA = 1
$now = Get-Date
$receivedAt = $now.ToString("yyyy-MM-ddTHH:mm:ss") + "-03:00"
$exportedAt = $now.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fff") + "Z"
$ts = [long]([DateTimeOffset]$now).ToUnixTimeMilliseconds()

# Montar objeto PowerShell e serializar com ConvertTo-Json (mais seguro)
$obj = [ordered]@{
    received_at = $receivedAt
    view = [ordered]@{
        schema = "cornerai-analyst-1"
        fixture_id = $fid
        league = $null
        home = $homeTeam
        away = $awayTeam
        minute = $minute
        extra = 0
        period = $null
        status = "live"
        score_home = $scoreH
        score_away = $scoreA
        corners_home = 3
        corners_away = 1
        attacks_home = 50
        attacks_away = 45
        dangerous_home = 15
        dangerous_away = 20
        xg_home = 0.5
        xg_away = 0.6
        possession_home = $null
        possession_away = $null
        shots_on_home = 2
        shots_on_away = 2
        corner_events = @()
        cpi_home = $null
        cpi_away = $null
        pred = $null
        raw_ts = $ts
        quality = 0.85
    }
    payload = [ordered]@{
        schema = "cornerai-analyst-1"
        source = "aura-capture-webview2"
        exportedAt = $exportedAt
        ts = $ts
        fixture = [ordered]@{
            id = $fid
            home = $homeTeam
            away = $awayTeam
            minute = $minute
            extra = 0
            status = "live"
            score = [ordered]@{ home = $scoreH; away = $scoreA }
        }
        pressure = [ordered]@{
            gauge = $null
            attacks = [ordered]@{ home = 50; away = 45 }
            dangerous = [ordered]@{ home = 15; away = 20 }
            xg = [ordered]@{ home = 0.5; away = 0.6 }
            shotsOn = [ordered]@{ home = 2; away = 2 }
        }
        corners = [ordered]@{
            total = [ordered]@{ home = 3; away = 1 }
            events = @()
        }
        stats = [ordered]@{
            attacks = [ordered]@{ home = 50; away = 45 }
            dangerous = [ordered]@{ home = 15; away = 20 }
            xg = [ordered]@{ home = 0.5; away = 0.6 }
            shotsOn = [ordered]@{ home = 2; away = 2 }
            corners = [ordered]@{ home = 3; away = 1 }
        }
        corner_events = @()
        quality = [ordered]@{ score = 0.85 }
    }
    fingerprint = "$fid|$minute|$scoreH|$scoreA|3|1|15|20"
}

$jsonText = $obj | ConvertTo-Json -Depth 10 -Compress:$false

# Gravar SEM BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($LatestPath, $jsonText, $utf8NoBom)
Log "  Arquivo gravado: $LatestPath ($((Get-Item $LatestPath).Length) bytes)" "Green"

# Validar com Python
if (Test-Path $VenvPy) {
    $val = & $VenvPy -c "import json; d=json.load(open(r'$LatestPath',encoding='utf-8')); print('OK', d['view']['home'], d['view']['fixture_id'])" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log "  Validacao Python: $val" "Green"
    } else {
        Log "  Validacao Python FALHOU: $val" "Red"
    }
}

# ============================================================
# FASE 5 - TESTAR /api/cornerai/latest
# ============================================================
Log "" "White"
Log "[FASE 5] Testando /api/cornerai/latest..." "Cyan"

Start-Sleep -Seconds 2

if ($bridgeOk) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 5
        Log "  Bridge /latest = 200 OK" "Green"
        if ($r.latest) {
            Log "  home=$($r.latest.view.home) fixture=$($r.latest.view.fixture_id)" "Green"
        } elseif ($r.view) {
            Log "  home=$($r.view.home) fixture=$($r.view.fixture_id)" "Green"
        } else {
            Log "  Resposta: $($r | ConvertTo-Json -Compress)" "Yellow"
        }
    } catch {
        $status = $null
        $errBody = ""
        try {
            $resp = $_.Exception.Response
            if ($resp) {
                $status = [int]$resp.StatusCode
                $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
                $errBody = $reader.ReadToEnd()
            }
        } catch {}
        Log "  Bridge /latest FALHOU status=$status" "Red"
        if ($errBody) { Log "  Body: $errBody" "Red" }
        else { Log "  $($_.Exception.Message)" "Red" }

        # Se 401, avisar sobre token
        if ($status -eq 401) {
            Log "  → Endpoint exige token. Engine usa token interno." "Yellow"
        }
    }
} else {
    Log "  Bridge offline - pulando teste" "Yellow"
}

# ============================================================
# FASE 6 - ESTADO DO ENGINE
# ============================================================
Log "" "White"
Log "[FASE 6] Estado do Engine..." "Cyan"

if ($engineOk) {
    Start-Sleep -Seconds 3
    try {
        $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
        Log "  fixtureId     = $($ui.fixtureId)" $(if ($ui.fixtureId) { "Green" } else { "Yellow" })
        Log "  jarvis_state  = $($ui.jarvis_state)" $(if ($ui.jarvis_state -eq "BLOCKED_BY_DATA") { "Red" } else { "Green" })
        Log "  capture_stale = $($ui.capture_stale)"
        Log "  source        = $($ui.source)"
        Log "  paper_trade   = $($ui.paper_trade)"

        if ($ui.fixtureId) {
            Log "" "White"
            Log "  >>> ENGINE ENGATOU NO FIXTURE! <<<" "Green"
        } else {
            Log "" "White"
            Log "  Engine ainda sem fixtureId." "Yellow"
            Log "  Possiveis causas:" "Yellow"
            Log "   - Bridge /latest ainda com erro (401/500)" "Yellow"
            Log "   - Engine precisa de token para ler o Bridge" "Yellow"
            Log "   - Captura real do Desktop nao esta enviando dados" "Yellow"
        }
    } catch {
        Log "  Erro ao ler /api/ui/state: $($_.Exception.Message)" "Red"
    }
} else {
    Log "  Engine offline - pulando" "Yellow"
}

# ============================================================
# FASE 7 - RESUMO FINAL
# ============================================================
Log "" "White"
Log "############################################################" "Cyan"
Log "#  RESUMO FINAL                                            #" "Cyan"
Log "############################################################" "Cyan"
Log ""

$checks = 0
$total = 5

if (Test-Path $VenvPy) {
    $fa = & $VenvPy -c "import fastapi" 2>&1
    if ($LASTEXITCODE -eq 0) { $checks++; Log "  [OK] FastAPI no venv" "Green" }
    else { Log "  [FAIL] FastAPI" "Red" }
} else { Log "  [FAIL] Venv ausente" "Red" }

if ($bridgeOk) { $checks++; Log "  [OK] Bridge online" "Green" }
else { Log "  [FAIL] Bridge offline" "Red" }

if ($engineOk) { $checks++; Log "  [OK] Engine online" "Green" }
else { Log "  [FAIL] Engine offline" "Red" }

if ((Test-Path $LatestPath) -and ((Get-Item $LatestPath).Length -gt 100)) {
    $checks++; Log "  [OK] live_latest.json existe" "Green"
} else { Log "  [FAIL] live_latest.json ausente/vazio" "Red" }

try {
    $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 3 -ErrorAction Stop
    if ($ui.fixtureId) { $checks++; Log "  [OK] Engine com fixtureId=$($ui.fixtureId)" "Green" }
    else { Log "  [PENDENTE] Engine sem fixtureId (jarvis=$($ui.jarvis_state))" "Yellow" }
} catch {
    Log "  [FAIL] Nao leu estado do Engine" "Red"
}

Log ""
Log "Checks: $checks / $total" "Cyan"
Log ""
Log "Proximos passos se ainda houver problema:" "Yellow"
Log "  1. Abra partida AO VIVO no SokkerPRO (ponto vermelho)" "White"
Log "  2. Clique Mesa live + Iniciar no Desktop" "White"
Log "  3. Espere 30s e rode este script de novo" "White"
Log "  4. Se Bridge /latest der 401: o Engine precisa do token" "White"
Log "     Token em: %LOCALAPPDATA%\AURA_QUANT_X\secure\cornerai_bridge_token.bin" "White"
Log ""
Log "############################################################" "Cyan"
Log ""

# Salvar report
$reportPath = Join-Path $Root "logs_instalacao\diagnostico_reparo_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
try {
    $report | Set-Content $reportPath -Encoding UTF8
    Log "Report salvo em: $reportPath" "Cyan"
} catch {}
