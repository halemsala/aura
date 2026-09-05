# AURA QUANT-X — BATERIA E2E TOTAL V26.1 (encoding-safe sync + chat timeout)
param(
  [int]$Seconds = 90,
  [int]$IntervalSec = 5,
  [switch]$WriteFeedback
)

$ErrorActionPreference = "Continue"
$Root = if (Test-Path ".\engine\server.py") { (Resolve-Path ".").Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
Set-Location $Root
$env:PYTHONPATH = $Root

$logDir = Join-Path $Root "logs_supervisor"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$report = Join-Path $logDir ("AUTO_TEST_E2E_" + $ts + ".txt")
$feedbackPath = Join-Path $Root "engine\data\system_health_feedback.json"
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$okCount = 0
$failCount = 0
$layerResults = @{}

function W([string]$msg, [string]$color = "White") {
  Write-Host $msg -ForegroundColor $color
  Add-Content -Path $report -Value $msg -Encoding UTF8
}
function Ok($msg) { $script:okCount++; W ("[OK]  " + $msg) "Green" }
function Fail($msg) { $script:failCount++; $errors.Add($msg); W ("[ERR] " + $msg) "Red" }
function Warn($msg) { $warnings.Add($msg); W ("[!!]  " + $msg) "Yellow" }
function Info($msg) { W ("[..]  " + $msg) "Cyan" }
function Layer($name, $ok, $detail, [switch]$Soft) {
  $layerResults[$name] = @{ ok = [bool]$ok; detail = $detail }
  if ($ok) { Ok ($name + " : " + $detail) }
  elseif ($Soft) { Warn ($name + " : " + $detail) }
  else { Fail ($name + " : " + $detail) }
}

function Try-Json([string]$url, [int]$timeout = 4) {
  try {
    return Invoke-RestMethod -Uri $url -TimeoutSec $timeout -ErrorAction Stop
  } catch { return $null }
}

function Try-PostJson([string]$url, $body, [int]$timeout = 25) {
  try {
    $json = $body | ConvertTo-Json -Depth 6 -Compress
    return Invoke-RestMethod -Uri $url -Method POST -Body $json -ContentType "application/json; charset=utf-8" -TimeoutSec $timeout -ErrorAction Stop
  } catch { return $null }
}

function Norm-Team([string]$s) {
  if (-not $s) { return "" }
  $t = $s.Trim().ToLowerInvariant()
  # undo common UTF-8-as-Latin1 mojibake for comparison
  $t = $t -replace "ä", "g" -replace "ã§", "c" -replace "Ã§", "c"
  $t = $t -replace "á", "a" -replace "é", "e" -replace "í", "i" -replace "ó", "o" -replace "ú", "u"
  $t = $t -replace "ã", "a" -replace "õ", "o" -replace "ç", "c" -replace "ñ", "n"
  $t = $t -replace "ğ", "g" -replace "ş", "s" -replace "ı", "i" -replace "ü", "u" -replace "ö", "o"
  $t = $t -replace "[^a-z0-9 ]", ""
  return ($t -replace "\s+", " ").Trim()
}

function Teams-Match($a, $b) {
  $na = Norm-Team ([string]$a)
  $nb = Norm-Team ([string]$b)
  if (-not $na -or -not $nb) { return $false }
  if ($na -eq $nb) { return $true }
  if ($na.Contains($nb) -or $nb.Contains($na)) { return $true }
  return $false
}

function Save-Feedback([hashtable]$payload) {
  try {
    $dir = Split-Path $feedbackPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Path $feedbackPath -Encoding UTF8
    $jsonl = Join-Path $dir "system_health_feedback.jsonl"
    Add-Content -Path $jsonl -Value ($payload | ConvertTo-Json -Depth 10 -Compress) -Encoding UTF8
  } catch {
    Warn ("Nao gravou feedback: " + $_.Exception.Message)
  }
}

W "============================================================"
W " AURA BATERIA E2E TOTAL + FEEDBACK IA  V26.1"
W (" Inicio: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
W (" Root:   " + $Root)
W (" Duracao monitor: " + $Seconds + " s | Intervalo: " + $IntervalSec + " s")
W (" Relatorio: " + $report)
W "============================================================"
W ""

# ========== 1 PROCESSOS / PORTAS ==========
Info "CAMADA 1) Processos e portas"
$procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "python|Aura|ollama|node" }
if ($procs) {
  Layer "Processos" $true ("count=" + $procs.Count + " names=" + (($procs.ProcessName | Select-Object -Unique) -join ","))
} else {
  Layer "Processos" $false "Nenhum processo AURA/Python/Ollama/Node"
}

$portMap = @{ 8080 = "Bridge"; 8765 = "Engine"; 8099 = "Voice"; 11434 = "Ollama"; 3000 = "Dashboard" }
foreach ($p in @(8080, 8765, 8099, 11434, 3000)) {
  $c = $null
  try { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 } catch {}
  $label = $portMap[$p]
  if ($c) { Layer ("Porta_" + $p) $true ($label + " LISTEN") }
  else {
    if ($p -eq 3000 -or $p -eq 8099) {
      Layer ("Porta_" + $p) $false ($label + " OFF") -Soft
    } else {
      Layer ("Porta_" + $p) $false ($label + " OFF")
    }
  }
}

# ========== 2 HEALTH ==========
Info "CAMADA 2) Health Bridge / Engine / Voice / Ollama / Deep"
$bridge = Try-Json "http://127.0.0.1:8080/health"
$engine = Try-Json "http://127.0.0.1:8765/api/health"
$voice  = Try-Json "http://127.0.0.1:8099/api/voice/health"
$ollama = Try-Json "http://127.0.0.1:11434/api/tags"
$deep   = Try-Json "http://127.0.0.1:8765/api/diagnostics/deep" 6

$bridgeOk = ($null -ne $bridge) -and (($bridge.ok -eq $true) -or ($null -ne $bridge.status) -or ($null -ne $bridge.feedLines))
if ($bridgeOk) {
  Layer "Bridge" $true ("feedLines=" + $bridge.feedLines + " ageSec=" + $bridge.latestAgeSec + " ok=" + $bridge.ok)
} else { Layer "Bridge" $false "offline ou sem resposta" }

if ($engine) { Layer "Engine" $true "alive" } else { Layer "Engine" $false "offline" }
if ($voice)  { Layer "Voice"  $true "ok" } else { Layer "Voice"  $false "offline (nao bloqueia paper)" -Soft }
if ($ollama) {
  $models = @()
  if ($ollama.models) { $models = $ollama.models | ForEach-Object { $_.name } }
  Layer "Ollama" $true ("models=" + ($models -join ", "))
} else { Layer "Ollama" $false "offline" }

if ($deep) { Layer "DiagnosticsDeep" $true "endpoint responde" } else { Warn "api/diagnostics/deep sem resposta" }

# ========== 3 IA ==========
Info "CAMADA 3) AURA IA One + Hermes"
$venvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
if (Test-Path (Join-Path $Root "engine\aura_ai_one\adapter.py")) { Ok "aura_ai_one/adapter.py presente" } else { Fail "FALTA aura_ai_one/adapter.py" }
if (Test-Path (Join-Path $Root "engine\agents\aura_hermes_router.py")) { Ok "aura_hermes_router.py presente" } else { Fail "FALTA aura_hermes_router.py" }

if (Test-Path $venvPy) {
  try {
    $out = & $venvPy -c "from engine.agents.aura_hermes_router import route_corner_analysis; print('AURA_IA_OK')" 2>&1
    if ("$out" -match "AURA_IA_OK") { Layer "IA_Import" $true "Hermes import OK" }
    else { Layer "IA_Import" $false ("import falhou: " + $out) }
  } catch { Layer "IA_Import" $false $_.Exception.Message }
} else { Warn "venv Python ausente - pule import IA" }

if ($engine) {
  Info "Chat smoke (timeout 30s)..."
  $chatResp = Try-PostJson "http://127.0.0.1:8765/api/trader/chat" @{ message = "OK breve"; fixtureId = "" } 30
  if ($chatResp) {
    Layer "ChatIA" $true "resposta recebida"
  } else {
    # try glm_chat as alternate
    $chat2 = Try-PostJson "http://127.0.0.1:8765/api/glm_chat" @{ message = "OK breve" } 30
    if ($chat2) { Layer "ChatIA" $true "glm_chat OK" }
    else { Layer "ChatIA" $false "chat sem resposta em 30s (GLM pode estar lento)" -Soft }
  }
} else { Warn "Engine offline - chat nao testado" }

# ========== 4 MONITOR ==========
Info ("CAMADA 4) Monitoramento " + $Seconds + " s (feed / sync / stats ricas)")
$feedOk = 0; $syncOk = 0; $richOk = 0; $samples = 0
$minAge = 9999; $maxAge = -1
$lastBridge = ""; $lastUi = ""
$endAt = (Get-Date).AddSeconds($Seconds)

while ((Get-Date) -lt $endAt) {
  $samples++
  $b = Try-Json "http://127.0.0.1:8080/health"
  $latest = Try-Json "http://127.0.0.1:8080/api/cornerai/latest"
  $ui = Try-Json "http://127.0.0.1:8765/api/ui/state"

  $age = $null
  if ($b -and $null -ne $b.latestAgeSec) { $age = [double]$b.latestAgeSec }
  if ($null -ne $age) {
    if ($age -lt $minAge) { $minAge = $age }
    if ($age -gt $maxAge) { $maxAge = $age }
    if ($age -lt 20) { $feedOk++ }
  }

  $view = $null
  if ($latest -and $latest.latest -and $latest.latest.view) { $view = $latest.latest.view }
  elseif ($latest -and $latest.view) { $view = $latest.view }
  elseif ($ui -and $ui.snapshot -and $ui.snapshot.view) { $view = $ui.snapshot.view }

  $bh = $null; $ba = $null; $bm = $null
  if ($view) {
    $bh = $view.home; $ba = $view.away; $bm = $view.minute
    $lastBridge = "$bh x $ba min=$bm"
    $hasAttacks = ($null -ne $view.attacks_home) -or ($null -ne $view.attacks_away)
    $hasXg = ($null -ne $view.xg_home) -or ($null -ne $view.xg_away)
    $hasCorners = ($null -ne $view.corners_home) -or ($null -ne $view.corners_away) -or ($null -ne $view.corner_events)
    if ($hasAttacks -or $hasXg -or $hasCorners) { $richOk++ }
  }

  $uh = $null; $ua = $null; $um = $null; $src = $null
  if ($ui) {
    $uh = $ui.home; $ua = $ui.away; $um = $ui.minute; $src = $ui.source
    if (-not $uh -and $ui.snapshot) {
      if ($ui.snapshot.view) {
        $uh = $ui.snapshot.view.home; $ua = $ui.snapshot.view.away; $um = $ui.snapshot.view.minute
      }
      if (-not $uh) { $uh = $ui.snapshot.home; $ua = $ui.snapshot.away }
    }
    $lastUi = "$uh x $ua min=$um src=$src"
  }

  $synced = $false
  if ($bh -and $uh -and (Teams-Match $bh $uh) -and (Teams-Match $ba $ua)) { $synced = $true }
  elseif ($bm -ne $null -and $um -ne $null -and ([string]$bm -eq [string]$um) -and $ba -and $ua -and (Teams-Match $ba $ua)) { $synced = $true }
  if ($synced) { $syncOk++ }

  $syncLabel = if ($synced) { "YES" } else { "NO" }
  W ("t=$samples age=$age bridge=[$lastBridge] ui=[$lastUi] sync=$syncLabel")
  Start-Sleep -Seconds $IntervalSec
}

W ""
Info "CAMADA 5) Resultado do monitoramento"
$feedPct = 0; $syncPct = 0; $richPct = 0
if ($samples -gt 0) {
  $feedPct = [math]::Round(100.0 * $feedOk / $samples, 1)
  $syncPct = [math]::Round(100.0 * $syncOk / $samples, 1)
  $richPct = [math]::Round(100.0 * $richOk / $samples, 1)
  W ("Amostras: " + $samples)
  W ("Feed fresco (<20s): $feedOk/$samples ($feedPct%) | age min=$minAge max=$maxAge")
  W ("Sync UI==Bridge:   $syncOk/$samples ($syncPct%)")
  W ("Stats ricas:       $richOk/$samples ($richPct%)")
  W ("Ultimo Bridge: $lastBridge")
  W ("Ultimo UI:     $lastUi")
  Layer "FeedFresco" ($feedPct -ge 50) ($feedPct.ToString() + "% fresco")
  Layer "SyncUIBridge" ($syncPct -ge 50) ($syncPct.ToString() + "% sync")
  Layer "CapturaRica" ($richPct -ge 30) ($richPct.ToString() + "% com atk/xg/corners")
} else {
  Layer "Monitor" $false "Nenhuma amostra coletada"
}

# ========== 6 DESKTOP ==========
Info "CAMADA 6) Desktop"
$desk = Get-Process -Name "Aura.QuantX.Desktop" -ErrorAction SilentlyContinue
if ($desk) { Layer "Desktop" $true ("PID=" + $desk.Id) } else { Layer "Desktop" $false "NAO esta aberto" -Soft }

# ========== 7 UI STATE fresh ==========
Info "CAMADA 7) UI state / fixture context (fresh)"
$uiState = Try-Json "http://127.0.0.1:8765/api/ui/state"
if ($uiState) {
  $h = $uiState.home; $a = $uiState.away
  if (-not $h -and $uiState.snapshot -and $uiState.snapshot.view) {
    $h = $uiState.snapshot.view.home; $a = $uiState.snapshot.view.away
  }
  if (-not $h -and $uiState.snapshot) { $h = $uiState.snapshot.home; $a = $uiState.snapshot.away }
  $hasHome = [bool]$h
  Layer "UIState" $hasHome ("home=$h away=$a source=$($uiState.source)")
} else {
  Layer "UIState" $false "api/ui/state sem dados"
}

# ========== RESUMO ==========
W ""
W "============================================================"
W " RESUMO FINAL POR CAMADA"
W (" OK=$okCount  ERR=$failCount  WARN=" + $warnings.Count)
W "============================================================"
foreach ($k in ($layerResults.Keys | Sort-Object)) {
  $r = $layerResults[$k]
  $mark = if ($r.ok) { "OK  " } else { "FAIL" }
  W ("  [" + $mark + "] " + $k.PadRight(18) + " " + $r.detail)
}
if ($errors.Count -gt 0) {
  W ""
  W "ERROS ENCONTRADOS:" "Red"
  foreach ($e in $errors) { W (" - " + $e) "Red" }
}
if ($warnings.Count -gt 0) {
  W ""
  W "AVISOS:" "Yellow"
  foreach ($w in $warnings) { W (" - " + $w) "Yellow" }
}

# Status: CRITICAL only if Bridge or Engine down
$coreDown = $false
if ($layerResults.ContainsKey("Bridge") -and -not $layerResults["Bridge"].ok) { $coreDown = $true }
if ($layerResults.ContainsKey("Engine") -and -not $layerResults["Engine"].ok) { $coreDown = $true }
$status = if ($coreDown) { "CRITICAL" } elseif ($failCount -eq 0) { "HEALTHY" } else { "DEGRADED" }

if ($WriteFeedback) {
  Info "Gravando feedback para AURA IA..."
  $payload = @{
    version = "26.1-E2E"
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    status = $status
    ok_count = $okCount
    fail_count = $failCount
    warn_count = $warnings.Count
    layers = $layerResults
    errors = @($errors)
    warnings = @($warnings)
    metrics = @{
      samples = $samples
      feed_fresh_pct = $feedPct
      sync_pct = $syncPct
      rich_pct = $richPct
      last_bridge = $lastBridge
      last_ui = $lastUi
    }
    report_path = $report
    message_for_ia = ("Sistema $status. Feed=$feedPct% Sync=$syncPct% Rica=$richPct%. Erros hard=$failCount.")
  }
  Save-Feedback $payload
  Ok ("Feedback gravado em " + $feedbackPath)
}

W ""
W ("Relatorio: " + $report)
W ("Fim: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
W ("Status global: " + $status)
try { Start-Process notepad.exe $report } catch {}
if ($coreDown) { exit 1 } else { exit 0 }
