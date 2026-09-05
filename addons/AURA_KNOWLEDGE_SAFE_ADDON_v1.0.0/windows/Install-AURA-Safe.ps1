[CmdletBinding()]
param(
  [ValidateSet('Plan','Stage','Install','Verify')]
  [string]$Mode = 'Plan',
  [string]$AURARoot = $env:AURA_ROOT
)
$ErrorActionPreference = 'Stop'
$bundle = Split-Path -Parent $PSScriptRoot
$source = Join-Path $bundle 'aura_maximizer'
$report = Join-Path $bundle ('reports\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Force -Path $report | Out-Null

function Fail($msg) { throw "[AURA-INSTALL] $msg" }
function Find-Root {
  if ($AURARoot) { return (Resolve-Path $AURARoot).Path }
  $candidates = @((Get-Location).Path, (Join-Path (Get-Location) 'AURA'), (Join-Path $env:USERPROFILE 'AURA'), (Join-Path $env:USERPROFILE 'aura'))
  foreach ($c in $candidates) {
    if ((Test-Path $c) -and ((Test-Path (Join-Path $c 'README.md')) -or (Test-Path (Join-Path $c 'engine')) -or (Test-Path (Join-Path $c 'config')))) { return (Resolve-Path $c).Path }
  }
  return $null
}
$root = Find-Root
@"
timestamp=$((Get-Date).ToUniversalTime().ToString('o'))
mode=$Mode
target=$root
paper_trade=true
execution_allowed=false
glm_advisory_only=true
network_enabled=false
scheduler_enabled=false
tool_execution_enabled=false
services_started=0
network_calls=0
files_overwritten=0
"@ | Set-Content (Join-Path $report 'plan.env') -Encoding UTF8

if ($Mode -eq 'Plan') { Write-Host "Plano salvo em $report"; if (-not $root) { Write-Host 'AURA_ROOT não detectado; informe -AURARoot.' }; exit 0 }
if (-not $root) { Fail 'AURARoot não detectado. Use -AURARoot C:\caminho\AURA.' }
$stage = Join-Path $report 'staging'
Copy-Item $source $stage -Recurse -Force
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
  & $py.Source -m compileall -q (Join-Path $stage 'aura_maximizer') (Join-Path $stage 'tests')
  & $py.Source -m unittest discover -s (Join-Path $stage 'tests') -q
} else { Write-Host 'Python não encontrado; validação Python marcada como pendente.' }
if ($Mode -eq 'Stage') { Write-Host "Staging aprovado em $stage"; exit 0 }
$dest = Join-Path $root 'addons\aura_maximizer'
$backup = Join-Path $root ('addons\aura_maximizer_backup_' + (Get-Date -Format yyyyMMddTHHmmssZ))
New-Item -ItemType Directory -Force -Path $dest, $backup | Out-Null
Get-ChildItem $stage -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Substring($stage.Length).TrimStart('\')
  $dst = Join-Path $dest $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  if (Test-Path $dst) { Copy-Item $dst (Join-Path $backup ($rel -replace '\\','__') + '.existing'); Write-Host "Preservado: $rel" }
  else { Copy-Item $_.FullName $dst }
}
"timestamp=$((Get-Date).ToUniversalTime().ToString('o'))`ntarget=$root`nbackup=$backup`nmode=installed_inert`nservices_started=0`nnetwork_calls=0`nfiles_overwritten=0" | Set-Content (Join-Path $dest 'INSTALLATION_RECORD.env') -Encoding UTF8
if ($Mode -eq 'Install') { Write-Host "Addon instalado de forma inerte em $dest"; exit 0 }
if ($Mode -eq 'Verify') {
  if (-not (Test-Path $dest)) { Fail 'Addon não encontrado.' }
  if ($py) { & $py.Source -m unittest discover -s (Join-Path $dest 'tests') -q }
  Select-String -Path (Join-Path $dest '*') -Pattern 'execution_allowed=false','paper_trade=true' -Recurse | Out-Null
  Write-Host 'Verificação offline aprovada; integrações permanecem desativadas.'
}
