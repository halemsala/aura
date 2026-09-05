# DISABLE_GLM.ps1 — desativa GLM sem apagar backup
# Rode na raiz C:\aura\AURA_QUANT_X_12.7.0 como Admin se necessário

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "engine"))) {
  $Root = Get-Location
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root ".install-backups\glm-disabled-$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

$Targets = @(
  "engine\agents_glm",
  "engine\glm_inference_gate.py",
  "engine\agent_glm_runtime.py",
  "bridge\glm5_inference_bridge.py",
  "engine\agents\glm_analysis_agent.py",
  "engine\agents\glm_config.yaml",
  "engine\agents\activation_manifest_glm.json",
  "agents\glm_analysis_agent.py",
  "agents\glm_config.yaml",
  "scripts\glm_preflight.py"
)

foreach ($rel in $Targets) {
  $src = Join-Path $Root $rel
  if (Test-Path $src) {
    $dest = Join-Path $Backup $rel
    $destDir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Move-Item -Force $src $dest
    Write-Host "MOVED -> backup: $rel"
  } else {
    Write-Host "skip (missing): $rel"
  }
}

# Stub mínimo para imports legados não quebrarem
$StubDir = Join-Path $Root "engine\agents_glm"
New-Item -ItemType Directory -Force -Path $StubDir | Out-Null
@"
# GLM disabled by DISABLE_GLM.ps1 — stubs only
def __getattr__(name):
    raise RuntimeError('GLM_DISABLED: use Hermes / AURA IA One')
"@ | Set-Content -Encoding UTF8 (Join-Path $StubDir "__init__.py")

@"
# GLM gate disabled
class GlmInferenceGate:
    enabled = False
    def __init__(self, *a, **k):
        self.enabled = False
    def health(self):
        return {'ok': False, 'glm_enabled': False, 'reason': 'disabled'}
    def infer(self, *a, **k):
        return {'status': 'GLM_DISABLED', 'use': 'hermes'}
"@ | Set-Content -Encoding UTF8 (Join-Path $Root "engine\glm_inference_gate.py")

@"
# GLM runtime disabled
class AgentGlmRuntime:
    enabled = False
    def run(self, *a, **k):
        return {'status': 'GLM_DISABLED'}
"@ | Set-Content -Encoding UTF8 (Join-Path $Root "engine\agent_glm_runtime.py")

# Flag de estado
$FlagDir = Join-Path $Root "engine\data"
New-Item -ItemType Directory -Force -Path $FlagDir | Out-Null
@{
  glm_enabled = $false
  hermes_primary = $true
  disabled_at = (Get-Date).ToString("o")
  backup = $Backup
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $FlagDir "glm_status.json")

Write-Host ""
Write-Host "GLM desativado. Backup em: $FlagDir"
Write-Host "Hermes permanece como caminho principal."
Write-Host "Reinicie Bridge/Engine (AURA_UM_COMANDO.bat)."
