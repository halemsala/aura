Write-Host "Parando AURA Local AIOps..." -ForegroundColor Yellow

# Para processos Python do orchestrator e callback
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match "local_orchestrator|callback_server"
} | ForEach-Object {
    Write-Host "  Matando PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Para Neo4j
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
docker compose down 2>$null
docker-compose down 2>$null

Write-Host "Tudo parado." -ForegroundColor Green
