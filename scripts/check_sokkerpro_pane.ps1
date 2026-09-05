# AURA QUANT-X - Alerta de pane SokkerPRO
# Detecta se o feed esta a chegar. Se nao, alerta que o SokkerPRO
# provavelmente NAO esta na pane DIREITA do Desktop.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\check_sokkerpro_pane.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\check_sokkerpro_pane.ps1 -Watch -IntervalSec 20

[CmdletBinding()]
param(
    [switch]$Watch,
    [int]$IntervalSec = 20,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$logDir = Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$alertLog = Join-Path $logDir "sokkerpro_pane_alerts.log"
$resultJson = Join-Path $logDir "sokkerpro_pane_status.json"

function Write-Alert {
    param([string]$msg, [string]$level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$level] $msg"
    Add-Content -Path $alertLog -Value $line -Encoding UTF8
    if (-not $Quiet) {
        switch ($level) {
            "OK"    { Write-Host $line -ForegroundColor Green }
            "WARN"  { Write-Host $line -ForegroundColor Yellow }
            "ALERT" { Write-Host $line -ForegroundColor Magenta }
            "ERROR" { Write-Host $line -ForegroundColor Red }
            default { Write-Host $line }
        }
    }
}

function Get-UiState {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:8765/api/ui/state" -UseBasicParsing -TimeoutSec 3
        return $r.Content | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-BridgeHealth {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:8080/health" -UseBasicParsing -TimeoutSec 2
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

function Test-CaptureLogRecent {
    $logPath = Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\logs\capture_forwarder.log"
    if (-not (Test-Path $logPath)) { return $false }
    $item = Get-Item $logPath
    return ($item.LastWriteTime -gt (Get-Date).AddMinutes(-2))
}

function Invoke-Check {
    $status = @{
        timestamp          = (Get-Date).ToString("o")
        bridge_up          = $false
        engine_ui_ok       = $false
        has_home_away      = $false
        feed_lines         = 0
        source             = ""
        capture_log_recent = $false
        desktop_running    = $false
        alert_level        = "OK"
        alert_message      = ""
        recommendations    = @()
    }

    $status.bridge_up = Get-BridgeHealth
    $status.desktop_running = [bool](Get-Process -Name "Aura.QuantX.Desktop" -ErrorAction SilentlyContinue)
    $status.capture_log_recent = Test-CaptureLogRecent

    $ui = Get-UiState
    if ($ui) {
        $status.engine_ui_ok = $true
        $homeVal = $ui.home
        $awayVal = $ui.away
        $status.has_home_away = (-not [string]::IsNullOrWhiteSpace($homeVal)) -or (-not [string]::IsNullOrWhiteSpace($awayVal))
        if ($ui.feedLines) {
            $status.feed_lines = [int]$ui.feedLines
        }
        $status.source = "$($ui.source)"
    }

    if (-not $status.bridge_up) {
        $status.alert_level = "ERROR"
        $status.alert_message = "Bridge offline (porta 8080). Rode AURA_FIX_EMERGENCIA_TOKEN_CAPTURA.bat"
        $status.recommendations += "Subir Bridge com o BAT de emergencia FIXED"
    }
    elseif (-not $status.desktop_running) {
        $status.alert_level = "ALERT"
        $status.alert_message = "Desktop NAO esta a correr. Abra Aura.QuantX.Desktop.exe"
        $status.recommendations += "Abrir o Desktop e colocar SokkerPRO na pane DIREITA"
    }
    elseif ((-not $status.capture_log_recent) -and (-not $status.has_home_away)) {
        $status.alert_level = "ALERT"
        $status.alert_message = "SEM CAPTURA: SokkerPRO provavelmente NAO esta na pane DIREITA do Desktop (ou token em falta)"
        $status.recommendations += "1. Confirme que a pane DIREITA do Desktop tem o SokkerPRO com jogo AO VIVO"
        $status.recommendations += "2. NAO use apenas o Chrome externo - a injecao nativa so funciona dentro do Desktop"
        $status.recommendations += "3. Verifique token: powershell -File scripts\validate_bridge_token.ps1 -Fix"
        $status.recommendations += "4. Se EXE antigo -> AURA_COMPILAR_DESKTOP.bat"
    }
    elseif ($status.has_home_away -or ($status.feed_lines -gt 0)) {
        $status.alert_level = "OK"
        $status.alert_message = "Feed OK - home/away ou feedLines > 0 detetado"
    }
    else {
        $status.alert_level = "WARN"
        $status.alert_message = "Estado intermedio - aguarde 30-60s com SokkerPRO AO VIVO na pane direita"
        $status.recommendations += "Espere e volte a verificar"
    }

    ($status | ConvertTo-Json -Depth 5) | Set-Content -Path $resultJson -Encoding UTF8

    Write-Alert "Bridge=$($status.bridge_up) Desktop=$($status.desktop_running) Feed=$($status.has_home_away) Lines=$($status.feed_lines) Source=$($status.source)" "INFO"
    Write-Alert $status.alert_message $status.alert_level
    foreach ($r in $status.recommendations) {
        Write-Alert "  -> $r" "WARN"
    }

    return $status
}

Write-Alert "=== Check SokkerPRO Pane ===" "INFO"

if ($Watch) {
    Write-Alert "Modo Watch ativo (intervalo ${IntervalSec}s). Ctrl+C para parar." "INFO"
    while ($true) {
        $null = Invoke-Check
        Start-Sleep -Seconds $IntervalSec
    }
}
else {
    $s = Invoke-Check
    if ($s.alert_level -eq "OK") {
        exit 0
    }
    else {
        exit 1
    }
}
