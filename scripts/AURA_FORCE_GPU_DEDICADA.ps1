# AURA V32 - Force dedicated NVIDIA GPU for Ollama + Engine Python
param([string]$Root = "")
$ErrorActionPreference = "SilentlyContinue"
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = $Root.TrimEnd('\')

$env:CUDA_VISIBLE_DEVICES = "0"
$env:OLLAMA_NUM_GPU = "1"
$env:GGML_CUDA_NO_PINNED = "0"
$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"

$key = "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }

function Set-GpuPref([string]$exe, [string]$pref, [string]$label) {
  if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) {
    Write-Host "[GPU] skip $label"
    return
  }
  $full = (Resolve-Path -LiteralPath $exe).Path
  New-ItemProperty -Path $key -Name $full -Value ("GpuPreference={0};" -f $pref) -PropertyType String -Force | Out-Null
  $mode = if ($pref -eq "2") { "DEDICATED/NVIDIA" } else { "INTEGRATED/economy" }
  Write-Host "[GPU] $label -> $mode"
}

$pythonVenv = Join-Path $Root "engine\venv\Scripts\python.exe"
$ollamaLocal = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$ollamaWhich = (Get-Command ollama.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)

# 2 = High performance (dedicated)
Set-GpuPref $pythonVenv "2" "Engine Python venv"
Set-GpuPref $ollamaLocal "2" "Ollama local"
if ($ollamaWhich -and $ollamaWhich -ne $ollamaLocal) { Set-GpuPref $ollamaWhich "2" "Ollama PATH" }

# Browsers on integrated to free dedicated VRAM
$chrome = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe" }
Set-GpuPref $chrome "1" "Chrome (integrated)"
if (Test-Path $edge) { Set-GpuPref $edge "1" "Edge (integrated)" }

Write-Host "[CUDA] CUDA_VISIBLE_DEVICES=$env:CUDA_VISIBLE_DEVICES OLLAMA_NUM_GPU=$env:OLLAMA_NUM_GPU"
Write-Host "[GPU] Done. Restart Ollama/core to apply registry prefs."
exit 0
