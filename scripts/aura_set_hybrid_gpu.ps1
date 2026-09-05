# AURA QUANT-X — GPU híbrida
# Intel/economia: Chrome (visual)
# NVIDIA/alto desempenho: python da venv, ollama, engine
param([string]$Root = "")
$ErrorActionPreference = "SilentlyContinue"
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = $Root.TrimEnd('\')
$key = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }

function Set-GpuPref([string]$exe, [ValidateSet("1","2")][string]$pref, [string]$label) {
  if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) {
    Write-Host "[GPU] skip $label"
    return
  }
  $full = (Resolve-Path -LiteralPath $exe).Path
  New-ItemProperty -Path $key -Name $full -Value ("GpuPreference={0};" -f $pref) -PropertyType String -Force | Out-Null
  $mode = if ($pref -eq "2") { "NVIDIA/alto" } else { "Intel/economia" }
  Write-Host "[GPU] $label -> $mode"
  Write-Host "      $full"
}

$pythonVenv = Join-Path $Root "engine\venv\Scripts\python.exe"
$ollamaLocal = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$ollamaWhich = (Get-Command ollama.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
$chrome = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe" }

Set-GpuPref $pythonVenv "2" "Engine Python venv"
Set-GpuPref $ollamaLocal "2" "Ollama local"
if ($ollamaWhich -and $ollamaWhich -ne $ollamaLocal) { Set-GpuPref $ollamaWhich "2" "Ollama PATH" }
Set-GpuPref $chrome "1" "Chrome visual"
if (Test-Path $edge) { Set-GpuPref $edge "1" "Edge visual" }

Write-Host "[GPU] Preferencia gravada neste usuario. Reabra Chrome e o core para aplicar."
exit 0
