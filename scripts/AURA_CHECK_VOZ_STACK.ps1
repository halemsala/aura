$ErrorActionPreference = 'Continue'
foreach ($p in 8080, 8765, 8099, 11434) {
  try {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop
    if ($c) { Write-Host "PORTA $p : LISTEN" } else { Write-Host "PORTA $p : FECHADA" }
  } catch {
    Write-Host "PORTA $p : FECHADA"
  }
}
try {
  $h = Invoke-RestMethod http://127.0.0.1:8099/api/voice/health -TimeoutSec 5
  Write-Host ("VOICE: status={0} engineReady={1} error={2}" -f $h.status, $h.engineReady, $h.error)
} catch {
  Write-Host "VOICE: FALHOU"
}
try {
  Invoke-RestMethod http://127.0.0.1:8765/api/health -TimeoutSec 5 | Out-Null
  Write-Host "ENGINE: OK"
} catch {
  Write-Host "ENGINE: FALHOU ou ausente"
}
try {
  Invoke-RestMethod http://127.0.0.1:8080/health -TimeoutSec 5 | Out-Null
  Write-Host "BRIDGE: OK"
} catch {
  Write-Host "BRIDGE: FALHOU ou ausente"
}
