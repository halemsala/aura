[CmdletBinding()]
param(
  [ValidateSet('Debug','Release')]
  [string]$Configuration = 'Release',
  [ValidateSet('win-x64')]
  [string]$Runtime = 'win-x64',
  [switch]$FrameworkDependent
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$project = Join-Path $repoRoot 'desktop\Aura.Desktop.csproj'
$publishDirFinal = Join-Path $repoRoot 'desktop\publish'
$publishDir = $publishDirFinal

if (-not [Environment]::Is64BitOperatingSystem) {
  throw 'AURA QUANT-X requer Windows 64 bits.'
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
  throw 'SDK dotnet não encontrado. Instale o .NET 8 SDK no Windows antes da publicação.'
}
if (-not (Test-Path $project)) {
  throw "Projeto desktop ausente: $project"
}
if (-not (Test-Path (Join-Path $repoRoot 'desktop\config\desktop.json'))) {
  throw 'desktop/config/desktop.json ausente; execute o script na raiz completa do AURA.'
}
$operatorUi = Join-Path $repoRoot 'desktop\ui\matriz_v22'
if (-not (Test-Path (Join-Path $operatorUi 'index.html'))) {
  throw 'desktop/ui/matriz_v22/index.html ausente; a Operator OS está incompleta.'
}
if (-not (Test-Path (Join-Path $operatorUi 'BUILD_INFO.json'))) {
  throw 'desktop/ui/matriz_v22/BUILD_INFO.json ausente; a identidade do bundle não pode ser comprovada.'
}
if (-not (Test-Path (Join-Path $repoRoot 'desktop\capture\aura-capture.js'))) {
  throw 'desktop/capture/aura-capture.js ausente; o shell não pode ser publicado.'
}

$stagingDir = Join-Path $repoRoot 'desktop\publish_staging'
if (Test-Path $stagingDir) {
  Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
$publishDir = $stagingDir

$runtimeArgs = @('--runtime', $Runtime)
$selfContainedArgs = @('--self-contained', ($(if ($FrameworkDependent) { 'false' } else { 'true' })))
Write-Host "Publicando AURA Desktop em staging $publishDir" -ForegroundColor Cyan

dotnet restore $project --runtime $Runtime
if ($LASTEXITCODE -ne 0) {
  throw "dotnet restore failed with exit code $LASTEXITCODE."
}

dotnet publish $project `
  --configuration $Configuration `
  --runtime $Runtime `
  --self-contained $(if ($FrameworkDependent) { 'false' } else { 'true' }) `
  --no-restore `
  --output $publishDir `
  -p:Platform=x64 `
  -p:PublishSingleFile=false `
  -p:PublishTrimmed=false `
  -p:DebugType=None `
  -p:DebugSymbols=false
$publishExitCode = $LASTEXITCODE
if ($publishExitCode -ne 0) {
  throw "dotnet publish failed with exit code $publishExitCode. No executable was produced."
}

$manusDir = Join-Path $publishDir 'ui\matriz_v22\__manus__'
if (Test-Path -LiteralPath $manusDir) {
  Write-Host "Removendo instrumentacao __manus__ injetada no bundle publicado ($manusDir)" -ForegroundColor Yellow
  Remove-Item -LiteralPath $manusDir -Recurse -Force
}

$required = @(
  (Join-Path $publishDir 'Aura.QuantX.Desktop.exe'),
  (Join-Path $publishDir 'config\desktop.json'),
  (Join-Path $publishDir 'capture\aura-capture.js'),
  (Join-Path $publishDir 'ui\matriz_v22\index.html'),
  (Join-Path $publishDir 'ui\matriz_v22\BUILD_INFO.json'),
  (Join-Path $publishDir 'ui\matriz_v22\manifest.webmanifest'),
  (Join-Path $publishDir 'ui\matriz_v22\sw.js')
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) {
  throw "Publicação incompleta. Ausentes: $($missing -join ', ')"
}

$operatorPublishedUi = Join-Path $publishDir 'ui\matriz_v22'
$publishedBuildInfo = Get-Content -Raw -LiteralPath (Join-Path $operatorPublishedUi 'BUILD_INFO.json')
# V27: aceita BUILD_INFO Mesa Live OU legado V25T6
$okV27 = (($publishedBuildInfo -match '12\.7\.62-V27') -and ($publishedBuildInfo -match 'OPERATOR-OS')) -or (($publishedBuildInfo -match '12\.7\.0-V25Q') -and ($publishedBuildInfo -match 'ORIGINAL-UI'))
$okV25 = ($publishedBuildInfo -match '12\.7\.0-V25T6-OPERATOR-OS-INDEX-FIX') -and ($publishedBuildInfo -match '"hosted_under"\s*:\s*"/index\.html"')
if (-not ($okV27 -or $okV25)) {
  throw 'BUILD_INFO publicado inválido. Esperado V27 Operator OS ou V25Q Original UI em /index.html.'
}
$publishedIndexPath = Join-Path $operatorPublishedUi 'index.html'
$publishedIndex = Get-Content -Raw -LiteralPath $publishedIndexPath
if ($publishedIndex -match 'manus-storage|umami|VITE_ANALYTICS') {
  throw 'Bundle publicado contém referência remota/analytics proibida para o Desktop local.'
}
function Test-LocalAssetReferences {
  param([string]$Text, [string]$BaseDir, [string]$Label)
  $refs = [regex]::Matches($Text, '(?:src|href)=["'']([^"'']+)["'']', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
  foreach ($match in $refs) {
    $ref = [string]$match.Groups[1].Value
    if ([string]::IsNullOrWhiteSpace($ref) -or $ref -match '^(?:https?:|data:|mailto:|#|javascript:)') { continue }
    $clean = ($ref -split '[?#]', 2)[0]
    if ($clean -match '^(?:/)?api(?:/|$)') { continue }
    if ($clean.StartsWith('/')) { $candidate = Join-Path $operatorPublishedUi $clean.TrimStart('/') }
    else { $candidate = Join-Path $BaseDir $clean }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      throw "Asset local ausente em ${Label}: $ref -> $candidate"
    }
  }
}
Test-LocalAssetReferences $publishedIndex $operatorPublishedUi 'index.html'
$manifestPath = Join-Path $operatorPublishedUi 'manifest.webmanifest'
$manifestText = Get-Content -Raw -LiteralPath $manifestPath
Test-LocalAssetReferences $manifestText $operatorPublishedUi 'manifest.webmanifest'
$swPath = Join-Path $operatorPublishedUi 'sw.js'
$swText = Get-Content -Raw -LiteralPath $swPath
foreach ($swRef in [regex]::Matches($swText, '["''](/[^"'']+)["'']')) {
  $candidate = Join-Path $operatorPublishedUi (($swRef.Groups[1].Value -split '[?#]', 2)[0].TrimStart('/'))
  $swClean = ($swRef.Groups[1].Value -split '[?#]', 2)[0]
  if ($swClean -match '^(?:/)?api(?:/|$)') { continue }
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Asset do service worker ausente: $($swRef.Groups[1].Value)" }
}
$manifest = $manifestText | ConvertFrom-Json
if ([string]$manifest.start_url -notin @('./', './index.html', '/index.html')) {
  throw "manifest start_url inesperado: $($manifest.start_url)"
}
$exe = Get-Item (Join-Path $publishDir 'Aura.QuantX.Desktop.exe')
$hash = (Get-FileHash -Algorithm SHA256 $exe.FullName).Hash
$versionInfo = $exe.VersionInfo
$informationalVersion = [string]$versionInfo.ProductVersion
$expectedInformationalVersion = '12.7.62-V27-UI-FIX'
$legacyVersion = '12.7.0-V25T6-OPERATOR-OS-INDEX-FIX'
if (($informationalVersion -notlike "*$expectedInformationalVersion*") -and ($informationalVersion -notlike "*$legacyVersion*")) {
  throw "EXE publicado com ProductVersion inesperado: '$informationalVersion'. Esperado V27-UI-FIX ou legado V25T6."
}
$publishRecord = [ordered]@{
  build_id = $informationalVersion
  executable = $exe.Name
  sha256 = $hash
  length = [int64]$exe.Length
  last_write_time = $exe.LastWriteTime.ToString('o')
  configuration = $Configuration
  runtime = $Runtime
  self_contained = (-not $FrameworkDependent)
}
$publishInfoPath = Join-Path $publishDir 'AURA_PUBLISH_INFO.json'
$publishInfoJson = $publishRecord | ConvertTo-Json -Depth 3
# -Encoding UTF8 do Windows PowerShell 5.x grava um BOM no inicio do
# arquivo, o que quebra json.loads() estrito em Python (aura_package_precheck.py
# le com encoding="utf-8", sem "-sig"). UTF8NoBOM evita o problema na origem.
[System.IO.File]::WriteAllText($publishInfoPath, $publishInfoJson, (New-Object System.Text.UTF8Encoding($false)))

# Swap atomico: so substitui publish\ depois de PASS
$publishDir = $publishDirFinal
if ($stagingDir -and (Test-Path $stagingDir)) {
  $backup = Join-Path $repoRoot 'desktop\publish_backup_prev'
  if (Test-Path $publishDir) {
    if (Test-Path $backup) { Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue }
    Rename-Item -LiteralPath $publishDir -NewName 'publish_backup_prev' -ErrorAction SilentlyContinue
  }
  Rename-Item -LiteralPath $stagingDir -NewName 'publish'
}

Write-Host 'PUBLICACAO_WINDOWS=PASS' -ForegroundColor Green
Write-Host "Build ID EXE: $informationalVersion"
Write-Host "Executável: $($exe.FullName)"
Write-Host "SHA-256 EXE: $hash"
Write-Host 'O WebView2 Runtime deve estar instalado no Windows de destino.' -ForegroundColor Yellow
Write-Host 'O backend permanece separado e não é iniciado por este script.' -ForegroundColor Yellow
