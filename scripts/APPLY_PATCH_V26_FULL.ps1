# APPLY_PATCH_V26_FULL.ps1
# Copia arquivos do patch para a instalação AURA e aplica flags.
# Uso (na pasta do patch ou passando -AuraRoot):
#   .\scripts\APPLY_PATCH_V26_FULL.ps1 -AuraRoot C:\aura\AURA_QUANT_X_12.7.0

param(
  [string]$AuraRoot = "C:\aura\AURA_QUANT_X_12.7.0",
  [switch]$EnableSkillExecution = $true,
  [switch]$DisableGlm = $true,
  [switch]$UnlockLive = $false
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $PatchRoot "engine\core\policy_runtime.py"))) {
  $PatchRoot = Get-Location
}

if (-not (Test-Path (Join-Path $AuraRoot "engine"))) {
  throw "AuraRoot inválido: $AuraRoot (engine\ não encontrado)"
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $AuraRoot ".install-backups\pre-patch-v26-full-$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

$Files = @(
  "engine\core\policy_runtime.py",
  "engine\core\runtime_manifest.py",
  "engine\core\capture\policy.py",
  "engine\execution_router.py",
  "engine\modules\paper_force_mode.py",
  "engine\aura_ai_one\contracts.py",
  "engine\agents\aura_hermes_router.py",
  "desktop\capture\aura-capture.js",
  "tools\ia_conector\aura-capture.js"
)

foreach ($rel in $Files) {
  $src = Join-Path $PatchRoot $rel
  $dst = Join-Path $AuraRoot $rel
  if (-not (Test-Path $src)) {
    Write-Host "SKIP missing in patch: $rel"
    continue
  }
  if (Test-Path $dst) {
    $b = Join-Path $Backup $rel
    $bdir = Split-Path $b -Parent
    New-Item -ItemType Directory -Force -Path $bdir | Out-Null
    Copy-Item -Force $dst $b
  }
  $ddir = Split-Path $dst -Parent
  New-Item -ItemType Directory -Force -Path $ddir | Out-Null
  Copy-Item -Force $src $dst
  Write-Host "APPLIED $rel"
}

# Skills
$EnvExample = Join-Path $AuraRoot "addons\installation_e_agent_skills\.env.example"
$EnvFile = Join-Path $AuraRoot "addons\installation_e_agent_skills\.env"
$skillVal = if ($EnableSkillExecution) { "1" } else { "0" }
"AURA_E_ENABLE_SKILL_EXECUTION=$skillVal" | Set-Content -Encoding UTF8 $EnvFile
Write-Host "Skill execution = $skillVal"

# Config env template
$ConfigDir = Join-Path $AuraRoot "config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$EnvAura = Join-Path $ConfigDir "AURA_RUNTIME.env"
@"
# AURA runtime policy — paper por padrão
# Para LIVE, veja LEIA_ME_PATCH_V26_FULL.txt (opt-in triplo)
AURA_PAPER_TRADE=1
AURA_EXECUTION_ALLOWED=0
AURA_UNLOCK_LIVE=0
# AURA_UNLOCK_CONFIRM=I_ACCEPT_REAL_EXECUTION_RISK
AURA_E_ENABLE_SKILL_EXECUTION=$skillVal
AURA_HERMES_PRIMARY=1
AURA_GLM_ENABLED=0
"@ | Set-Content -Encoding UTF8 $EnvAura
Write-Host "Wrote config\AURA_RUNTIME.env"

if ($DisableGlm) {
  $Dis = Join-Path $PatchRoot "scripts\DISABLE_GLM.ps1"
  if (Test-Path $Dis) {
    & $Dis
  } else {
    Write-Host "DISABLE_GLM.ps1 não encontrado no patch — rode manualmente."
  }
}

if ($UnlockLive) {
  Write-Host ""
  Write-Host "AVISO: -UnlockLive NÃO ativa LIVE sozinho."
  Write-Host "Você precisa preencher config\UNLOCK_LIVE.flag e as env vars."
  Write-Host "Veja LEIA_ME_PATCH_V26_FULL.txt"
}

# Activation note
$Act = Join-Path $AuraRoot "engine\data"
New-Item -ItemType Directory -Force -Path $Act | Out-Null
@{
  patch = "V26-FULL"
  applied_at = (Get-Date).ToString("o")
  hermes_primary = $true
  glm_enabled = -not $DisableGlm
  skill_execution = [bool]$EnableSkillExecution
  paper_default = $true
  live_requires_explicit_unlock = $true
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Act "patch_v26_full_status.json")

Write-Host ""
Write-Host "PATCH aplicado. Backup: $Backup"
Write-Host "Reinicie: .\AURA_UM_COMANDO.bat"
Write-Host "Teste: .\RODAR_TESTE_AUTOMATICO.bat"
