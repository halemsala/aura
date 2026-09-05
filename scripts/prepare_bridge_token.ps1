[CmdletBinding()]
param(
    [ValidateSet('Ensure', 'Load')]
    [string]$Mode = 'Ensure',
    [string]$Path = (Join-Path $env:LOCALAPPDATA 'AURA_QUANT_X\secure\cornerai_bridge_token.bin')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Security

$directory = Split-Path -Parent $Path
New-Item -ItemType Directory -Path $directory -Force | Out-Null

if ($Mode -eq 'Ensure') {
    if (Test-Path -LiteralPath $Path) {
        $cipher = [IO.File]::ReadAllBytes($Path)
        if ($cipher.Length -lt 32) {
            throw 'existing bridge token is invalid or too short'
        }
        exit 0
    }

    $plain = New-Object byte[] 32
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try {
        $rng.GetBytes($plain)
    } finally {
        $rng.Dispose()
    }
    $cipher = [Security.Cryptography.ProtectedData]::Protect(
        $plain, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $temporary = "$Path.$PID.tmp"
    [IO.File]::WriteAllBytes($temporary, $cipher)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
    exit 0
}

if (-not (Test-Path -LiteralPath $Path)) {
    throw 'bridge token is not provisioned'
}
$cipher = [IO.File]::ReadAllBytes($Path)
$plain = [Security.Cryptography.ProtectedData]::Unprotect(
    $cipher, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
$token = [Text.Encoding]::UTF8.GetString($plain)
if ([string]::IsNullOrWhiteSpace($token)) {
    throw 'bridge token is empty'
}
[Console]::Out.Write($token)
