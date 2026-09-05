# AURA_SAFE_FREE_PORTS.ps1
# Libera so portas AURA. Nao mata Ollama :11434. Nao mata Python alheio.
param(
  [int[]]$Ports = @(8080,8765,8099,8766,9101,5173,8790),
  [switch]$IncludeWebViewCache
)
$ErrorActionPreference = 'SilentlyContinue'
$auraPorts = $Ports | Where-Object { $_ -ne 11434 }
Write-Host "[SAFE_FREE] portas AURA: $($auraPorts -join ', ')"
foreach ($p in $auraPorts) {
  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $procId = $_.OwningProcess
    if ($procId -le 4) { return }
    try {
      $proc = Get-Process -Id $procId -ErrorAction Stop
      $path = [string]$proc.Path
      $name = [string]$proc.ProcessName
      $isAura = ($path -match '(?i)\\aura|\\engine\\venv|hermes_v10|Aura\.QuantX') -or ($name -match '(?i)^Aura')
      if ($isAura -or $name -match '(?i)^(python|pythonw|py)$') {
        Write-Host ("  stop PID {0} {1} :{2}" -f $procId, $name, $p)
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
      } else {
        Write-Host ("  SKIP PID {0} {1} :{2} (nao AURA)" -f $procId, $name, $p)
      }
    } catch {}
  }
}
Get-Process Aura.QuantX.Desktop, Aura* -ErrorAction SilentlyContinue | ForEach-Object {
  if ($_.ProcessName -match '(?i)Aura') {
    Write-Host ("  stop desktop {0}" -f $_.Id)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
  }
}
if ($IncludeWebViewCache) {
  $wv = Join-Path $env:LOCALAPPDATA 'AURA_QUANT_X\desktop_data'
  if (Test-Path $wv) {
    Remove-Item -Recurse -Force $wv -ErrorAction SilentlyContinue
    Write-Host '  cache WebView2 limpo'
  }
}
Write-Host '[SAFE_FREE] OK'
