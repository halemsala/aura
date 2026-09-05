# AURA — Preparar e executar no Windows PowerShell
# Execute o PowerShell como Administrador.
# Este script não cola nem executa HTTPConnection; usa somente comandos válidos do PowerShell.

$ErrorActionPreference = 'Stop'
$AURA = 'C:\aura\scripts'
$Repair = Join-Path $AURA 'AURA_REPARAR_OLLAMA.py'
$Harness = Join-Path $AURA 'AURA_HARNESS_CORE.py'
$Bat = Join-Path $AURA 'AURA_REPARAR_OLLAMA.bat'
$BackupRoot = Join-Path $AURA ('backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))

Write-Host '=== AURA / Ollama — validação e execução ===' -ForegroundColor Cyan

if (-not (Test-Path $AURA)) {
    New-Item -ItemType Directory -Path $AURA -Force | Out-Null
}

Write-Host "Pasta: $AURA"
Write-Host 'Arquivos encontrados:' -ForegroundColor Yellow
Get-ChildItem -Path $AURA -Filter 'AURA_*' -File -ErrorAction SilentlyContinue |
    Select-Object Name, Length, LastWriteTime |
    Format-Table -AutoSize

if (-not (Test-Path $Repair)) {
    throw "Arquivo obrigatório ausente: $Repair. Confirme que AURA_REPARAR_OLLAMA.py está em C:\aura\scripts e execute novamente."
}

# Backup reversível antes de qualquer ação posterior.
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
Copy-Item -Path $Repair -Destination $BackupRoot -Force
if (Test-Path $Harness) { Copy-Item -Path $Harness -Destination $BackupRoot -Force }
if (Test-Path $Bat) { Copy-Item -Path $Bat -Destination $BackupRoot -Force }
Write-Host "Backup criado em: $BackupRoot" -ForegroundColor Green

# Confirma Python e valida sintaxe sem iniciar o harness.
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    throw 'Python não foi encontrado no PATH.'
}

Write-Host 'Validando sintaxe Python...' -ForegroundColor Yellow
& $Python.Source -m py_compile $Repair
if (Test-Path $Harness) { & $Python.Source -m py_compile $Harness }
Write-Host 'Sintaxe OK.' -ForegroundColor Green

# Teste direto de loopback: não usa DNS, proxy ou urlopen.
Write-Host 'Testando TCP 127.0.0.1:11434...' -ForegroundColor Yellow
$Tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 11434 -InformationLevel Quiet
if (-not $Tcp) {
    Write-Host 'Ollama não está à escuta em 127.0.0.1:11434.' -ForegroundColor Red
    Write-Host 'Abra o Ollama ou execute "ollama serve" em outro terminal; depois rode este script novamente.' -ForegroundColor Yellow
    exit 2
}
Write-Host 'TCP OK — Ollama está acessível.' -ForegroundColor Green

# Desativa proxies apenas para este processo filho e preserva o restante do sistema.
$env:NO_PROXY = '127.0.0.1,localhost'
$env:no_proxy = '127.0.0.1,localhost'

$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($Ollama) {
    Write-Host 'Modelos instalados no Ollama:' -ForegroundColor Yellow
    & $Ollama.Source list
} else {
    Write-Host 'Aviso: comando ollama não está no PATH; o serviço TCP respondeu, então a execução poderá continuar.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Executando reparo AURA...' -ForegroundColor Cyan
Set-Location $AURA
& $Python.Source $Repair
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    Write-Host "O reparo terminou com código $ExitCode." -ForegroundColor Red
    exit $ExitCode
}

Write-Host 'Reparo concluído com sucesso.' -ForegroundColor Green
Write-Host 'Para executar o harness completo manualmente:' -ForegroundColor Yellow
Write-Host '  python C:\aura\scripts\AURA_HARNESS_CORE.py'
Write-Host 'Ou, se o harness aceitar o parâmetro:' -ForegroundColor Yellow
Write-Host '  python C:\aura\scripts\AURA_HARNESS_CORE.py --reparar'
Write-Host 'Métricas, quando o harness estiver ativo: http://127.0.0.1:8000/metrics'
