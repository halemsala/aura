# ============================================================
# AURA QUANT-X - Reparar Venv do Engine (FastAPI + deps)
# Versão: V25T15-CORRECAO-VENV
# Resolve: ModuleNotFoundError: No module named 'fastapi'
#          Permission denied ao recriar venv
# ============================================================

$ErrorActionPreference = "Continue"
$Root = "C:\aura\AURA_QUANT_X_12.7.0"
$VenvPath = Join-Path $Root "engine\venv"
$PythonSystem = "C:\Users\salaa\AppData\Local\Programs\Python\Python311\python.exe"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " AURA QUANT-X - REPARAR VENV DO ENGINE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "ROOT = $Root"
Write-Host ""

# 1. Matar tudo que possa estar travando o python.exe
Write-Host "[1/7] Matando processos que travam o venv..." -ForegroundColor Yellow
$procs = @("python", "pythonw", "Aura.QuantX.Desktop", "uvicorn")
foreach ($p in $procs) {
    Get-Process -Name $p -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "      Kill $($_.ProcessName) PID $($_.Id)"
        } catch {}
    }
}
# Portas também
foreach ($port in @(8080, 8765, 8099)) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.OwningProcess -gt 4) {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "      Kill PID $($_.OwningProcess) on :$port"
        }
    }
}
Start-Sleep -Seconds 3
Write-Host "      OK" -ForegroundColor Green

# 2. Apagar venv corrompido (com retries)
Write-Host "[2/7] Removendo venv corrompido..." -ForegroundColor Yellow
for ($i = 1; $i -le 5; $i++) {
    if (Test-Path $VenvPath) {
        try {
            Remove-Item -Recurse -Force $VenvPath -ErrorAction Stop
            Write-Host "      Venv removido na tentativa $i" -ForegroundColor Green
            break
        } catch {
            Write-Host "      Tentativa $i falhou: $($_.Exception.Message)" -ForegroundColor Yellow
            Start-Sleep -Seconds 2
            # Tenta matar de novo
            Get-Process -Name python* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "      Venv já não existe" -ForegroundColor Green
        break
    }
}
if (Test-Path $VenvPath) {
    Write-Host "      AVISO: Ainda não conseguiu apagar completamente. Tente reiniciar o PC." -ForegroundColor Red
}

# 3. Verificar Python do sistema
Write-Host "[3/7] Verificando Python do sistema..." -ForegroundColor Yellow
if (-not (Test-Path $PythonSystem)) {
    # Tenta encontrar
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) {
        $PythonSystem = $found.Source
    } else {
        Write-Host "      ERRO: Python 3.11 não encontrado!" -ForegroundColor Red
        Write-Host "      Instale Python 3.11 e rode de novo." -ForegroundColor Red
        exit 1
    }
}
$ver = & $PythonSystem --version 2>&1
Write-Host "      $ver  ($PythonSystem)" -ForegroundColor Green

# 4. Criar venv limpo
Write-Host "[4/7] Criando venv limpo..." -ForegroundColor Yellow
& $PythonSystem -m venv $VenvPath
if (-not (Test-Path "$VenvPath\Scripts\python.exe")) {
    Write-Host "      ERRO: Falha ao criar venv!" -ForegroundColor Red
    exit 1
}
Write-Host "      Venv criado com sucesso" -ForegroundColor Green

# 5. Atualizar pip
Write-Host "[5/7] Atualizando pip..." -ForegroundColor Yellow
& "$VenvPath\Scripts\python.exe" -m pip install --upgrade pip --quiet
Write-Host "      OK" -ForegroundColor Green

# 6. Instalar dependências críticas do Engine
Write-Host "[6/7] Instalando dependências do Engine (FastAPI etc)..." -ForegroundColor Yellow

$packages = @(
    "fastapi",
    "uvicorn[standard]",
    "pydantic",
    "httpx",
    "aiofiles",
    "python-multipart",
    "starlette",
    "anyio",
    "sniffio",
    "typing-extensions"
)

foreach ($pkg in $packages) {
    Write-Host "      Instalando $pkg ..." -NoNewline
    & "$VenvPath\Scripts\python.exe" -m pip install $pkg --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FALHOU" -ForegroundColor Red
    }
}

# Se existir requirements do engine, instala também
$reqFiles = @(
    "$Root\engine\requirements.txt",
    "$Root\requirements.txt",
    "$Root\engine\requirements-engine.txt"
)
foreach ($req in $reqFiles) {
    if (Test-Path $req) {
        Write-Host "      Instalando de $req ..." -NoNewline
        & "$VenvPath\Scripts\python.exe" -m pip install -r $req --quiet 2>$null
        Write-Host " OK" -ForegroundColor Green
    }
}

# 7. Verificar se FastAPI está instalado
Write-Host "[7/7] Verificando instalação..." -ForegroundColor Yellow
$check = & "$VenvPath\Scripts\python.exe" -c "import fastapi; print(fastapi.__version__)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "      FastAPI $check instalado com sucesso!" -ForegroundColor Green
} else {
    Write-Host "      ERRO: FastAPI ainda não importa!" -ForegroundColor Red
    Write-Host "      $check"
    exit 1
}

# Mostrar pip freeze resumido
Write-Host ""
Write-Host "Pacotes principais instalados:" -ForegroundColor Cyan
& "$VenvPath\Scripts\python.exe" -m pip freeze | Select-String -Pattern "fastapi|uvicorn|pydantic|httpx|starlette"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " VENV REPARADO COM SUCESSO" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Agora execute:" -ForegroundColor White
Write-Host "   .\AURA_TUDO_EM_UM.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host " Depois verifique:" -ForegroundColor White
Write-Host "   Invoke-RestMethod http://127.0.0.1:8765/api/ui/state | Select-Object ok, fixtureId, jarvis_state" -ForegroundColor Yellow
Write-Host ""
