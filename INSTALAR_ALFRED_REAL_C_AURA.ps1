param(
    [Parameter(Mandatory=$true)][string]$Zip,
    [string]$Target = 'C:\aura',
    [string]$Log = ''
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$stage = $null
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $Target 'logs_supervisor\alfred_real_install.log' }
try {
    $target = [IO.Path]::GetFullPath($Target)
    $zip = [IO.Path]::GetFullPath($Zip)
    New-Item -ItemType Directory -Force -Path (Join-Path $target 'logs_supervisor') | Out-Null
    if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) { throw "ZIP não encontrado: $zip" }
    Start-Transcript -LiteralPath $Log -Append | Out-Null
    Write-Host "[INFO] ZIP: $zip"
    Write-Host "[INFO] DESTINO: $target"
    $stage = Join-Path $env:TEMP ("alfred_real_" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Write-Host '[1/4] Expand-Archive...'
    Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
    $items = @(Get-ChildItem -LiteralPath $stage -Force)
    $source = $stage
    if ($items.Count -eq 1 -and $items[0].PSIsContainer) { $source = $items[0].FullName }
    $hasBridge = Test-Path -LiteralPath (Join-Path $source 'alfred\bridge.py')
    $hasApi = Test-Path -LiteralPath (Join-Path $source 'alfred\api.py')
    $hasStart = Test-Path -LiteralPath (Join-Path $source 'AURA_ALFRED_START.bat')
    if (-not $hasBridge -or -not $hasApi) {
        throw "ZIP incompleto: bridge.py=$hasBridge api.py=$hasApi start.bat=$hasStart. Conteúdo: $((Get-ChildItem -LiteralPath $source -Force | Select-Object -ExpandProperty Name) -join ', ')"
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backup = Join-Path $target "backups\alfred_real_$stamp"
    Write-Host "[2/4] Backup: $backup"
    $backupNames = @('alfred','config\alfred.json','requirements-alfred.txt','AURA_ALFRED_INSTALL.bat','AURA_ALFRED_START.bat','AURA_ALFRED_STOP.bat','AURA_ALFRED_STATUS.bat','AURA_ALFRED_ROLLBACK.bat','FINALIZAR_AURA_ALFRED_QWEN3.bat','README_ALFRED_COMPLETO.md')
    foreach ($rel in $backupNames) {
        $old = Join-Path $target $rel
        if (Test-Path -LiteralPath $old) {
            $dest = Join-Path $backup $rel
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
            Copy-Item -LiteralPath $old -Destination $dest -Recurse -Force
        }
    }
    Write-Host '[3/4] Copiar código para C:\aura...'
    Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
    foreach ($rel in @('alfred\bridge.py','alfred\api.py','config\alfred.json','requirements-alfred.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $target $rel))) { throw "Instalação incompleta: falta $rel" }
    }
    Write-Host '[4/4] Validação concluída.'
    Write-Host "[OK] Alfred completo instalado em $target"
    Write-Host "[INFO] Backup: $backup"
    exit 0
}
catch {
    Write-Host '[ERRO] A instalação falhou:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    exit 1
}
finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    try { Stop-Transcript | Out-Null } catch {}
}
