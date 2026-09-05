# AURA QUANT-X - SSE latency monitor for /api/ui/state/stream
param(
  [int]$Seconds = 60,
  [string]$Url = "http://127.0.0.1:8765/api/ui/state/stream"
)
$ErrorActionPreference = "Continue"
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

Write-Host "SSE monitor $Url for ${Seconds}s" -ForegroundColor Cyan
$swAll = [System.Diagnostics.Stopwatch]::StartNew()
$latencies = New-Object System.Collections.Generic.List[double]
$events = 0
$errors = 0
$lastFx = ""

try {
  $req = [System.Net.HttpWebRequest]::Create($Url)
  $req.Method = "GET"
  $req.Accept = "text/event-stream"
  $req.Timeout = ($Seconds + 30) * 1000
  $req.ReadWriteTimeout = ($Seconds + 30) * 1000
  $resp = $req.GetResponse()
  $stream = $resp.GetResponseStream()
  $reader = New-Object System.IO.StreamReader($stream)
  $swEvt = [System.Diagnostics.Stopwatch]::StartNew()

  while ($swAll.Elapsed.TotalSeconds -lt $Seconds) {
    $line = $reader.ReadLine()
    if ($null -eq $line) { break }
    if ($line.StartsWith("data:")) {
      $ms = $swEvt.Elapsed.TotalMilliseconds
      $swEvt.Restart()
      $events++
      [void]$latencies.Add($ms)
      $json = $line.Substring(5).Trim()
      $fx = "?"
      $src = "?"
      try {
        $obj = $json | ConvertFrom-Json
        $fx = [string]$obj.fixtureId
        $src = [string]$obj.source
        $lastFx = $fx
      } catch {}
      Write-Host ("[{0:N0}s] event#{1} gap={2:N0}ms fixture={3} source={4}" -f $swAll.Elapsed.TotalSeconds, $events, $ms, $fx, $src)
    }
  }
  $reader.Close()
  $resp.Close()
} catch {
  $errors++
  Write-Host ("SSE ERROR: " + $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
Write-Host "======== SSE SUMMARY ========" -ForegroundColor Cyan
Write-Host ("events={0} errors={1} lastFixture={2}" -f $events, $errors, $lastFx)
if ($latencies.Count -gt 1) {
  $arr = $latencies | Select-Object -Skip 1
  $avg = ($arr | Measure-Object -Average).Average
  $min = ($arr | Measure-Object -Minimum).Minimum
  $max = ($arr | Measure-Object -Maximum).Maximum
  Write-Host ("gap_ms avg={0:N0} min={1:N0} max={2:N0} (target ~3000ms for 3s stream)" -f $avg, $min, $max)
  if ($avg -gt 5000) {
    Write-Host "WARN: average gap high - Engine slow or blocked" -ForegroundColor Yellow
  } else {
    Write-Host "SSE latency OK" -ForegroundColor Green
  }
} else {
  Write-Host "Not enough events to measure latency"
}
