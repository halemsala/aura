# Install-AURA-CUA-Safe.ps1 — stage only, never -Activate in this deployment
# Does NOT install cua-driver, Hermes, MCP, or start services.
param(
  [string]$AURARoot = "",
  [switch]$Activate
)
if ($Activate) {
  Write-Error "Activation is forbidden in this installation stage. Omit -Activate."
  exit 1
}
Write-Host "Stage-only installer. computer_use_enabled=false. No driver install."
Write-Host "Copy addon folders code/config/tests/docs/installer/windows to addons/aura-computer-use-guarded-connector"
exit 0
