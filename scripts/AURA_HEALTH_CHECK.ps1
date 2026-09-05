# AURA QUANT-X health check (ASCII-safe, UTF-8 BOM written by packager)
param(
  [switch]$Once,
  [int]$IntervalSec = 15,
  [int]$MaxLoops = 0
)
$ErrorActionPreference = "Continue"
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

function Try-Json([string]$url) {
  try {
    return Invoke-RestMethod -Uri $url -TimeoutSec 3 -ErrorAction Stop
  } catch {
    return $null
  }
}

function Row([string]$name, [bool]$ok, [string]$detail) {
  $mark = if ($ok) { "OK  " } else { "FAIL" }
  return ("{0}  {1,-10} {2}" -f $mark, $name, $detail)
}

$loop = 0
do {
  $loop++
  $ts = Get-Date -Format "HH:mm:ss"
  Write-Host ""
  Write-Host ("======== AURA HEALTH {0} (loop {1}) ========" -f $ts, $loop) -ForegroundColor Cyan

  $bridge = Try-Json "http://127.0.0.1:8080/health"
  $engine = Try-Json "http://127.0.0.1:8765/api/health"
  $voice  = Try-Json "http://127.0.0.1:8099/api/voice/health"
  $ollama = Try-Json "http://127.0.0.1:11434/api/tags"
  $ui     = Try-Json "http://127.0.0.1:8765/api/ui/state"

  $bOk = ($null -ne $bridge) -and ($bridge.ok -eq $true)
  $eOk = ($null -ne $engine) -and (($engine.status -eq "alive") -or ($engine.ok -eq $true))
  $vOk = $null -ne $voice
  $oOk = $null -ne $ollama

  $age = $null
  $lines = 0
  if ($null -ne $bridge) {
    $age = $bridge.latestAgeSec
    $lines = $bridge.feedLines
  }

  $fx = $null
  $src = $null
  $view = $null
  if ($null -ne $ui) {
    $fx = $ui.fixtureId
    $src = $ui.source
    if ($ui.snapshot -and $ui.snapshot.view) { $view = $ui.snapshot.view }
  }

  $home = $null; $away = $null; $min = $null
  if ($null -ne $view) {
    $home = $view.home
    $away = $view.away
    $min = $view.minute
  }

  $feedFresh = ($null -ne $age) -and ([double]$age -lt 20)
  $hasFixture = (-not [string]::IsNullOrWhiteSpace([string]$fx)) -or (-not [string]::IsNullOrWhiteSpace([string]$home))

  Write-Host (Row "Bridge"  ([bool]$bOk) $(if ($bOk) { "feedLines=$lines ageSec=$age" } else { "offline :8080" }))
  Write-Host (Row "Engine"  ([bool]$eOk) $(if ($eOk) { "alive :8765" } else { "offline :8765" }))
  Write-Host (Row "Voice"   ([bool]$vOk) $(if ($vOk) { "ok :8099" } else { "offline/optional :8099" }))
  $mc = 0
  if ($oOk -and $ollama.models) { $mc = @($ollama.models).Count }
  Write-Host (Row "Ollama"  ([bool]$oOk) $(if ($oOk) { "models=$mc" } else { "offline :11434" }))
  Write-Host (Row "Feed"    ([bool]$feedFresh) $(if ($null -eq $age) { "no latest" } elseif ($feedFresh) { "fresh age=$age" } else { "STALE age=$age (open LIVE match)" }))
  Write-Host (Row "Fixture" ([bool]$hasFixture) $(if ($hasFixture) { "id=$fx $home x $away min=$min src=$src" } else { "NO FEED in UI state" }))

  if ($bOk -and $eOk -and $hasFixture -and $feedFresh) {
    Write-Host "RESULT: SYSTEM READY (paper trade)" -ForegroundColor Green
  } else {
    Write-Host "RESULT: incomplete - see FAIL lines above" -ForegroundColor Yellow
  }

  if ($Once) { break }
  if ($MaxLoops -gt 0 -and $loop -ge $MaxLoops) { break }
  Start-Sleep -Seconds $IntervalSec
} while ($true)
