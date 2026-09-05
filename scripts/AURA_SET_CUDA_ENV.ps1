# Prefer NVIDIA for Ollama + Python; set CUDA env for current process tree hints
$ErrorActionPreference = "SilentlyContinue"
$env:CUDA_VISIBLE_DEVICES = "0"
$env:OLLAMA_NUM_GPU = "1"
$env:GGML_CUDA_NO_PINNED = "0"
# Hybrid GPU prefs (registry) if script exists
$root = Split-Path -Parent $PSScriptRoot
$hybrid = Join-Path $root "scripts\aura_set_hybrid_gpu.ps1"
if (Test-Path $hybrid) {
  & $hybrid -Root $root | Out-Null
}
Write-Host "[CUDA] CUDA_VISIBLE_DEVICES=$env:CUDA_VISIBLE_DEVICES OLLAMA_NUM_GPU=$env:OLLAMA_NUM_GPU"
