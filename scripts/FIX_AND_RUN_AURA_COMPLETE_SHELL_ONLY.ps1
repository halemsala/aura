[CmdletBinding()]
param(
    [string]$Base = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $Base -PathType Container)) {
    throw "Raiz do projeto não encontrada: $Base"
}
$Base = (Resolve-Path -LiteralPath $Base).Path
$Target = Join-Path $Base "scripts\INSTALL_AND_DIAGNOSE_AURA_COMPLETE_SHELL_ONLY.ps1"
$Validator = Join-Path $Base "scripts\VALIDATE_AURA_IN_PLACE_SHELL_ONLY.ps1"

if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
    throw "Instalador completo não encontrado: $Target"
}

function Read-Utf8([string]$Path) {
    $Encoding = New-Object System.Text.UTF8Encoding($false, $true)
    return [System.IO.File]::ReadAllText($Path, $Encoding)
}

function Save-Utf8Bom([string]$Path, [string]$Text) {
    $Encoding = New-Object System.Text.UTF8Encoding($true)
    $Normalized = $Text -replace "`r`n?", "`n"
    $WindowsText = $Normalized -replace "(?<!`r)`n", "`r`n"
    [System.IO.File]::WriteAllText($Path, $WindowsText, $Encoding)
}

function Patch-CompleteInstaller([string]$Path) {
    $Text = (Read-Utf8 $Path) -replace "`r`n?", "`n"

    $OldProbe = @'
    & $VenvPython -I -c "import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)"
'@
    $NewProbe = @'
    $VenvProbe = 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
    & $VenvPython -I -c $VenvProbe
'@
    if ($Text.Contains($OldProbe)) {
        $Text = $Text.Replace($OldProbe, $NewProbe)
    }

    $OldExecutableProbe = @'
Invoke-RequiredProcess $VenvPython @("-I", "-c", "import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)") "verificação executável da engine\\venv"
'@
    $NewExecutableProbe = @'
$VenvExecutableProbe = 'import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
Invoke-RequiredProcess $VenvPython @("-I", "-c", $VenvExecutableProbe) "verificação executável da engine\\venv"
'@
    if ($Text.Contains($OldExecutableProbe)) {
        $Text = $Text.Replace($OldExecutableProbe, $NewExecutableProbe)
    }

    if (-not $Text.Contains('$VenvProbe =')) {
        throw "Não foi possível corrigir o probe de validação da venv em $Path"
    }
    if (-not $Text.Contains('$VenvExecutableProbe =')) {
        throw "Não foi possível corrigir o probe executável da venv em $Path"
    }
    if ($Text -match '(?m)^\s*& \$VenvPython -I -c ".*SystemExit\(0 if') {
        throw "Ainda existe quoting inválido de Python no instalador completo"
    }

    if (-not $Text.Contains('venv limpa de staging')) {
        $StageFallback = @'
        try {
            Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction Stop
        } catch {
            $StageId = [Guid]::NewGuid().ToString("N")
            $Venv = Join-Path (Join-Path $Base "engine") ("venv.install." + $StageId)
            $VenvPython = Join-Path $Venv "Scripts\\python.exe"
            $VenvConfig = Join-Path $Venv "pyvenv.cfg"
            Write-Host "[WARNING] engine\\venv está bloqueada; usando venv limpa de staging: $Venv"
        }
'@
        $OldRemoveStop = '        Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction Stop'
        $OldRemoveSilent = '        Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction SilentlyContinue'
        if ($Text.Contains($OldRemoveStop)) {
            $Text = $Text.Replace($OldRemoveStop, $StageFallback.TrimEnd("`r", "`n"))
        } elseif ($Text.Contains($OldRemoveSilent)) {
            $Text = $Text.Replace($OldRemoveSilent, $StageFallback.TrimEnd("`r", "`n"))
        } else {
            throw "Não foi encontrada a remoção antiga da engine\\venv para aplicar fallback"
        }
    }
    if (-not $Text.Contains('venv limpa de staging')) {
        throw "Fallback de staging da engine\\venv não foi aplicado"
    }

    Save-Utf8Bom $Path $Text
}

function Patch-InPlaceValidator([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $Text = (Read-Utf8 $Path) -replace "`r`n?", "`n"
    $Old = @'
& $VenvPython -I -c "import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)"
'@
    $New = @'
$VenvExecutableProbe = 'import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
& $VenvPython -I -c $VenvExecutableProbe
'@
    if ($Text.Contains($Old)) {
        $Text = $Text.Replace($Old, $New)
    }
    if ($Text -match '(?m)^\s*& \$VenvPython -I -c ".*SystemExit\(0 if') {
        throw "Ainda existe quoting inválido de Python no validador in-place"
    }
    Save-Utf8Bom $Path $Text
}

Write-Host "[INFO] Corrigindo quoting PowerShell/Python e codificação UTF-8..."
Patch-CompleteInstaller $Target
Patch-InPlaceValidator $Validator
Write-Host "[OK] Instalador corrigido: $Target"

$PowerShellHost = Get-Command powershell.exe -ErrorAction SilentlyContinue
if (-not $PowerShellHost) {
    $PowerShellHost = Get-Command pwsh -ErrorAction SilentlyContinue
}
if (-not $PowerShellHost) {
    throw "powershell.exe/pwsh não encontrado no PATH"
}

Write-Host "[INFO] Executando instalação completa e diagnósticos..."
Write-Host "[INFO] Nenhum Engine, Bridge, Voice, Ollama ou servidor será iniciado."
& $PowerShellHost.Source -NoProfile -ExecutionPolicy Bypass -File $Target -Base $Base
$ResultCode = $LASTEXITCODE

if ($ResultCode -ne 0) {
    throw "Instalação/diagnóstico falhou com código $ResultCode. Nenhum servidor será iniciado."
}

Write-Host "[CONCLUÍDO] Instalação completa e diagnósticos aprovados."
Write-Host "[CONCLUÍDO] Nenhum servidor foi iniciado."
