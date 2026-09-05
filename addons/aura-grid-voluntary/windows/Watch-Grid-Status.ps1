param([string]$StatusFile = "grid_status.json", [double]$Seconds = 3)
Set-Location $PSScriptRoot\..
$env:AURA_GRID_STATUS_FILE = $StatusFile
python scripts\grid_status.py --watch $Seconds
