# AURA QUANT-X - Script de validacao do token Bridge
# Uso: powershell -ExecutionPolicy Bypass -File scripts\validate_bridge_token.ps1
#      powershell -ExecutionPolicy Bypass -File scripts\validate_bridge_token.ps1 -Fix

[CmdletBinding()]
param(
    [string]$TokenPath = (Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\secure\cornerai_bridge_token.bin"),
    [switch]$Fix,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "token_validation.log"

function Write-Log {
    param([string]$msg, [string]$level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$level] $msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    if (-not $Quiet) {
        switch ($level) {
            "OK"    { Write-Host $line -ForegroundColor Green }
            "WARN"  { Write-Host $line -ForegroundColor Yellow }
            "ERROR" { Write-Host $line -ForegroundColor Red }
            default { Write-Host $line }
        }
    }
}

Write-Log "=== Validacao de CORNERAI_BRIDGE_TOKEN ==="

$result = @{
    timestamp     = (Get-Date).ToString("o")
    token_path    = $TokenPath
    exists        = $false
    size_bytes    = 0
    valid         = $false
    can_unprotect = $false
    length_plain  = 0
    env_present   = $false
    message       = ""
    fixed         = $false
}

try {
    if (Test-Path -LiteralPath $TokenPath) {
        $result.exists = $true
        $item = Get-Item -LiteralPath $TokenPath
        $result.size_bytes = $item.Length
        Write-Log "Ficheiro existe ($($item.Length) bytes)" "OK"

        if ($item.Length -lt 32) {
            Write-Log "Ficheiro demasiado curto (< 32 bytes) - invalido" "ERROR"
            $result.message = "token_file_too_short"
        }
        else {
            Add-Type -AssemblyName System.Security
            $cipher = [IO.File]::ReadAllBytes($TokenPath)
            try {
                $plain = [Security.Cryptography.ProtectedData]::Unprotect(
                    $cipher, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
                $tokenStr = [Text.Encoding]::UTF8.GetString($plain)
                $result.can_unprotect = $true
                $result.length_plain = $tokenStr.Length
                if ($tokenStr.Length -ge 16) {
                    $result.valid = $true
                    Write-Log "Token valido (plain length=$($tokenStr.Length))" "OK"
                    $result.message = "ok"
                }
                else {
                    Write-Log "Token desencriptado mas demasiado curto" "ERROR"
                    $result.message = "token_plain_too_short"
                }
            }
            catch {
                Write-Log "Falha DPAPI Unprotect: $($_.Exception.Message)" "ERROR"
                $result.message = "dpapi_unprotect_failed"
            }
        }
    }
    else {
        Write-Log "Token NAO existe: $TokenPath" "ERROR"
        $result.message = "token_missing"
    }

    $envToken = [Environment]::GetEnvironmentVariable("CORNERAI_BRIDGE_TOKEN")
    if (-not [string]::IsNullOrWhiteSpace($envToken)) {
        $result.env_present = $true
        Write-Log "CORNERAI_BRIDGE_TOKEN presente no ambiente (len=$($envToken.Length))" "OK"
    }
    else {
        Write-Log "CORNERAI_BRIDGE_TOKEN NAO esta no ambiente deste processo" "WARN"
    }

    if ($Fix -and -not $result.valid) {
        Write-Log "Modo -Fix ativo: a regenerar token..." "WARN"
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $prepare = Join-Path (Split-Path -Parent $scriptDir) "scripts\prepare_bridge_token.ps1"
        if (-not (Test-Path $prepare)) {
            $prepare = Join-Path $scriptDir "prepare_bridge_token.ps1"
        }
        if (Test-Path $prepare) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $prepare -Mode Ensure -Path $TokenPath
            $result.fixed = $true
            Write-Log "Token regenerado via prepare_bridge_token.ps1" "OK"
            $result.valid = $true
            $result.message = "fixed"
        }
        else {
            Add-Type -AssemblyName System.Security
            $dir = Split-Path -Parent $TokenPath
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $raw = New-Object byte[] 32
            $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
            $rng.GetBytes($raw)
            $rng.Dispose()
            $protected = [Security.Cryptography.ProtectedData]::Protect(
                $raw, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
            $tmp = "$TokenPath.$PID.tmp"
            [IO.File]::WriteAllBytes($tmp, $protected)
            Move-Item -LiteralPath $tmp -Destination $TokenPath -Force
            $result.fixed = $true
            $result.valid = $true
            $result.message = "fixed_native"
            Write-Log "Token regenerado via DPAPI nativo" "OK"
        }
    }
}
catch {
    Write-Log "Excecao: $($_.Exception.Message)" "ERROR"
    $result.message = "exception"
}

$jsonPath = Join-Path $logDir "token_validation_result.json"
($result | ConvertTo-Json -Depth 4) | Set-Content -Path $jsonPath -Encoding UTF8
Write-Log "Resultado JSON: $jsonPath"

if ($result.valid) {
    exit 0
}
else {
    exit 1
}
