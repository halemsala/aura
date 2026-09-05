if (-not $env:AURA_GRID_TOKEN) { Write-Error "Set AURA_GRID_TOKEN first"; exit 1 }
if (-not $env:AURA_GRID_MASTER_HOST) { Write-Error "Set AURA_GRID_MASTER_HOST first"; exit 1 }
Set-Location $PSScriptRoot\..
python scriptsun_worker.py
