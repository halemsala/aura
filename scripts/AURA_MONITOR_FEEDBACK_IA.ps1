# AURA QUANT-X — MONITOR CONTINUO + FEEDBACK PARA IA  V26.2-FIX
# Grava periodicamente engine/data/system_health_feedback.json
# Correções:
#  - Detecção de Desktop mais robusta (vários nomes de processo + caminho EXE)
#  - Ollama é soft (não conta como erro crítico)
#  - Bridge age vazio não força erro se Bridge responde
#  - Mensagens mais claras para a IA
param(
  [int]$IntervalSec = 10,
  [int]$MaxLoops = 0
)

$ErrorActionPreference = "Continue"
$Root = if (Test-Path ".\engine\server.py") { (Resolve-Path ".").Path } else { $PSScriptRoot + "\.." }
Set-Location $Root

$feedbackPath = Join-Path $Root "engine\data\system_health_feedback.json"
$jsonlPath    = Join-Path $Root "engine\data\system_health_feedback.jsonl"
$logDir = Join-Path $Root "logs_supervisor"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Try-Json([string]$url, [int]$timeout = 3) {
  try { return Invoke-RestMethod -Uri $url -TimeoutSec $timeout -ErrorAction Stop }
  catch { return $null }
}

function Write-Feedback($obj) {
  $dir = Split-Path $feedbackPath -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $obj | ConvertTo-Json -Depth 10 | Set-Content -Path $feedbackPath -Encoding UTF8
  Add-Content -Path $jsonlPath -Value ($obj | ConvertTo-Json -Depth 10 -Compress) -Encoding UTF8
}

function Find-DesktopProcess {
  # Vários nomes possíveis do processo Desktop
  $names = @(
    "Aura.QuantX.Desktop",
    "Aura.QuantX.Desktop.exe",
    "AuraQuantXDesktop"
  )
  foreach ($n in $names) {
    $p = Get-Process -Name $n -ErrorAction SilentlyContinue
    if ($p) { return $p | Select-Object -First 1 }
  }
  # Fallback: qualquer processo cujo Path contenha Aura.QuantX.Desktop
  $all = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try {
      $path = $_.Path
      if ($path -and ($path -match "Aura\.QuantX\.Desktop")) { return $true }
    } catch {}
    $false
  }
  if ($all) { return $all | Select-Object -First 1 }
  return $null
}

$loop = 0
Write-Host "Monitor continuo V26.2-FIX iniciado. Feedback -> $feedbackPath" -ForegroundColor Cyan
Write-Host "Intervalo ${IntervalSec}s. Ctrl+C para parar." -ForegroundColor Cyan

