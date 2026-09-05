[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [string]$ChecksumPath = "",

    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "AURA_QUANT_X\portable"),

    [switch]$InstallDependencies,

    [switch]$InstallVoiceDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# O checksum do ZIP deve ser fornecido em arquivo externo. Não embuta o hash
# do próprio ZIP no pacote, pois isso criaria uma autorreferência impossível.
$ExpectedPolicySha256 = "c15cdaaae945dcf833755a3800f90327d69100ebb6110a69d0f7de02f46bfec2"

function Stop-Safely([string]$Message) {
    throw "AURA instalação interrompida: $Message"
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

$resolvedZip = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
Require-File $resolvedZip "ZIP"

if ([string]::IsNullOrWhiteSpace($ChecksumPath)) {
    $candidate = "$resolvedZip.sha256"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $ChecksumPath = $candidate
    } else {
        Stop-Safely "arquivo de checksum externo é obrigatório"
    }
}

Require-File $ChecksumPath "arquivo de checksum"
$checksumLine = Get-Content -LiteralPath $ChecksumPath -Raw
$declaredHash = (($checksumLine -split "\s+") | Where-Object { $_ -match "^[0-9a-fA-F]{64}$" } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($declaredHash)) {
    Stop-Safely "checksum sem SHA-256 válido"
}

$actualHash = (Get-FileHash -LiteralPath $resolvedZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $declaredHash.ToLowerInvariant()) {
    Stop-Safely "SHA-256 inválido. Esperado=$declaredHash; calculado=$actualHash"
}
Write-Host "[OK] SHA-256 do ZIP confirmado: $actualHash"

