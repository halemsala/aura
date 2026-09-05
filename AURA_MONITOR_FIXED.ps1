# AURA_MONITOR.ps1
# Monitor externo seguro — somente leitura.

$Root = 'C:\aura'
$Runtime = Join-Path $Root 'halem_control\runtime'
$Ports = @(11434, 8765, 8080, 8099)

function Test-PortOk {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        return [bool](Test-NetConnection `
            -ComputerName '127.0.0.1' `
            -Port $Port `
            -InformationLevel Quiet `
            -WarningAction SilentlyContinue)
    }
    catch {
        return $false
    }
}

while ($true) {
    Clear-Host

    Write-Host 'AURA LIVE MONITOR PRO' -ForegroundColor Cyan
    Write-Host (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') -ForegroundColor DarkGray
    Write-Host ''

    Write-Host 'SERVIÇOS' -ForegroundColor Yellow

    foreach ($Port in $Ports) {
        if (Test-PortOk -Port $Port) {
            Write-Host ("  PORTA {0}  ONLINE" -f $Port) -ForegroundColor Green
        }
        else {
            Write-Host ("  PORTA {0}  OFFLINE" -f $Port) -ForegroundColor Red
        }
    }

    Write-Host ''
    Write-Host 'PROCESSOS' -ForegroundColor Yellow

    Get-Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessName -match '(?i)python|aura|electron|node|ollama'
        } |
        Select-Object `
            Id,
            ProcessName,
            @{Name = 'RAM_MB'; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } },
            @{Name = 'CPU_s'; Expression = {
                try {
                    [math]::Round($_.CPU, 1)
                }
                catch {
                    0
                }
            }} |
        Format-Table -AutoSize

    Write-Host 'LOGS RECENTES' -ForegroundColor Yellow

    if (Test-Path -LiteralPath $Runtime) {
        Get-ChildItem -LiteralPath $Runtime -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10 `
                Name,
                LastWriteTime,
                @{Name = 'KB'; Expression = { [math]::Round($_.Length / 1KB, 1) }} |
            Format-Table -AutoSize
    }
    else {
        Write-Host '  Diretório de runtime ainda não existe.' -ForegroundColor DarkGray
    }

    Write-Host 'ERROS / FALHAS' -ForegroundColor Yellow

    if (Test-Path -LiteralPath $Runtime) {
        $Errors = Get-ChildItem -LiteralPath $Runtime -Filter '*.log' -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                Select-String `
                    -Path $_.FullName `
                    -Pattern 'ERROR|Traceback|Exception|CRITICAL|failed|falha|offline|timeout' `
                    -ErrorAction SilentlyContinue
            } |
            Select-Object -Last 15

        if ($Errors) {
            $Errors | ForEach-Object {
                Write-Host ("  {0}: {1}" -f $_.Filename, $_.Line.Trim()) -ForegroundColor Red
            }
        }
        else {
            Write-Host '  Nenhum erro textual recente.' -ForegroundColor Green
        }
    }
    else {
        Write-Host '  Nenhum log disponível ainda.' -ForegroundColor DarkGray
    }

    Write-Host ''
    Write-Host 'CTRL+C para sair | atualização 2s' -ForegroundColor DarkGray

    Start-Sleep -Seconds 2
}
