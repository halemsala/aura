# ============================================================
# AURA QUANT-X - TERMINAL 01  (QA destrutivo em loop)
# Nao mata Desktop, nao recria venv, nao injeta template.
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_TERMINAL_QA.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_TERMINAL_QA.ps1 -Once
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_TERMINAL_QA.ps1 -IntervalSec 8
# ============================================================
param(
    [switch]$Once,
    [switch]$AI,
    [int]$IntervalSec = 10,
    [int]$AiEvery = 3
)

$ErrorActionPreference = "Continue"
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
Set-Location $Root
$LogDir = Join-Path $Root "logs_instalacao"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "terminal_qa_$Stamp.txt"
$JsonFile = Join-Path $LogDir "terminal_qa_$Stamp.json"

$MESA_MIN = 12000
$round = 0
$history = New-Object System.Collections.Generic.List[object]

function Write-Log([string]$m, [string]$c = "Gray") {
    $line = ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m)
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line -ForegroundColor $c
}

function Try-Json($url, [int]$timeout = 4) {
    try {
        return Invoke-RestMethod $url -TimeoutSec $timeout
    } catch {
        return $null
    }
}

function Get-LeafCount($obj) {
    if ($null -eq $obj) { return 0 }
    $n = 0
    if ($obj -is [System.Collections.IEnumerable] -and -not ($obj -is [string])) {
        foreach ($x in $obj) { $n += Get-LeafCount $x }
        return $n
    }
    $props = @()
    try { $props = $obj.PSObject.Properties } catch { return 1 }
    if (-not $props -or $props.Count -eq 0) { return 1 }
    foreach ($p in $props) {
        $v = $p.Value
        if ($null -eq $v -or $v -is [string] -or $v -is [ValueType]) { $n++ }
        else { $n += Get-LeafCount $v }
    }
    return $n
}

