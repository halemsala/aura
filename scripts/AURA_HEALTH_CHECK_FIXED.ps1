# AURA HEALTH CHECK V26.2-FIX
param([switch]$Once,[int]$IntervalSec=15,[int]$MaxLoops=0)
$ErrorActionPreference="Continue"
function Try-Json($url){ try{ Invoke-RestMethod -Uri $url -TimeoutSec 4 -ErrorAction Stop } catch { $null } }
function Row($n,$ok,$d){ "{0}  {1,-12} {2}" -f ($(if($ok){"OK  "}else{"FAIL"}),$n,$d) }
function Find-Desktop {
  $names = @("Aura.QuantX.Desktop","Aura.QuantX.Desktop.exe")
  foreach ($n in $names) {
    $p = Get-Process -Name $n -ErrorAction SilentlyContinue
    if ($p) { return $p | Select-Object -First 1 }
  }
  return Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and ($_.Path -match "Aura\.QuantX\.Desktop") } catch { $false }
  } | Select-Object -First 1
}
$loop=0
do {
  $loop++; Write-Host ""; Write-Host ("======== AURA HEALTH V26.2 {0} ========" -f (Get-Date -Format HH:mm:ss)) -ForegroundColor Cyan
  $bridge=Try-Json "http://127.0.0.1:8080/health"
  $engine=Try-Json "http://127.0.0.1:8765/api/health"
  $voice=Try-Json "http://127.0.0.1:8099/api/voice/health"
  $ollama=Try-Json "http://127.0.0.1:11434/api/tags"
  $ui=Try-Json "http://127.0.0.1:8765/api/ui/state"
  $latest=Try-Json "http://127.0.0.1:8080/api/cornerai/latest"
  $bOk=($null -ne $bridge) -and (($bridge.ok -eq $true) -or ($null -ne $bridge.feedLines) -or ($null -ne $bridge.status))
  $eOk=($null -ne $engine)
  $age=$null; $lines=$null
  if ($bridge) { $age=$bridge.latestAgeSec; $lines=$bridge.feedLines }
  $teamHome=$null; $teamAway=$null; $minute=$null; $src=$null
  if ($ui) { $teamHome=$ui.home; $teamAway=$ui.away; $minute=$ui.minute; $src=$ui.source }
  $bh=$null; $ba=$null
  if ($latest -and $latest.latest -and $latest.latest.view) { $bh=$latest.latest.view.home; $ba=$latest.latest.view.away }
  elseif ($latest -and $latest.view) { $bh=$latest.view.home; $ba=$latest.view.away }
  $sync = ($null -ne $teamHome) -and ($null -ne $bh) -and ($teamHome -eq $bh)
  $desk = Find-Desktop
  $deskOk = $null -ne $desk

  Write-Host (Row "Bridge" $bOk "feedLines=$lines ageSec=$age")
  Write-Host (Row "Engine" $eOk "alive")
  Write-Host (Row "Voice" ($null -ne $voice) $(if($voice){"ok"}else{"offline (soft)"}))
  Write-Host (Row "Ollama" ($null -ne $ollama) $(if($ollama){"ok"}else{"offline (soft)"}))
  Write-Host (Row "Desktop" $deskOk $(if($desk){"pid=$($desk.Id) name=$($desk.ProcessName)"}else{"NAO ENCONTRADO"}))
  Write-Host (Row "UI" ($null -ne $teamHome) "$teamHome x $teamAway min=$minute src=$src")
  Write-Host (Row "BridgeGame" ($null -ne $bh) "$bh x $ba")
  Write-Host (Row "SYNC" $sync $(if($sync){"UI==Bridge"}else{"DESSINC ou sem jogo"}))

  if ($bOk -and $eOk -and $deskOk -and $sync) {
    Write-Host "RESULT: SYSTEM READY + SYNC OK" -ForegroundColor Green
  } elseif ($bOk -and $eOk -and $deskOk) {
    Write-Host "RESULT: SERVICES+DESKTOP UP - abra SokkerPRO AO VIVO na pane DIREITA" -ForegroundColor Yellow
  } elseif ($bOk -and $eOk) {
    Write-Host "RESULT: Bridge+Engine UP - abra Desktop (AURA_ABRIR_DESKTOP_SEGURO.bat)" -ForegroundColor Yellow
  } else {
    Write-Host "RESULT: incomplete - suba Bridge/Engine com AURA_SUBIR_*_VISIVEL.bat" -ForegroundColor Red
  }
  if ($Once -or ($MaxLoops -gt 0 -and $loop -ge $MaxLoops)) { break }
  Start-Sleep -Seconds $IntervalSec
} while ($true)