while ($true) {
  $loop++
  $ts = Get-Date
  $errors = New-Object System.Collections.Generic.List[string]
  $okList = New-Object System.Collections.Generic.List[string]
  $layers = @{}

  $bridge = Try-Json "http://127.0.0.1:8080/health"
  $engine = Try-Json "http://127.0.0.1:8765/api/health"
  $voice  = Try-Json "http://127.0.0.1:8099/api/voice/health"
  $ollama = Try-Json "http://127.0.0.1:11434/api/tags"
  $ui     = Try-Json "http://127.0.0.1:8765/api/ui/state"
  $latest = Try-Json "http://127.0.0.1:8080/api/cornerai/latest"

  $bridgeOk = ($null -ne $bridge) -and (($bridge.ok -eq $true) -or ($null -ne $bridge.feedLines) -or ($null -ne $bridge.status))
  if ($bridgeOk) { $okList.Add("Bridge"); $layers.Bridge = @{ ok = $true; age = $bridge.latestAgeSec; feedLines = $bridge.feedLines } }
  else { $errors.Add("Bridge offline"); $layers.Bridge = @{ ok = $false } }

  if ($engine) { $okList.Add("Engine"); $layers.Engine = @{ ok = $true } }
  else { $errors.Add("Engine offline"); $layers.Engine = @{ ok = $false } }

  if ($voice) { $okList.Add("Voice"); $layers.Voice = @{ ok = $true } }
  else { $layers.Voice = @{ ok = $false } }  # nao critico

  # Ollama = soft (nao conta como erro critico)
  if ($ollama) { $okList.Add("Ollama"); $layers.Ollama = @{ ok = $true } }
  else { $layers.Ollama = @{ ok = $false } }

  $view = $null
  if ($latest -and $latest.latest -and $latest.latest.view) { $view = $latest.latest.view }
  elseif ($latest -and $latest.view) { $view = $latest.view }

  $bh = $null; $ba = $null; $bm = $null
  $rich = $false
  if ($view) {
    $bh = $view.home; $ba = $view.away; $bm = $view.minute
    $rich = ($null -ne $view.attacks_home) -or ($null -ne $view.xg_home) -or ($null -ne $view.corner_events) -or ($null -ne $view.corners_home)
  }

  $uh = $null; $ua = $null; $um = $null; $src = $null
  if ($ui) {
    $uh = $ui.home; $ua = $ui.away; $um = $ui.minute; $src = $ui.source
    if (-not $uh -and $ui.snapshot -and $ui.snapshot.view) {
      $uh = $ui.snapshot.view.home; $ua = $ui.snapshot.view.away; $um = $ui.snapshot.view.minute
    }
  }

  $sync = ($bh -and $uh -and ($bh -eq $uh) -and ($ba -eq $ua))
  if ($sync) { $okList.Add("Sync") }
  elseif ($bh -or $uh) {
    # dessincronizacao nao e erro critico se Bridge e Engine estao up
    # apenas aviso
  }

  $age = if ($bridge -and $null -ne $bridge.latestAgeSec) { [double]$bridge.latestAgeSec } else { $null }
  $feedFresh = ($null -ne $age) -and ($age -lt 20)
  if ($feedFresh) { $okList.Add("FeedFresh") }

  $desk = Find-DesktopProcess
  $deskOk = $null -ne $desk
  if ($deskOk) { $okList.Add("Desktop") }
  else { $errors.Add("Desktop fechado - abra com AURA_ABRIR_DESKTOP_SEGURO.bat") }

  # Status: so Bridge/Engine/Desktop contam como erros criticos
  $status = if ($errors.Count -eq 0) { "HEALTHY" } elseif ($errors.Count -le 2) { "DEGRADED" } else { "CRITICAL" }

  # Se Bridge+Engine OK mas sem feed/sync, status informativo
  if ($bridgeOk -and $engine -and -not $feedFresh -and -not $sync) {
    if ($status -eq "HEALTHY") { $status = "DEGRADED" }
  }

  $payload = @{
    version     = "26.2-MONITOR-FIX"
    timestamp   = $ts.ToUniversalTime().ToString("o")
    loop        = $loop
    status      = $status
    ok          = @($okList)
    errors      = @($errors)
    layers      = $layers
    metrics     = @{
      feed_age_sec   = $age
      feed_fresh     = $feedFresh
      sync           = $sync
      rich_stats     = $rich
      bridge_game    = $(if ($bh) { "$bh x $ba min=$bm" } else { $null })
      ui_game        = $(if ($uh) { "$uh x $ua min=$um src=$src" } else { $null })
      desktop_pid    = $(if ($desk) { $desk.Id } else { $null })
      desktop_name   = $(if ($desk) { $desk.ProcessName } else { $null })
    }
    message_for_ia = "Status $status. OK=[$($okList -join ', ')]. Erros=[$($errors -join '; ')]. Sem feed/sync = abra SokkerPRO AO VIVO na pane DIREITA do Desktop. Use isso para diagnosticar."
  }

  Write-Feedback $payload

  $color = switch ($status) { "HEALTHY" { "Green" } "DEGRADED" { "Yellow" } default { "Red" } }
  Write-Host ("[{0}] {1} | age={2} sync={3} rich={4} desk={5} errs={6}" -f `
    $ts.ToString("HH:mm:ss"), $status, $age, $sync, $rich, $deskOk, $errors.Count) -ForegroundColor $color

  if ($MaxLoops -gt 0 -and $loop -ge $MaxLoops) { break }
  Start-Sleep -Seconds $IntervalSec
}