function Invoke-Round {
    $script:round++
    $fails = New-Object System.Collections.Generic.List[string]
    $warns = New-Object System.Collections.Generic.List[string]
    $oks = New-Object System.Collections.Generic.List[string]
    function F([string]$m) { $fails.Add($m) | Out-Null }
    function W([string]$m) { $warns.Add($m) | Out-Null }
    function O([string]$m) { $oks.Add($m) | Out-Null }

    Write-Host ""
    Write-Host ("======== RODADA {0}  TERMINAL 01 QA  {1} ========" -f $round, (Get-Date -Format "HH:mm:ss")) -ForegroundColor Cyan

    # --- T01: Desktop EXE ---
    $exe = Join-Path $Root "desktop\publish\Aura.QuantX.Desktop.exe"
    if (Test-Path $exe) { O "Desktop EXE presente" } else { F "Desktop EXE AUSENTE em desktop\bin - nao faca taskkill; rode AURA_TUDO_EM_UM.bat" }

    $deskProc = Get-Process -Name "Aura.QuantX.Desktop" -ErrorAction SilentlyContinue
    if ($deskProc) { O ("Desktop processo PID=" + ($deskProc.Id -join ",")) } else { W "Desktop EXE nao esta a correr (Start-Process desktop\publish\Aura.QuantX.Desktop.exe)" }

    # --- T02: index.html tamanho (dashboard novo) ---
    $mesaPaths = @(
        (Join-Path $Root "desktop\ui\matriz_v22\index.html"),
        (Join-Path $Root "desktop\ui\matriz_v22\index.html"),
        (Join-Path $Root "desktop\publish\ui\matriz_v22\index.html")
    )
    foreach ($mp in $mesaPaths) {
        if (-not (Test-Path $mp)) { F "index.html ausente: $mp"; continue }
        $len = (Get-Item $mp).Length
        if ($len -lt $MESA_MIN) { F "index.html ANTIGO size=$len (precisa >= $MESA_MIN) em $mp" }
        else { O ("index.html OK size=$len  " + $mp.Replace($Root + "\", "")) }
    }

    # --- T03: working_memory ---
    $wm = Join-Path $Root "engine\working_memory.py"
    if (Test-Path $wm) { O "engine\working_memory.py presente" } else { F "engine\working_memory.py AUSENTE - Engine vai crashar no import" }

    # --- T04: servicos ---
    $bridge = Try-Json "http://127.0.0.1:8080/health"
    $engine = Try-Json "http://127.0.0.1:8765/api/health"
    $voice  = Try-Json "http://127.0.0.1:8099/api/voice/health"
    if ($bridge) { O ("Bridge UP feedLines={0} latestAgeSec={1}" -f $bridge.feedLines, $bridge.latestAgeSec) } else { F "Bridge OFF :8080" }
    if ($engine) { O "Engine UP" } else { F "Engine OFF :8765" }
    if ($voice)  { O "Voice UP" } else { W "Voice OFF :8099 (opcional)" }

    # --- T05: ui/state ---
    $ui = Try-Json "http://127.0.0.1:8765/api/ui/state"
    $uiHome = $null; $uiAway = $null; $uiMin = $null; $uiFid = $null; $uiJarvis = $null; $uiStale = $null
    if ($ui) {
        $uiFid = [string]$ui.fixtureId
        $uiHome = [string]$ui.home
        $uiAway = [string]$ui.away
        $uiMin = $ui.minute
        $uiJarvis = [string]$ui.jarvis_state
        $uiStale = $ui.capture_stale
        if ($ui.ok -eq $true) { O "ui/state ok=True" } else { F "ui/state ok!=True" }
        if ([string]::IsNullOrWhiteSpace($uiFid) -or $uiFid -eq "None") { F "fixtureId VAZIO - Matriz sem jogo" } else { O "fixtureId=$uiFid" }
        if ([string]::IsNullOrWhiteSpace($uiHome) -or $uiHome -eq "None") { F "home VAZIO no ui/state" } else { O "home=$uiHome" }
        if ([string]::IsNullOrWhiteSpace($uiAway) -or $uiAway -eq "None") { F "away VAZIO no ui/state" } else { O "away=$uiAway" }
        if ($null -eq $uiMin) { F "minute VAZIO" } else { O "minute=$uiMin" }
        if ($uiStale -eq $true) { F "capture_stale=True - captura parada" } else { O "capture_stale=False" }
        if ($uiJarvis -eq "DEGRADADO") { W "jarvis=DEGRADADO" }
        elseif ($uiJarvis) { O "jarvis=$uiJarvis" }
    } else {
        F "ui/state inacessivel"
    }

    # --- T06: live_latest ---
    $latestPath = Join-Path $Root "bridge\live_latest.json"
    $latHome = $null; $latFid = $null; $source = $null; $age = $null
    if (-not (Test-Path $latestPath)) {
        F "bridge\live_latest.json ausente - sem captura"
    } else {
        $age = [math]::Round(((Get-Date) - (Get-Item $latestPath).LastWriteTime).TotalSeconds, 1)
        $raw = $null
        try { $raw = Get-Content $latestPath -Raw -Encoding UTF8 } catch { F "nao leu live_latest.json" }
        $doc = $null
        if ($raw) {
            try { $doc = $raw | ConvertFrom-Json } catch { F "live_latest.json JSON invalido" }
        }
        if ($doc) {
            $view = $doc
            if ($doc.payload) { $view = $doc.payload }
            elseif ($doc.view) { $view = $doc.view }
            if ($doc.payload -and $doc.payload.source) { $source = [string]$doc.payload.source }
            elseif ($view.source) { $source = [string]$view.source }
            elseif ($doc.source) { $source = [string]$doc.source }
            if ($view.fixture_id) { $latFid = [string]$view.fixture_id }
            elseif ($view.fixture -and $view.fixture.id) { $latFid = [string]$view.fixture.id }
            if ($view.home) { $latHome = [string]$view.home }
            elseif ($view.fixture -and $view.fixture.home) { $latHome = [string]$view.fixture.home }
            if ($age -gt 45) { F "Feed STALE ageSec=$age (precisa Mesa live + jogo AO VIVO)" }
            elseif ($age -gt 20) { W "Feed velho ageSec=$age" }
            else { O "Feed fresco ageSec=$age" }
            if ($source -match "inject|template|manual|diagnostico|Aldosivi") {
                F "source=$source DADOS INJETADOS - nao e captura real"
            } elseif ($source -match "aura-capture-webview2") {
                O "source=$source"
            } elseif ([string]::IsNullOrWhiteSpace($source)) {
                W "source vazio"
            } else { W "source=$source" }
            if ($latHome) { O "bridge home=$latHome fid=$latFid" } else { F "bridge home vazio" }
        }
    }

    # --- T07: /latest HTTP ---
    $latestApi = Try-Json "http://127.0.0.1:8080/api/cornerai/latest"
    if ($latestApi) { O "GET /api/cornerai/latest HTTP 200" }
    else {
        try {
            Invoke-WebRequest "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 4 | Out-Null
        } catch {
            $msg = $_.Exception.Message
            if ($msg -match "401") { W "GET /latest 401 (token) - health pode estar OK na mesma" }
            else { F "GET /latest falhou: $msg" }
        }
    }

    # --- T08: fixture mismatch (quebra Matriz vs pane) ---
    if ($uiFid -and $latFid -and ($uiFid -ne $latFid) -and ($uiFid -ne "None") -and ($latFid -ne "None")) {
        F "FIXTURE DESSINCRONIZADO Engine=$uiFid ($uiHome) vs Bridge=$latFid ($latHome) - Matriz mostra jogo errado"
    } elseif ($uiFid -and $latFid) {
        O "fixture alinhado Engine=Bridge=$uiFid"
    }

    # --- T09: minuto suspeito ---
    if ($null -ne $uiMin) {
        try {
            $mi = [int]$uiMin
            if ($mi -lt 0 -or $mi -gt 130) { F "minute fora de 0-130: $mi" }
        } catch { W "minute nao numerico: $uiMin" }
    }

    # --- T10: skill-feed ---
    $skill = Try-Json "http://127.0.0.1:8080/api/cornerai/skill-feed"
    if ($skill) { O ("skill-feed presente keys~" + (Get-LeafCount $skill)) }
    else { W "skill-feed ausente - H2H/odds/charts profundos nao vao para a Matriz" }

    # --- T11: nao usar template Aldosivi ---
    if ($uiHome -match "Aldosivi" -or $latHome -match "Aldosivi") {
        F "TEMPLATE Aldosivi detectado - NAO rode AURA_INJETAR_LATEST_VALIDO"
    }

    # --- score ---
    $failN = $fails.Count
    $warnN = $warns.Count
    $okN = $oks.Count
    $verdict = "PASS"
    if ($failN -gt 0) { $verdict = "FAIL" }
    elseif ($warnN -gt 0) { $verdict = "WARN" }

    foreach ($x in $oks)   { Write-Log ("  [OK]   " + $x) "Green" }
    foreach ($x in $warns) { Write-Log ("  [WARN] " + $x) "Yellow" }
    foreach ($x in $fails) { Write-Log ("  [FAIL] " + $x) "Red" }

    Write-Host ("VEREDICTO R{0}: {1}   OK={2}  WARN={3}  FAIL={4}" -f $round, $verdict, $okN, $warnN, $failN) -ForegroundColor $(
        if ($verdict -eq "PASS") { "Green" } elseif ($verdict -eq "WARN") { "Yellow" } else { "Red" }
    )

    if ($failN -gt 0) {
        Write-Host "ACOES (Terminal 01 -> voce):" -ForegroundColor Yellow
        if ($fails | Where-Object { $_ -match "EXE AUSENTE" }) { Write-Host "  - .\AURA_TUDO_EM_UM.bat   (so se o EXE nao existir)" -ForegroundColor Yellow }
        if ($fails | Where-Object { $_ -match "index.html ANTIGO" }) { Write-Host "  - Copy-Item index.html para bin\ui\matriz_v22 (size 14582)" -ForegroundColor Yellow }
        if ($fails | Where-Object { $_ -match "STALE|ausente - sem captura|home VAZIO" }) { Write-Host "  - Pane direita: 1 jogo AO VIVO + Mesa live" -ForegroundColor Yellow }
        if ($fails | Where-Object { $_ -match "DESSINCRONIZADO" }) { Write-Host "  - Feche outros fixtures; deixe so o jogo da pane direita" -ForegroundColor Yellow }
        if ($fails | Where-Object { $_ -match "working_memory" }) { Write-Host "  - Reponha engine\working_memory.py do ZIP" -ForegroundColor Yellow }
        if ($fails | Where-Object { $_ -match "Engine OFF" }) { Write-Host "  - powershell -File .\scripts\AURA_START_ENGINE_FORTE.ps1" -ForegroundColor Yellow }
    }

    $rec = [pscustomobject]@{
        round = $round
        ts = (Get-Date).ToString("o")
        verdict = $verdict
        ok = $okN; warn = $warnN; fail = $failN
        fixtureEngine = $uiFid
        fixtureBridge = $latFid
        home = $uiHome
        away = $uiAway
        minute = $uiMin
        jarvis = $uiJarvis
        ageSec = $age
        source = $source
        fails = @($fails)
    }
    $history.Add($rec) | Out-Null
    ($history | ConvertTo-Json -Depth 6) | Set-Content $JsonFile -Encoding UTF8

    if ($AI -and ($round % [Math]::Max(1, $AiEvery) -eq 0)) {
        $py = Join-Path $Root "engine\venv\Scripts\python.exe"
        $aud = Join-Path $Root "scripts\AURA_AI_AUDITOR.py"
        if ((Test-Path $py) -and (Test-Path $aud)) {
            Write-Host "---- L7 AI AUDITOR (rodada $round) ----" -ForegroundColor Magenta
            & $py $aud 2>&1 | ForEach-Object { Write-Host $_ }
        } else {
            Write-Host "[WARN] AI auditor: python/script ausente" -ForegroundColor Yellow
        }
    }
    return $verdict
}

Write-Host "############################################################" -ForegroundColor Cyan
Write-Host "#  AURA TERMINAL 01 - QA DESTRUTIVO EM LOOP                #" -ForegroundColor Cyan
Write-Host ("#  ROOT={0}" -f $Root) -ForegroundColor Cyan
Write-Host ("#  Intervalo={0}s  Once={1}" -f $IntervalSec, $Once) -ForegroundColor Cyan
Write-Host "#  NAO mata processos. NAO recria venv.                    #" -ForegroundColor Cyan
Write-Host ("#  Log: {0}" -f $LogFile) -ForegroundColor Cyan
Write-Host "############################################################" -ForegroundColor Cyan
Write-Host "Ctrl+C para parar." -ForegroundColor DarkGray

if ($Once) {
    Invoke-Round | Out-Null
    Write-Host ("Log: {0}" -f $LogFile)
    exit 0
}

while ($true) {
    Invoke-Round | Out-Null
    Start-Sleep -Seconds ([Math]::Max(3, $IntervalSec))
}
