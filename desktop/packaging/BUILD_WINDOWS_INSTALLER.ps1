[CmdletBinding()]
param(
  [switch]$SkipPublish,
  [string]$InnoSetupPath = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$publishScript = Join-Path $PSScriptRoot 'PUBLISH_WINDOWS.ps1'
$iss = Join-Path $PSScriptRoot 'AURA_Setup.iss'
$outputDir = Join-Path $repoRoot 'dist_installer'
$logDir = Join-Path $repoRoot 'logs_instalacao'

if (-not [Environment]::Is64BitOperatingSystem) {
  throw 'O instalador AURA QUANT-X exige Windows x64.'
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
  throw 'dotnet SDK não encontrado. Instale o .NET 8 SDK e execute novamente.'
}
if (-not (Test-Path $iss)) {
  throw "Script Inno Setup ausente: $iss"
}

function Resolve-InnoSetupPath {
  param([string]$RequestedPath)

  $candidates = @()
  if ($RequestedPath) { $candidates += $RequestedPath }
  if ($env:INNO_SETUP_PATH) { $candidates += $env:INNO_SETUP_PATH }

  $resolvedIscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($resolvedIscc) { $candidates += $resolvedIscc.Source }

  $candidates += @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
  )

  $registryKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
  )
  foreach ($registryKey in $registryKeys) {
    try {
      $installLocation = (Get-ItemProperty -LiteralPath $registryKey -Name InstallLocation -ErrorAction Stop).InstallLocation
      if ($installLocation) { $candidates += (Join-Path $installLocation 'ISCC.exe') }
    } catch {
      # Registry key absent or unreadable; continue with the next source.
    }
  }

  foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
    $path = $candidate
    if (Test-Path -LiteralPath $path -PathType Container) {
      $path = Join-Path $path 'ISCC.exe'
    }
    if ((Test-Path -LiteralPath $path -PathType Leaf) -and ((Split-Path -Leaf $path) -ieq 'ISCC.exe')) {
      return (Resolve-Path -LiteralPath $path).Path
    }
  }
  return $null
}

$InnoSetupPath = Resolve-InnoSetupPath -RequestedPath $InnoSetupPath
if (-not $InnoSetupPath) {
  throw 'Inno Setup 6 was not found. Install Inno Setup 6+ or pass -InnoSetupPath with the full path to ISCC.exe. Diagnostic: Test-Path ''C:\Program Files (x86)\Inno Setup 6\ISCC.exe'''
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (-not $SkipPublish) {
  & $publishScript -Configuration Release -Runtime win-x64
  if ($LASTEXITCODE -ne 0) {
    throw "The .NET publish failed with exit code $LASTEXITCODE."
  }
}

$publishExe = Join-Path $repoRoot 'desktop\publish\Aura.QuantX.Desktop.exe'
$required = @(
  $publishExe,
  (Join-Path $repoRoot 'desktop\publish\config\desktop.json'),
  (Join-Path $repoRoot 'desktop\publish\capture\aura-capture.js'),
  (Join-Path $repoRoot 'desktop\publish\ui\index.html')
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) {
    throw "Published payload is incomplete: $($missing -join '; ')"
}

Write-Host "Compiling Inno Setup: $iss" -ForegroundColor Cyan
& $InnoSetupPath /Qp $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$setups = Get-ChildItem -LiteralPath $outputDir -Filter '*.exe' -File | Sort-Object LastWriteTime -Descending
if (-not $setups) {
    throw "No Setup.exe was produced in $outputDir."
}
$setup = $setups[0]
$hash = (Get-FileHash -Algorithm SHA256 $setup.FullName).Hash
$record = [ordered]@{
  product = 'AURA QUANT-X'
  version = '25.0.0'
  artifact = $setup.Name
  path = $setup.FullName
  sha256 = $hash
  built_at_utc = [DateTime]::UtcNow.ToString('o')
  runtime = 'win-x64 self-contained shell'
  backend_autostart = $false
  webview2_required = $true
  paper_trade_only = $true
  execution_allowed = $false
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputDir 'installer-build.json') -Encoding UTF8
"$hash  $($setup.Name)" | Set-Content -LiteralPath (Join-Path $outputDir "$($setup.Name).sha256") -Encoding ASCII
Write-Host 'WINDOWS_INSTALLER_BUILD=PASS' -ForegroundColor Green
Write-Host "Setup: $($setup.FullName)"
Write-Host "SHA-256: $hash"