$stage = Join-Path ([IO.Path]::GetTempPath()) ("AURA_QUANT_X_STAGE_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage -Force | Out-Null

try {
    Expand-Archive -LiteralPath $resolvedZip -DestinationPath $stage -Force

    $requiredDirectories = @(
        "config",
        "docs",
        "scripts",
        "engine\core\capture",
        "engine\agents",
        "engine\contracts",
        "engine\analytics",
        "engine\alerts",
        "engine\ingestion",
        "engine\aura_ai_one",
        "bridge\auth",
        "desktop\capture",
        "desktop\config",
        "desktop\packaging",
        "desktop\ui\matriz_v22",
        "interface\aura-quant-x-dashboard\client\src\components",
        "interface\aura-quant-x-dashboard\shared",
        "interface\aura-quant-x-dashboard\server",
        "skills\aura-spec-driven-engineering\references",
        "skills\typescript-contracts-matt-pocock\references"
    )

    foreach ($directory in $requiredDirectories) {
        $path = Join-Path $stage $directory
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    Write-Host "[OK] Estrutura de pastas criada/confirmada"

    $policyPath = Join-Path $stage "engine\core\capture\policy.py"
    Require-File $policyPath "policy.py"
    $policyHash = (Get-FileHash -LiteralPath $policyPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($policyHash -ne $ExpectedPolicySha256) {
        Stop-Safely "policy.py diverge do contrato validado; assert_safety_invariants não será alterada"
    }
    $safetyFunction = Select-String -LiteralPath $policyPath -Pattern "def assert_safety_invariants" -SimpleMatch
    if (-not $safetyFunction) {
        Stop-Safely "assert_safety_invariants não encontrada"
    }
    Write-Host "[OK] policy.py e assert_safety_invariants preservadas: $policyHash"

    Require-File (Join-Path $stage "AURA_FULL_INSTALL.md") "manifesto de instalação"
    Require-File (Join-Path $stage "scripts\aura_package_precheck.py") "precheck"
    Require-File (Join-Path $stage "engine\aura_ai_one\adapter.py") "adapter AURA IA One"
    Require-File (Join-Path $stage "engine\agents\aura_hermes_router.py") "roteador AURA IA One/Hermes"
    Require-File (Join-Path $stage "skills\aura-spec-driven-engineering\SKILL.md") "skill Spec-Driven"
    Require-File (Join-Path $stage "skills\typescript-contracts-matt-pocock\SKILL.md") "skill TypeScript"

    if (Test-Path -LiteralPath $InstallRoot) {
        Stop-Safely "destino já existe: $InstallRoot. Escolha uma pasta nova ou faça rollback controlado antes de repetir"
    }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $stage -Force | Copy-Item -Destination $InstallRoot -Recurse -Force
    Write-Host "[OK] Pacote extraído em $InstallRoot"

    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    $pythonArgs = @("-3")
    if (-not $pythonLauncher) {
        $pythonLauncher = Get-Command python -ErrorAction SilentlyContinue
        $pythonArgs = @()
    }
    if (-not $pythonLauncher) {
        Stop-Safely "Python 3 não encontrado"
    }
    $venvPath = Join-Path $InstallRoot "engine\venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    $venvConfig = Join-Path $venvPath "pyvenv.cfg"
    $venvReady = (Test-Path -LiteralPath $venvPython -PathType Leaf) -and (Test-Path -LiteralPath $venvConfig -PathType Leaf)

    if (-not $venvReady) {
        if (Test-Path -LiteralPath $venvPath) {
            Write-Host "[INFO] engine\\venv incompleta; removendo somente essa venv para recriação"
            Remove-Item -LiteralPath $venvPath -Recurse -Force -ErrorAction Stop
        }
        & $pythonLauncher.Source @pythonArgs -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely "falha ao criar engine\\venv"
        }
    } else {
        Write-Host "[OK] engine\\venv existente e íntegra"
    }

    Require-File $venvPython "Python da venv"
    Require-File $venvConfig "pyvenv.cfg da venv"
    & $venvPython -I -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "Python da venv não executa; a venv será considerada inválida"
    }
    Write-Host "[OK] engine\\venv pronta e executável"

    $pipInstallArgs = @("--disable-pip-version-check", "--no-input", "--no-cache-dir")
    if ($InstallDependencies) {
        $requirements = Join-Path $InstallRoot "requirements.txt"
        if (Test-Path -LiteralPath $requirements -PathType Leaf) {
            & $venvPython -m pip install @pipInstallArgs -r $requirements
            if ($LASTEXITCODE -ne 0) {
                Stop-Safely "falha ao instalar requirements.txt"
            }
        }
        & $venvPython -m pip install @pipInstallArgs pytest
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely "falha ao instalar pytest"
        }
        Write-Host "[OK] Dependências base e pytest instalados sem usar cache global"
    }
    if ($InstallVoiceDependencies) {
        $voiceRequirements = Join-Path $InstallRoot "bridge\requirements_voice.txt"
        if (Test-Path -LiteralPath $voiceRequirements -PathType Leaf) {
            & $venvPython -m pip install @pipInstallArgs -r $voiceRequirements
            if ($LASTEXITCODE -ne 0) {
                Stop-Safely "falha ao instalar requirements_voice.txt"
            }
            Write-Host "[OK] Dependências de voz explicitamente solicitadas instaladas"
        } else {
            Stop-Safely "requirements_voice.txt ausente"
        }
    }

    $env:PYTHONPATH = $InstallRoot
    $unitTests = @(Get-ChildItem -LiteralPath (Join-Path $InstallRoot "tests") -Filter "test_*.py" -File -ErrorAction SilentlyContinue)
    if ($unitTests.Count -eq 0) {
        Stop-Safely "nenhum arquivo tests/test_*.py encontrado"
    }
    & $venvPython -m pytest -q @($unitTests.FullName)
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "testes unitários falharam; nenhum servidor será iniciado"
    }
    Write-Host "[OK] Testes unitários tests/test_*.py aprovados"

    $env:AURA_PACKAGE_ROOT = $InstallRoot
    & $venvPython (Join-Path $InstallRoot "scripts\aura_package_precheck.py")
    if ($LASTEXITCODE -ne 0) {
        Stop-Safely "precheck falhou; nenhum servidor será iniciado"
    }
    Write-Host "[OK] Precheck aprovado"
    Write-Host "[CONCLUÍDO] Instalação Shell-only validada. Nenhum servidor foi iniciado."
    Write-Host "Para iniciar, execute somente o comando controlado definido no manifesto após revisar os logs."
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:AURA_PACKAGE_ROOT -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
