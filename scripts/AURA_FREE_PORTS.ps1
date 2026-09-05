# Free AURA ports 8080 / 8765 / 8099 / 9102 (no second instance)
param([int[]]$Ports = @(8080, 8765, 8099, 9102))
$ErrorActionPreference = "Continue"
foreach ($port in $Ports) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      $pid = $c.OwningProcess
      if ($pid -and $pid -gt 0) {
        $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
        Write-Host ("[PORT] kill PID {0} ({1}) on :{2}" -f $pid, $(if($p){$p.ProcessName}else{"?"}), $port)
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    # fallback netstat
    $lines = netstat -ano | Select-String (":$port\s+.*LISTENING")
    foreach ($line in $lines) {
      $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }
      $opid = $parts[-1]
      if ($opid -match '^\d+$' -and [int]$opid -gt 0) {
        Write-Host ("[PORT] kill PID {0} on :{1}" -f $opid, $port)
        taskkill /F /PID $opid 2>$null | Out-Null
      }
    }
  }
}
Start-Sleep -Seconds 1
Write-Host "[PORT] done"
