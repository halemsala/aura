# ============================================================
# AURA QUANT-X - TESTE E2E CAPTURA + MATRIZ (ponta a ponta)
# NAO confunde "servicos UP" com "feed rico da SokkerPRO".
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\AURA_E2E_CAPTURA_MATRIZ.ps1
# ============================================================
$ErrorActionPreference = "Continue"
$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
$LogDir = Join-Path $Root "logs_instalacao"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Report = Join-Path $LogDir "e2e_captura_$Stamp.txt"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$lines = New-Object System.Collections.Generic.List[string]
$pass = 0; $fail = 0; $warn = 0
function L($m,$c="White"){ $lines.Add($m); Write-Host $m -ForegroundColor $c }
function OK($m){ $script:pass++; L "  [OK]   $m" "Green" }
function BAD($m){ $script:fail++; L "  [FAIL] $m" "Red" }
function WN($m){ $script:warn++; L "  [WARN] $m" "Yellow" }
function SEC($t){ L ""; L "==== $t ====" "Cyan" }

L "############################################################" "Cyan"
L "#  AURA E2E - CAPTURA SOKKERPRO + ENGINE + MATRIZ         #" "Cyan"
L ("#  {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) "Cyan"
L "############################################################" "Cyan"
L "Este teste NAO aceita 'so nome e placar' como sucesso."
L "Exige feed fresco, source de captura real e campos de stats."

# ---- 1 Servicos basicos ----
SEC "1. SERVICOS (pre-requisito, nao e o objetivo final)"
$bridgeOk=$false; $engineOk=$false
try { $h=Invoke-RestMethod "http://127.0.0.1:8080/health" -TimeoutSec 4; $bridgeOk=$true; OK "Bridge health feedLines=$($h.feedLines) latestAgeSec=$($h.latestAgeSec)" } catch { BAD "Bridge offline: $($_.Exception.Message)" }
try { $h=Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 4; $engineOk=$true; OK "Engine health status=$($h.status)" } catch { BAD "Engine offline: $($_.Exception.Message)" }

# ---- 2 live_latest.json riqueza ----
SEC "2. live_latest.json - RIQUEZA DO PAYLOAD"
$latestPath = Join-Path $Root "bridge\live_latest.json"
$doc = $null
if (-not (Test-Path $latestPath)) {
    BAD "Arquivo ausente: bridge\live_latest.json"
} else {
    $age = [math]::Round(((Get-Date) - (Get-Item $latestPath).LastWriteTime).TotalSeconds, 1)
    $raw = Get-Content $latestPath -Raw -Encoding UTF8
    try { $doc = $raw | ConvertFrom-Json } catch { BAD "JSON invalido: $($_.Exception.Message)" }
    if ($doc) {
        OK "Arquivo existe size=$((Get-Item $latestPath).Length) ageSec=$age"
        if ($age -gt 45) { BAD "Feed STALE ageSec=$age (precisa < 45s com Mesa live + partida AO VIVO)" }
        elseif ($age -gt 20) { WN "Feed um pouco velho ageSec=$age (ideal < 15s)" }
        else { OK "Feed fresco ageSec=$age" }

        $view = $null
        if ($doc.view) { $view = $doc.view }
        elseif ($doc.payload) { $view = $doc.payload }
        else { $view = $doc }

        $source = $null
        if ($doc.payload -and $doc.payload.source) { $source = [string]$doc.payload.source }
        elseif ($view.source) { $source = [string]$view.source }
        elseif ($doc.source) { $source = [string]$doc.source }

        if ($source -match "aura-capture-webview2") {
            OK "source=$source (captura Desktop WebView2)"
        } elseif ($source -match "inject|template|manual|diagnostico") {
            BAD "source=$source - DADOS INJETADOS/TEMPLATE, nao captura real"
        } elseif ([string]::IsNullOrWhiteSpace($source)) {
            WN "source vazio - nao da para provar origem da captura"
        } else {
            WN "source=$source"
        }

        # extrair campos
        $fid = $null; $homeN=$null; $awayN=$null; $min=$null; $sh=$null; $sa=$null
        if ($view.fixture_id) { $fid = $view.fixture_id }
        if ($view.fixture -and $view.fixture.id) { $fid = $view.fixture.id }
        if ($doc.view -and $doc.view.fixture_id) { $fid = $doc.view.fixture_id }
        if ($view.home) { $homeN = $view.home }
        if ($view.fixture -and $view.fixture.home) { $homeN = $view.fixture.home }
        if ($view.away) { $awayN = $view.away }
        if ($view.fixture -and $view.fixture.away) { $awayN = $view.fixture.away }
        if ($view.minute -ne $null) { $min = $view.minute }
        if ($view.fixture -and $view.fixture.minute -ne $null) { $min = $view.fixture.minute }
        if ($view.score_home -ne $null) { $sh = $view.score_home }
        if ($view.fixture -and $view.fixture.score) { $sh = $view.fixture.score.home; $sa = $view.fixture.score.away }

        L "  campos: fixture=$fid | $homeN x $awayN | min=$min | placar=$sh-$sa" "Gray"

        if ([string]::IsNullOrWhiteSpace([string]$fid)) { BAD "fixture_id ausente" } else { OK "fixture_id=$fid" }
        if ([string]::IsNullOrWhiteSpace([string]$homeN) -or [string]::IsNullOrWhiteSpace([string]$awayN)) {
            BAD "home/away vazios ou incompletos"
        } else { OK "times preenchidos: $homeN x $awayN" }
        if ($min -eq $null) { BAD "minuto ausente" }
        elseif ([int]$min -eq 30 -and $source -notmatch "webview") { WN "minuto=30 suspeito (valor default do template de injecao)" }
        else { OK "minuto=$min" }

        # stats ricos
        $hasAtt=$false; $hasXg=$false; $hasPress=$false; $hasDanger=$false; $hasCorners=$false; $hasShots=$false
        function HasNum($o) {
            if ($null -eq $o) { return $false }
            if ($o -is [ValueType]) { return $true }
            if ($o.home -ne $null -or $o.away -ne $null) { return $true }
            return $false
        }
        if ($view.pressure) {
            if ($view.pressure.gauge -ne $null) { $hasPress = $true }
            if (HasNum $view.pressure.attacks) { $hasAtt = $true }
            if (HasNum $view.pressure.dangerous) { $hasDanger = $true }
            if (HasNum $view.pressure.xg) { $hasXg = $true }
            if (HasNum $view.pressure.shotsOn) { $hasShots = $true }
        }
        if ($view.stats) {
            if (HasNum $view.stats.attacks) { $hasAtt = $true }
            if (HasNum $view.stats.dangerous) { $hasDanger = $true }
            if (HasNum $view.stats.xg) { $hasXg = $true }
            if (HasNum $view.stats.shotsOn) { $hasShots = $true }
            if (HasNum $view.stats.corners) { $hasCorners = $true }
        }
        if ($view.attacks_home -ne $null -or $view.attacks_away -ne $null) { $hasAtt = $true }
        if ($view.xg_home -ne $null -or $view.xg_away -ne $null) { $hasXg = $true }
        if ($view.corners_home -ne $null -or $view.corners -ne $null) { $hasCorners = $true }
        if ($view.dangerous_home -ne $null) { $hasDanger = $true }

        $rich = 0
        if ($hasAtt) { OK "stats: ataques presentes"; $rich++ } else { BAD "stats: ataques AUSENTES" }
        if ($hasDanger) { OK "stats: ataques perigosos presentes"; $rich++ } else { BAD "stats: ataques perigosos AUSENTES" }
        if ($hasXg) { OK "stats: xG presente"; $rich++ } else { BAD "stats: xG AUSENTE" }
        if ($hasPress) { OK "stats: pressao % presente"; $rich++ } else { WN "stats: pressao % ausente (SokkerPRO as vezes nao mostra)" }
        if ($hasShots) { OK "stats: chutes no gol presentes"; $rich++ } else { WN "stats: chutes no gol ausentes" }
        if ($hasCorners) { OK "stats: escanteios presentes"; $rich++ } else { WN "stats: escanteios ausentes/zerados" }

        if ($rich -lt 2) {
            BAD "PAYLOAD POBRE - so nome/placar nao basta (richScore=$rich/6)"
        } elseif ($rich -lt 4) {
            WN "PAYLOAD PARCIAL richScore=$rich/6 - captura incompleta no DOM"
        } else {
            OK "PAYLOAD RAZOAVEL richScore=$rich/6"
        }

        # template inject detection
        if ($homeN -match "Aldosivi" -and $fid -eq "19764966") {
            BAD "Detectado TEMPLATE de injecao (Aldosivi/19764966) - NAO e captura SokkerPRO"
        }
    }
}

# ---- 3 Bridge /latest API ----
SEC "3. Bridge GET /api/cornerai/latest"
if ($bridgeOk) {
    try {
        $lat = Invoke-RestMethod "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 5
        OK "HTTP 200 em /api/cornerai/latest"
        $v = $null
        if ($lat.view) { $v = $lat.view }
        elseif ($lat.latest -and $lat.latest.view) { $v = $lat.latest.view }
        elseif ($lat.latest) { $v = $lat.latest }
        else { $v = $lat }
        $hn = $v.home; if (-not $hn -and $v.fixture) { $hn = $v.fixture.home }
        $an = $v.away; if (-not $an -and $v.fixture) { $an = $v.fixture.away }
        $fi = $v.fixture_id; if (-not $fi -and $v.fixture) { $fi = $v.fixture.id }
        L "  API view: home=$hn away=$an fixture=$fi" "Gray"
        if ([string]::IsNullOrWhiteSpace([string]$hn)) { WN "API nao expoe home no formato esperado (Engine pode usar outro path)" }
        else { OK "API expoe home=$hn" }
    } catch {
        BAD "/api/cornerai/latest falhou: $($_.Exception.Message)"
    }
}

# ---- 4 Engine ui/state ----
SEC "4. Engine GET /api/ui/state (o que a Matriz consome)"
if ($engineOk) {
    try {
        $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
        OK "ui/state ok=$($ui.ok) jarvis=$($ui.jarvis_state) paper_trade=$($ui.paper_trade)"
        if ($ui.fixtureId) { OK "fixtureId=$($ui.fixtureId)" } else { BAD "fixtureId VAZIO - Matriz sem jogo" }
        if ($ui.home) { OK "home=$($ui.home)" } else { BAD "home VAZIO no ui/state - Matriz mostra so placar/nome incompleto" }
        if ($ui.away) { OK "away=$($ui.away)" } else { BAD "away VAZIO no ui/state" }
        if ($null -ne $ui.minute) { OK "minute=$($ui.minute)" } else { BAD "minute VAZIO/errado no ui/state" }
        if ($ui.capture_stale -eq $true) { BAD "capture_stale=True - Engine considera captura parada" }
        else { OK "capture_stale=$($ui.capture_stale)" }
        # snapshot richness if present
        if ($ui.snapshot) {
            $sv = $ui.snapshot.view
            if ($sv) {
                $keys = ($sv | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name) -join ","
                L "  snapshot.view keys: $keys" "Gray"
            }
        }
    } catch {
        BAD "ui/state falhou: $($_.Exception.Message)"
    }
}

# ---- 5 Capture forwarder / Desktop logs ----
SEC "5. LOGS DE CAPTURA (Desktop)"
$capLog = Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\logs\capture_forwarder.log"
$hostLog = Join-Path $Root "logs_instalacao\desktop_host.log"
if (Test-Path $capLog) {
    OK "capture_forwarder.log existe"
    $tail = Get-Content $capLog -Tail 15 -ErrorAction SilentlyContinue
    foreach ($t in $tail) { L "  | $t" "DarkGray" }
    $blob = ($tail -join "`n")
    if ($blob -match "TOKEN|token vazio|401") { BAD "Possivel problema de token no forwarder" }
    if ($blob -match "drop|DROP|overflow") { WN "Drops no forwarder - fila cheia ou envio falhou" }
    if ($blob -match "AURA_SOKKERPRO_CAPTURE|enqueued|ok") { OK "Sinais de enqueue/capture no log" }
} else {
    WN "capture_forwarder.log nao encontrado em %LOCALAPPDATA%\AURA_QUANT_X\logs\"
    WN "Se nunca existiu: WebView2 pode nao estar a postMessage (captura JS nao corre)"
}
if (Test-Path $hostLog) {
    $ht = Get-Content $hostLog -Tail 8 -ErrorAction SilentlyContinue
    L "  desktop_host.log (tail):" "Gray"
    foreach ($t in $ht) { L "  | $t" "DarkGray" }
}

# ---- 6 Arquivos de captura JS no pacote ----
SEC "6. PIPELINE DE CAPTURA NO PACOTE"
$capJs = Join-Path $Root "desktop\capture\aura-capture.js"
$capJsPub = Join-Path $Root "desktop\capture\aura-capture.js"
$capJsPub2 = Join-Path $Root "desktop\publish\capture\aura-capture.js"
$foundJs = $false
foreach ($p in @($capJs, $capJsPub, $capJsPub2)) {
    if (Test-Path $p) { OK "JS captura: $p"; $foundJs = $true }
}
if (-not $foundJs) { BAD "aura-capture.js NAO encontrado junto do EXE - WebView nao injeta captura" }

# ---- 7 Matriz endpoints ----
SEC "7. MATRIZ / OPERATOR (endpoints)"
$matrixUrls = @(
    "http://127.0.0.1:8765/api/ui/state",
    "http://127.0.0.1:8765/api/health"
)
foreach ($u in $matrixUrls) {
    try {
        $r = Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { OK "$u -> $($r.StatusCode)" }
        else { BAD "$u -> $($r.StatusCode)" }
    } catch { BAD "$u falhou: $($_.Exception.Message)" }
}

# ---- RESUMO ----
SEC "RESUMO E2E"
L ("PASS={0}  FAIL={1}  WARN={2}" -f $pass,$fail,$warn) $(if($fail -eq 0){"Green"}else{"Red"})
L ""
L "LIMITACAO CONHECIDA DO CAPTURADOR ATUAL (aura-capture.js):" "Yellow"
L "  Extrai do TEXTO VISIVEL da pagina SokkerPRO:" "Yellow"
L "  - times, placar, minuto AO VIVO, pressao %, ataques, xG," "Yellow"
L "    chutes no gol, alguns eventos de escanteio." "Yellow"
L "  NAO extrai automaticamente 'milhares de parametros' (H2H completo," "Yellow"
L "  odds profundas, rankings, todas as abas). Isso exige scrapers" "Yellow"
L "  por seletor/aba ou extensao dedicada (market-capture / h2h-capture)." "Yellow"
L ""
L "COMO TER FEED REAL (nao simulado):" "Cyan"
L "  1. SokkerPRO SO na pane DIREITA do Desktop (nunca no Chrome externo)"
L "  2. Abrir fixture com ponto vermelho AO VIVO"
L "  3. Clicar Mesa live + Iniciar na toolbar"
L "  4. Rodape: ok deve subir; latestAgeSec < 15"
L "  5. NAO rode AURA_INJETAR_LATEST_VALIDO (isso e template falso)"
L "  6. Rode este E2E de novo"
L ""
L "Se home/away/stats vazios com jogo aberto:" "Yellow"
L "  - DOM do SokkerPRO mudou e o regex do aura-capture.js nao casa"
L "  - capture_forwarder sem token / ingest URL"
L "  - EXE Desktop desatualizado sem inject do JS"

$lines | Set-Content $Report -Encoding UTF8
L ""
L "Relatorio: $Report" "Cyan"
if ($fail -gt 0) { exit 1 } else { exit 0 }
