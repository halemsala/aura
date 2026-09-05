[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Apply,
    [switch]$Force,
    [string]$RootPath = (Join-Path $PSScriptRoot '..\..\..'),
    [string]$LogPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootPath = (Resolve-Path -LiteralPath $RootPath).Path
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $logDir = Join-Path $RootPath 'logs_instalacao'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $LogPath = Join-Path $logDir 'pillar9_cleanup.log'
}

$serviceNames = @('python.exe', 'pythonw.exe')
$ports = @(8080, 8765, 8099, 8088)
$scriptPattern = '(?i)(?:\\engine\\server\.py|\\bridge\\server\.py|\\bridge\\jarvis_voice_server\.py|\\engine\\core_system\.py)'
$rootPattern = [regex]::Escape($RootPath.TrimEnd('\'))

function Write-AuditLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 's'), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-ProcessSnapshot {
    param([int]$ProcessId)
    try {
        return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-CanonicalAuraProcess {
    param($Process)
    if ($null -eq $Process) { return $false }
    $commandLine = [string]$Process.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }
    return ($commandLine -match $rootPattern) -and ($commandLine -match $scriptPattern) -and ($serviceNames -contains ([string]$Process.Name).ToLowerInvariant())
}

function Stop-Candidate {
    param($Process, [string]$Reason)
    $processId = [int]$Process.ProcessId
    $name = [string]$Process.Name
    $description = "PID=$processId Name=$name Reason=$Reason CommandLine=$([string]$Process.CommandLine)"
    if (-not $Apply) {
        Write-AuditLog "[DRY-RUN] candidato ignorado: $description"
        return
    }
    if ($PSCmdlet.ShouldProcess($description, 'Stop-AuraOwnedProcess')) {
        try {
            Write-AuditLog "[APPLY] parada graciosa solicitada: $description"
            Stop-Process -Id $processId -ErrorAction Stop
            Start-Sleep -Milliseconds 500
            if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
                if ($Force) {
                    Write-AuditLog "[APPLY] parada forçada autorizada por -Force: PID=$processId"
                    Stop-Process -Id $processId -Force -ErrorAction Stop
                } else {
                    Write-AuditLog "[WARNING] processo não encerrou; use -Force somente após revisão: PID=$processId"
                }
            } else {
                Write-AuditLog "[OK] processo encerrado: PID=$processId"
            }
        } catch {
            Write-AuditLog "[ERROR] falha ao encerrar PID=${processId}: $($_.Exception.GetType().Name)"
        }
    }
}

Write-AuditLog ("Pillar9 cleanup start Apply={0} Force={1} Root={2}" -f $Apply.IsPresent, $Force.IsPresent, $RootPath)
if (-not $Apply) {
    Write-AuditLog '[INFO] modo dry-run: nenhum processo será alterado. Use -Apply para uma limpeza explícita.'
}

foreach ($port in $ports) {
    try {
        $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            $processId = [int]$connection.OwningProcess
            if ($processId -le 4) { continue }
            $snapshot = Get-ProcessSnapshot -ProcessId $processId
            if (Test-CanonicalAuraProcess -Process $snapshot) {
                Stop-Candidate -Process $snapshot -Reason "canonical service port $port"
            } else {
                Write-AuditLog "[SKIP] PID=$processId port=$port não corresponde ao processo AURA canônico"
            }
        }
    } catch {
        Write-AuditLog "[WARNING] falha ao consultar porta ${port}: $($_.Exception.GetType().Name)"
    }
}

try {
    $currentPid = $PID
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            [int]$_.ProcessId -ne $currentPid -and (Test-CanonicalAuraProcess -Process $_)
        } |
        ForEach-Object {
            Stop-Candidate -Process $_ -Reason 'canonical AURA command line'
        }
} catch {
    Write-AuditLog "[WARNING] falha na varredura WMI canônica: $($_.Exception.GetType().Name)"
}

Write-AuditLog '[Pillar9] limpeza concluída sem atingir processos fora da raiz/allowlist AURA'
