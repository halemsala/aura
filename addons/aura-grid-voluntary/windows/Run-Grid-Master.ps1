# Opt-in only. Requires AURA_GRID_TOKEN set by the operator.
if (-not $env:AURA_GRID_TOKEN) { Write-Error "Set AURA_GRID_TOKEN first"; exit 1 }
$env:AURA_GRID_BIND = if ($env:AURA_GRID_BIND) { $env:AURA_GRID_BIND } else { "127.0.0.1" }
Set-Location $PSScriptRoot\..
python scriptsun_master.py
