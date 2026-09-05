# AURA_MONITOR.ps1
# AURA Live Monitor Pro — somente leitura.
# Versão corrigida: estrutura PowerShell expandida para evitar erros de parser.

$ErrorActionPreference = 'SilentlyContinue'

$Root = 'C:\aura'
$Runtime = Join-Path $Root 'halem_control\runtime'
$AuditLog = Join-Path $Root 'halem_control\audit.jsonl'

$Services = @(
    @{ Name = 'OLLAMA'; Port = 11434; Url = 'http://127.0.0.1:11434/api/tags' },
    @{ Name = 'ENGINE'; Port = 8765;  Url = 'http://127.0.0.1:8765/api/health' },
    @{ Name = 'BRIDGE'; Port = 8080;  Url = 'http://127.0.0.1:8080/health' },
    @{ Name = 'VOICE';  Port = 8099;  Url = 'http://127.0.0.1:8099/api/health' }
)

function Test-PortOk {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $client = $null

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(700, $false)

        if (-not $connected) {
            return $false
        }

        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $client) {
            $client.Dispose()
        }
    }
}

function Test-HttpHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    $watch = [System.Diagnostics.Stopwatch]::StartNew()

    try {
        $response = Invoke-WebRequest `
            -Uri $Url `
            -Method Get `
            -TimeoutSec 2 `
            -UseBasicParsing

        $watch.Stop()

        return @{
            Online = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
            LatencyMs = $watch.ElapsedMilliseconds
            Status = [int]$response.StatusCode
        }
    }
    catch {
        $watch.Stop()

        return @{
            Online = $false
            LatencyMs = $watch.ElapsedMilliseconds
            Status = 0
        }
    }
}

while ($true) {
    Clear-Host

    Write-Host 'AURA LIVE MONITOR PRO' -ForegroundColor Cyan
    Write-Host ('Atualizado: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor DarkGray
    Write-Host ''

    Write-Host 'SERVIÇOS' -ForegroundColor Yellow

    foreach ($Service in $Services) {
        $tcpOnline = Test-PortOk -Port $Service.Port

        if ($tcpOnline) {
            $health = Test-HttpHealth -Url $Service.Url

            if ($health.Online) {
                Write-Host (
                    '  {0,-7} :{1,-5} ONLINE  HTTP {2}  {3} ms' -f
                    $Service.Name,
                    $Service.Port,
                    $health.Status,
                    $health.LatencyMs
                ) -ForegroundColor Green
            }
            else {
                Write-Host (
                    '  {0,-7} :{1,-5} TCP ONLINE / HTTP SEM RESPOSTA' -f
                    $Service.Name,
                    $Service.Port
                ) -ForegroundColor Yellow
            }
        }
        else {
            Write-Host (
                '  {0,-7} :{1,-5} OFFLINE' -f
                $Service.Name,
                $Service.Port
            ) -ForegroundColor Red
        }
    }

    Write-Host ''
    Write-Host 'PROCESSOS AURA / IA' -ForegroundColor Yellow

    $processes = Get-Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessName -match '(?i)python|aura|electron|node|ollama'
        } |
        Select-Object `
            Id,
            ProcessName,
            @{Name = 'RAM_MB'; Expression = {
                [math]::Round($_.WorkingSet64 / 1MB, 1)
            }},
            @{Name = 'CPU_s'; Expression = {
                try {
                    [math]::Round($_.CPU, 1)
                }
                catch {
                    0
                }
            }}

    if ($processes) {
        $processes | Format-Table -AutoSize
    }
    else {
        Write-Host '  Nenhum processo AURA/IA encontrado.' -ForegroundColor DarkGray
    }

    Write-Host 'ARQUIVOS DE RUNTIME' -ForegroundColor Yellow

    if (Test-Path -LiteralPath $Runtime) {
        $runtimeFiles = Get-ChildItem `
            -LiteralPath $Runtime `
            -File `
            -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10 `
                Name,
                LastWriteTime,
                @{Name = 'KB'; Expression = {
                    [math]::Round($_.Length / 1KB, 1)
                }}

        if ($runtimeFiles) {
            $runtimeFiles | Format-Table -AutoSize
        }
        else {
            Write-Host '  Nenhum arquivo de runtime ainda.' -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host '  Diretório runtime ainda não existe.' -ForegroundColor DarkGray
    }

    Write-Host 'AUDITORIA / ERROS RECENTES' -ForegroundColor Yellow

    $errorLines = @()

    if (Test-Path -LiteralPath $Runtime) {
        $logs = Get-ChildItem `
            -LiteralPath $Runtime `
            -Filter '*.log' `
            -File `
            -ErrorAction SilentlyContinue

        foreach ($log in $logs) {
            $matches = Select-String `
                -Path $log.FullName `
                -Pattern 'ERROR|Traceback|Exception|CRITICAL|failed|falha|offline|timeout' `
                -ErrorAction SilentlyContinue

            if ($matches) {
                $errorLines += $matches
            }
        }
    }

    if (Test-Path -LiteralPath $AuditLog) {
        $auditMatches = Select-String `
            -Path $AuditLog `
            -Pattern 'ERROR|Traceback|Exception|CRITICAL|failed|falha|offline|timeout' `
            -ErrorAction SilentlyContinue

        if ($auditMatches) {
            $errorLines += $auditMatches
        }
    }

    $errorLines = $errorLines | Select-Object -Last 15

    if ($errorLines) {
        foreach ($item in $errorLines) {
            $fileName = Split-Path $item.Path -Leaf
            Write-Host (
                '  {0}: {1}' -f
                $fileName,
                $item.Line.Trim()
            ) -ForegroundColor Red
        }
    }
    else {
        Write-Host '  Nenhum erro textual recente.' -ForegroundColor Green
    }

    Write-Host ''
    Write-Host 'MODO: SOMENTE LEITURA | CTRL+C para sair | atualização: 2s' -ForegroundColor DarkGray

    Start-Sleep -Seconds 2
}
