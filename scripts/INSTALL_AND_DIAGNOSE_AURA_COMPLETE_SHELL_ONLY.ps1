[CmdletBinding()]
param(
    [string]$Base = (Get-Location).Path,

    [switch]$SkipDesktopPublish,

    [switch]$SkipVoiceDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedPolicySha256 = "c15cdaaae945dcf833755a3800f90327d69100ebb6110a69d0f7de02f46bfec2"
$DiagnosticResults = [System.Collections.Generic.List[object]]::new()

function Stop-Safely([string]$Message) {
    throw "AURA instalação/diagnóstico interrompido: $Message"
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

function Add-Diagnostic([string]$Name, [bool]$Passed, [string]$Detail) {
    $status = if ($Passed) { "PASS" } else { "FAIL" }
    $DiagnosticResults.Add([ordered]@{
        name = $Name
        status = $status
        detail = $Detail
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
    })
    Write-Host "[$status] $Name - $Detail"
}

function Invoke-RequiredProcess([string]$FilePath, [string[]]$Arguments, [string]$Label) {
    Write-Host "[INFO] $Label"
    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Stop-Safely "$Label falhou com código $code"
    }
}

function Invoke-Diagnostic([string]$Name, [string]$FilePath, [string[]]$Arguments) {
    try {
        & $FilePath @Arguments
        $code = $LASTEXITCODE
        if ($code -eq 0) {
            Add-Diagnostic $Name $true "código 0"
            return $true
        }
        Add-Diagnostic $Name $false "código $code"
        return $false
    } catch {
        Add-Diagnostic $Name $false $_.Exception.Message
        return $false
    }
}

if (-not (Test-Path -LiteralPath $Base -PathType Container)) {
    Stop-Safely "raiz do projeto ausente: $Base"
}
$Base = (Resolve-Path -LiteralPath $Base).Path
Set-Location -LiteralPath $Base

$LogDir = Join-Path $Base "logs_instalacao"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$SummaryPath = Join-Path $LogDir "install_complete_diagnostics.json"

$Policy = Join-Path $Base "engine\core\capture\policy.py"
$Precheck = Join-Path $Base "scripts\aura_package_precheck.py"
$FinalCheck = Join-Path $Base "scripts\aura_final_check.py"
$SelfTests = Join-Path $Base "scripts\run_selftests.py"
$StaticAudit = Join-Path $Base "desktop\packaging\audit_installer_static.py"
$Requirements = Join-Path $Base "requirements.txt"
$VoiceRequirements = Join-Path $Base "bridge\requirements_voice.txt"
$TestsDir = Join-Path $Base "tests"
$Venv = Join-Path $Base "engine\venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvConfig = Join-Path $Venv "pyvenv.cfg"
$PublishScript = Join-Path $Base "desktop\packaging\PUBLISH_WINDOWS.ps1"

Write-Host "============================================================"
Write-Host "AURA QUANT-X - INSTALAÇÃO COMPLETA + DIAGNÓSTICOS"
Write-Host "Raiz: $Base"
Write-Host "============================================================"
Write-Host "[INFO] Este fluxo não inicia Engine, Bridge, Voice, Ollama ou qualquer servidor."
Write-Host "[INFO] Paper Lock e assert_safety_invariants não serão alterados."

foreach ($RequiredDirectory in @(
    (Join-Path $Base "engine"),
    (Join-Path $Base "bridge"),
    (Join-Path $Base "scripts"),
    (Join-Path $Base "desktop"),
    $TestsDir
)) {
    Require-Directory $RequiredDirectory "diretório obrigatório"
}
foreach ($RequiredFile in @(
    $Policy,
    $Precheck,
    $Requirements,
    $FinalCheck,
    $SelfTests,
    $StaticAudit,
    (Join-Path $Base "engine\aura_ai_one\__init__.py"),
    (Join-Path $Base "engine\aura_ai_one\contracts.py"),
    (Join-Path $Base "engine\aura_ai_one\features.py"),
    (Join-Path $Base "engine\aura_ai_one\adapter.py"),
    (Join-Path $Base "engine\agents\aura_hermes_router.py"),
    (Join-Path $Base "engine\aura_controller.py"),
    (Join-Path $Base "engine\core\runtime_manifest.py"),
    (Join-Path $Base "engine\agents\llm_firewall.py"),
    (Join-Path $Base "config\config.root.json"),
    (Join-Path $Base "config\aura_sports_corner_profile.json")
)) {
    Require-File $RequiredFile "arquivo obrigatório"
}
if (-not $SkipVoiceDependencies) {
    Require-File $VoiceRequirements "requirements_voice.txt"
}

$PolicyHash = (Get-FileHash -LiteralPath $Policy -Algorithm SHA256).Hash.ToLowerInvariant()
if ($PolicyHash -ne $ExpectedPolicySha256) {
    Stop-Safely "policy.py diverge. Nenhuma alteração será feita. Hash atual: $PolicyHash"
}
if (-not (Select-String -LiteralPath $Policy -Pattern "def assert_safety_invariants" -SimpleMatch -Quiet)) {
    Stop-Safely "assert_safety_invariants não encontrada"
}
Add-Diagnostic "policy.py" $true "SHA-256 esperado e assert_safety_invariants presentes"
Add-Diagnostic "aura-ai-one-hermes-source" $true "módulos-fonte AURA IA One, Hermes, Golden Context e perfil de escanteios presentes"

$PyCommand = Get-Command py -ErrorAction SilentlyContinue
$PyArgs = @("-3")
if (-not $PyCommand) {
    $PyCommand = Get-Command python -ErrorAction SilentlyContinue
    $PyArgs = @()
}
if (-not $PyCommand) {
    Stop-Safely "Python 3 não encontrado no PATH"
}
Invoke-RequiredProcess $PyCommand.Source ($PyArgs + @("--version")) "verificação do Python 3"

$VenvReady = (Test-Path -LiteralPath $VenvPython -PathType Leaf) -and (Test-Path -LiteralPath $VenvConfig -PathType Leaf)
if ($VenvReady) {
    $VenvProbe = 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
    & $VenvPython -I -c $VenvProbe
    if ($LASTEXITCODE -ne 0) {
        $VenvReady = $false
    }
}
if (-not $VenvReady) {
    if (Test-Path -LiteralPath $Venv) {
        Write-Host "[INFO] Tentando remover somente engine\\venv incompleta ou inválida"
        try {
            Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction Stop
        } catch {
            $StageId = [Guid]::NewGuid().ToString("N")
            $Venv = Join-Path (Join-Path $Base "engine") ("venv.install." + $StageId)
            $VenvPython = Join-Path $Venv "Scripts\\python.exe"
            $VenvConfig = Join-Path $Venv "pyvenv.cfg"
            Write-Host "[WARNING] engine\\venv está bloqueada; usando venv limpa de staging: $Venv"
        }
    }
    Invoke-RequiredProcess $PyCommand.Source ($PyArgs + @("-m", "venv", $Venv)) "criação da venv ativa"
}
Require-File $VenvPython "Python da venv ativa"
Require-File $VenvConfig "pyvenv.cfg da venv ativa"
$VenvExecutableProbe = 'import sys; print(sys.executable); raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
Invoke-RequiredProcess $VenvPython @("-I", "-c", $VenvExecutableProbe) "verificação executável da venv ativa"
Add-Diagnostic "engine\\venv" $true "venv ativa íntegra, executável e com pyvenv.cfg: $Venv"

Invoke-RequiredProcess $VenvPython @("-m", "ensurepip", "--upgrade") "bootstrap do pip"
$PipArgs = @("--disable-pip-version-check", "--no-input", "--no-cache-dir")
Invoke-RequiredProcess $VenvPython (@("-m", "pip", "install") + $PipArgs + @("--upgrade", "pip")) "atualização segura do pip"
Invoke-RequiredProcess $VenvPython (@("-m", "pip", "install") + $PipArgs + @("-r", $Requirements)) "instalação das dependências base"
if (-not $SkipVoiceDependencies) {
    Invoke-RequiredProcess $VenvPython (@("-m", "pip", "install") + $PipArgs + @("-r", $VoiceRequirements)) "instalação das dependências completas de Voice"
}
Invoke-RequiredProcess $VenvPython (@("-m", "pip", "install") + $PipArgs + @("pytest")) "instalação do pytest"
Invoke-RequiredProcess $VenvPython @("-m", "pip", "check") "verificação de dependências instaladas"
Add-Diagnostic "pip" $true "requirements base, Voice conforme solicitado e pytest verificados"

Invoke-RequiredProcess $VenvPython @("-I", "-c", "import fastapi, uvicorn, pydantic, requests, httpx, numpy, pandas, yaml, zmq, psutil; print('AURA_BASE_IMPORTS_OK')") "importação dos módulos base"
if (-not $SkipVoiceDependencies) {
    Invoke-RequiredProcess $VenvPython @("-I", "-c", "import faster_whisper, sounddevice, edge_tts; print('AURA_VOICE_IMPORTS_OK')") "importação dos módulos Voice"
}
Add-Diagnostic "imports" $true "módulos base e Voice carregados sem iniciar serviços"

$PreviousPythonPath = $env:PYTHONPATH
$PreviousPackageRoot = $env:AURA_PACKAGE_ROOT
try {
    $env:PYTHONPATH = $Base
    $Tests = @(Get-ChildItem -LiteralPath $TestsDir -Filter "test_*.py" -File)
    if ($Tests.Count -eq 0) {
        Stop-Safely "nenhum arquivo tests/test_*.py encontrado"
    }
    Invoke-RequiredProcess $VenvPython (@("-m", "pytest", "-q") + @($Tests.FullName)) "execução de tests/test_*.py"
    Add-Diagnostic "tests/test_*.py" $true "$($Tests.Count) arquivo(s) executado(s)"

    $env:AURA_PACKAGE_ROOT = $Base
    Invoke-RequiredProcess $VenvPython @($Precheck) "execução do precheck oficial"
    Add-Diagnostic "precheck" $true "precheck oficial aprovado"
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

if ($SkipDesktopPublish) {
    Add-Diagnostic "publicação Desktop" $false "pulado explicitamente por -SkipDesktopPublish"
} else {
    $Dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
    $PowerShellHost = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if (-not $PowerShellHost) {
        $PowerShellHost = Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $Dotnet) {
        Add-Diagnostic "SDK .NET 8" $false "dotnet não encontrado; Desktop não foi publicado"
    } elseif (-not $PowerShellHost) {
        Add-Diagnostic "host PowerShell para publicação" $false "powershell.exe/pwsh não encontrado"
    } else {
        $Published = Invoke-Diagnostic "publicação Desktop sem iniciar backend" $PowerShellHost.Source @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PublishScript)
        if ($Published) {
            $PublishedExe = Join-Path $Base "desktop\publish\Aura.QuantX.Desktop.exe"
            if (Test-Path -LiteralPath $PublishedExe -PathType Leaf) {
                Add-Diagnostic "EXE Desktop publicado" $true "arquivo encontrado: $PublishedExe"
            } else {
                Add-Diagnostic "EXE Desktop publicado" $false "PUBLISH_WINDOWS terminou sem o EXE esperado"
            }
        }
    }
}

$WebView2Paths = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"),
    (Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\EdgeWebView\Application")
)
$WebView2Found = $WebView2Paths | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Select-Object -First 1
if ($WebView2Found) {
    Add-Diagnostic "WebView2 Runtime" $true "diretório encontrado: $WebView2Found"
} else {
    Add-Diagnostic "WebView2 Runtime" $false "não encontrado; o Desktop publicado exigirá o Runtime no Windows"
}

Invoke-Diagnostic "auditoria estática dos instaladores" $VenvPython @($StaticAudit)
$SelfTestsJson = Join-Path $LogDir "run_selftests_list.json"
$SelfTestsMd = Join-Path $LogDir "run_selftests_list.md"
Invoke-Diagnostic "manifesto e contratos estáticos" $VenvPython @($SelfTests, "--root", $Base, "--list", "--fail-on-missing", "--no-deps", "--json", $SelfTestsJson, "--md", $SelfTestsMd)
Invoke-Diagnostic "final check quick sem serviços" $VenvPython @($FinalCheck, "--quick")

$SummaryJson = $DiagnosticResults | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($SummaryPath, $SummaryJson, (New-Object System.Text.UTF8Encoding($false)))
$FailedDiagnostics = @($DiagnosticResults | Where-Object { $_.status -eq "FAIL" })
Write-Host "============================================================"
Write-Host "Resumo: $($DiagnosticResults.Count - $FailedDiagnostics.Count)/$($DiagnosticResults.Count) diagnósticos PASS"
Write-Host "Relatório: $SummaryPath"
Write-Host "Nenhum servidor foi iniciado."
if ($FailedDiagnostics.Count -gt 0) {
    Write-Host "[WARNING] Há diagnósticos FAIL; leia o relatório antes de qualquer inicialização."
    exit 2
}
Write-Host "[CONCLUÍDO] Instalação completa e diagnósticos aprovados."
exit 0
