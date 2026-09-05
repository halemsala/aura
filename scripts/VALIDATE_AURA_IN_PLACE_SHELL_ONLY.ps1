[CmdletBinding()]
param(
    [string]$Base = (Get-Location).Path,

    [switch]$InstallDependencies,

    [switch]$InstallVoiceDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedPolicySha256 = "c15cdaaae945dcf833755a3800f90327d69100ebb6110a69d0f7de02f46bfec2"

function Stop-Safely([string]$Message) {
    throw "AURA validação interrompida: $Message"
}

function Require-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Stop-Safely "$Label ausente: $Path"
    }
}

function Require-Directory([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Stop-Safely "$Label ausente: $Path"
    }
}

if (-not (Test-Path -LiteralPath $Base -PathType Container)) {
    Stop-Safely "raiz do projeto ausente: $Base"
}
$Base = (Resolve-Path -LiteralPath $Base).Path
Set-Location -LiteralPath $Base

$Policy = Join-Path $Base "engine\core\capture\policy.py"
$Precheck = Join-Path $Base "scripts\aura_package_precheck.py"
$TestsDir = Join-Path $Base "tests"
$Venv = Join-Path $Base "engine\venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvConfig = Join-Path $Venv "pyvenv.cfg"

foreach ($Item in @($Policy, $Precheck, $TestsDir)) {
    if (Test-Path -LiteralPath $Item -PathType Container) {
        Require-Directory $Item $Item
    } else {
        Require-File $Item $Item
    }
}

$PolicyHash = (Get-FileHash -LiteralPath $Policy -Algorithm SHA256).Hash.ToLowerInvariant()
if ($PolicyHash -ne $ExpectedPolicySha256) {
    Stop-Safely "policy.py diverge do arquivo validado. Hash atual: $PolicyHash"
}
if (-not (Select-String -LiteralPath $Policy -Pattern "def assert_safety_invariants" -SimpleMatch -Quiet)) {
    Stop-Safely "assert_safety_invariants não encontrada"
}
Write-Host "[OK] policy.py e assert_safety_invariants preservadas"

$PyCommand = Get-Command py -ErrorAction SilentlyContinue
$PyArgs = @("-3")
if (-not $PyCommand) {
    $PyCommand = Get-Command python -ErrorAction SilentlyContinue
    $PyArgs = @()
}
if (-not $PyCommand) {
    Stop-Safely "Python 3 não encontrado no PATH"
}

$VenvReady = (Test-Path -LiteralPath $VenvPython -PathType Leaf) -and (Test-Path -LiteralPath $VenvConfig -PathType Leaf)
if (-not $VenvReady) {
    if (Test-Path -LiteralPath $Venv) {
        Write-Host "[INFO] Tentando remover somente engine\\venv incompleta"
        try {
            Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction Stop
        } catch {
            $StageId = [Guid]::NewGuid().ToString("N")
            $Venv = Join-Path (Join-Path $Base "engine") ("venv.validate." + $StageId)
            $VenvPython = Join-Path $Venv "Scripts\\python.exe"
            $VenvConfig = Join-Path $Venv "pyvenv.cfg"
            Write-Host "[WARNING] engine\\venv está bloqueada; usando venv limpa de staging: $Venv"
        }
    }

    & $PyCommand.Source @PyArgs -m venv $Venv
    $VenvExitCode = $LASTEXITCODE
    if ($VenvExitCode -ne 0) {
        Stop-Safely "falha ao criar a venv ativa; código=$VenvExitCode"
    }
}

Require-File $VenvPython "Python da venv ativa"
Require-File $VenvConfig "pyvenv.cfg da venv ativa"
$VenvExecutableProbe = 'import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
& $VenvPython -I -c $VenvExecutableProbe
if ($LASTEXITCODE -ne 0) {
    Stop-Safely "engine\\venv não executa como ambiente virtual válido"
}
Write-Host "[OK] engine\\venv íntegra e executável"

$pipInstallArgs = @("--disable-pip-version-check", "--no-input", "--no-cache-dir")
if ($InstallDependencies) {
    $Requirements = Join-Path $Base "requirements.txt"
    if (Test-Path -LiteralPath $Requirements -PathType Leaf) {
        & $VenvPython -m pip install @pipInstallArgs -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely "falha em requirements.txt"
        }
    }

    & $VenvPython -m pip install @pipInstallArgs pytest
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "falha ao instalar pytest"
    }
    Write-Host "[OK] dependências base e pytest instalados sem cache global"
}

if ($InstallVoiceDependencies) {
    $VoiceRequirements = Join-Path $Base "bridge\requirements_voice.txt"
    Require-File $VoiceRequirements "requirements_voice.txt"
    & $VenvPython -m pip install @pipInstallArgs -r $VoiceRequirements
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "falha em bridge\\requirements_voice.txt"
    }
    Write-Host "[OK] dependências de voz explicitamente solicitadas instaladas"
}

$PreviousPythonPath = $env:PYTHONPATH
$PreviousPackageRoot = $env:AURA_PACKAGE_ROOT
try {
    $env:PYTHONPATH = $Base
    $Tests = @(Get-ChildItem -LiteralPath $TestsDir -Filter "test_*.py" -File)
    if ($Tests.Count -eq 0) {
        Stop-Safely "nenhum arquivo tests/test_*.py encontrado"
    }

    Write-Host "[INFO] Executando testes unitários antes de qualquer servidor..."
    & $VenvPython -m pytest -q @($Tests.FullName)
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "testes unitários falharam; nenhum servidor será iniciado"
    }
    Write-Host "[OK] testes unitários tests/test_*.py aprovados"

    $env:AURA_PACKAGE_ROOT = $Base
    Write-Host "[INFO] Executando precheck..."
    & $VenvPython $Precheck
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "precheck falhou; nenhum servidor será iniciado"
    }
    Write-Host "[OK] precheck aprovado"
    Write-Host "[CONCLUÍDO] AURA validada em $Base. Nenhum servidor foi iniciado."
} finally {
    if ($null -eq $PreviousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $PreviousPythonPath
    }
    if ($null -eq $PreviousPackageRoot) {
        Remove-Item Env:AURA_PACKAGE_ROOT -ErrorAction SilentlyContinue
    } else {
        $env:AURA_PACKAGE_ROOT = $PreviousPackageRoot
    }
}
