#Requires -Version 5.1
# AURA LAB - install ops_daemon scheduled task (Windows)
# auto_repair = OFF
#
# Usage:
#   Set-ExecutionPolicy -Scope Process Bypass
#   cd C:\aura\aura_lab
#   .\tools\INSTALL_OPS_DAEMON_WINDOWS.ps1
#   .\tools\INSTALL_OPS_DAEMON_WINDOWS.ps1 -IntervalMinutes 10
#   .\tools\INSTALL_OPS_DAEMON_WINDOWS.ps1 -Uninstall

[CmdletBinding()]
param(
    [string]$LabRoot = "C:\aura\aura_lab",
    [int]$IntervalMinutes = 5,
    [string]$TaskName = "AURA_LAB_OpsDaemon",
    [switch]$Uninstall,
    [switch]$SkipEnv
)

$ErrorActionPreference = "Stop"

function Find-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        return $cmd.Source
    }
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        return $cmd.Source
    }
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    throw "Python not found. Install Python 3.10+ and add it to PATH."
}

Write-Host "=== AURA LAB ops_daemon installer ===" -ForegroundColor Cyan
Write-Host "LabRoot: $LabRoot"
Write-Host "IntervalMinutes: $IntervalMinutes"
Write-Host "TaskName: $TaskName"
Write-Host "auto_repair=OFF"

$daemon = Join-Path $LabRoot "tools\ops_daemon.py"
if (-not (Test-Path -LiteralPath $daemon)) {
    throw "File not found: $daemon - extract AURA_LAB zip to $LabRoot"
}

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed task: $TaskName" -ForegroundColor Yellow
    }
    else {
        # fallback schtasks
        schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
        Write-Host "Delete attempted for: $TaskName"
    }
    exit 0
}

if (-not $SkipEnv) {
    [System.Environment]::SetEnvironmentVariable("AURA_LAB_ROOT", $LabRoot, "User")
    $env:AURA_LAB_ROOT = $LabRoot
    Write-Host "AURA_LAB_ROOT (User) = $LabRoot" -ForegroundColor Green
    Write-Host "Close and reopen terminals/Harness to inherit env."
}

$python = Find-Python
Write-Host "Python: $python"

Write-Host "Running test: ops_daemon --once ..."
& $python $daemon --once
Write-Host "Test finished."

# Remove old task if present
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed previous task definition."
}

# schtasks is more reliable than MaxValue RepetitionDuration on Windows
# /TR must be one command string
$tr = "`"$python`" `"$daemon`" --once"
$mo = [Math]::Max(1, [int]$IntervalMinutes)

Write-Host "Registering via schtasks (every $mo minutes)..."
$create = schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO $mo /RL LIMITED /F
if ($LASTEXITCODE -ne 0) {
    Write-Host "schtasks failed, trying Register-ScheduledTask fallback..." -ForegroundColor Yellow
    $arg = "`"$daemon`" --once"
    $action = New-ScheduledTaskAction -Execute $python -Argument $arg -WorkingDirectory $LabRoot
    $start = (Get-Date).AddMinutes(1)
    # Finite duration: 10 years (Windows rejects TimeSpan.MaxValue)
    $repInterval = New-TimeSpan -Minutes $mo
    $repDuration = New-TimeSpan -Days 3650
    $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval $repInterval -RepetitionDuration $repDuration
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}

# Set working directory via XML tweak is hard; daemon uses absolute paths for scripts
# Verify task exists
$check = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $check) {
    throw "Task was NOT registered: $TaskName"
}

Write-Host ""
Write-Host "OK - scheduled task registered: $TaskName" -ForegroundColor Green
Write-Host "  Execute : $python"
Write-Host "  Script  : $daemon --once"
Write-Host "  Every   : $mo minutes"
Write-Host ""
Write-Host "Verify: schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "Open GUI: taskschd.msc"
Write-Host "Uninstall: .\tools\INSTALL_OPS_DAEMON_WINDOWS.ps1 -Uninstall"
Write-Host "Harness: restart, then: experiencias / ops / daemon"
