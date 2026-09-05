@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "LOG=%ROOT%\data\alfred\final_start.log"
if not exist "%ROOT%\data\alfred" mkdir "%ROOT%\data\alfred" >nul 2>&1

echo ================================================================
echo AURA / ALFRED / QWEN3 - ARRANQUE LIMPO
echo ================================================================
echo ROOT=%ROOT%
echo.

if not exist "%ROOT%\alfred\api.py" (
  echo [ERRO] Falta alfred\api.py.
  echo O pacote de codigo nao foi instalado correctamente em C:\aura.
  echo Log: %LOG%
  pause
  exit /b 2
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao esta no PATH.
  echo Instala Python 3.11+ ou activa o ambiente virtual do Aura.
  pause
  exit /b 3
)
python --version

echo [1/4] A verificar qwen3:8b no Ollama...
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $t=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; if(@($t.models | %% {$_.name}) -notcontains 'qwen3:8b'){throw 'qwen3:8b nao aparece em /api/tags'}; Write-Host 'qwen3:8b OK'"
if errorlevel 1 (
  echo [ERRO] Ollama/qwen3:8b nao esta disponivel.
  echo Inicia o Ollama e repete este BAT.
  pause
  exit /b 4
)

echo [2/4] A compilar os modulos Alfred...
python -m compileall -q -f alfred >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Falha de compilacao. Consulta %LOG%
  type "%LOG%"
  pause
  exit /b 5
)

if not exist "%ROOT%\data\alfred\alfred.pid" (
  echo [3/4] A iniciar API Alfred em 127.0.0.1:8791...
  start "AURA Alfred" /min cmd /c "python -m alfred.api >> data\alfred\stdout.log 2>> data\alfred\stderr.log"
  timeout /t 4 /nobreak >nul
) else (
  echo [3/4] Alfred ja possui PID registado; nao vou duplicar o processo.
)

python -m alfred.service status >> "%LOG%" 2>&1
powershell.exe -NoLogo -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8791/health' -TimeoutSec 5; if($r.StatusCode -ne 200){exit 1}; Write-Host 'ALFRED health OK' } catch { exit 1 }"
if errorlevel 1 (
  echo [ERRO] Alfred nao respondeu em /health.
  echo [INFO] Consulta data\alfred\stderr.log e %LOG%
  pause
  exit /b 6
)

echo [4/4] ALFRED ONLINE COM qwen3:8b.
echo [INFO] Chat: http://127.0.0.1:8777/chat ^(se o Hermes estiver activo^)
echo [INFO] API:  http://127.0.0.1:8791/health
echo [INFO] Log:  %LOG%
echo.
echo Nao foi aberto nenhum navegador.
echo Arranque concluido. Pressiona uma tecla para fechar.
pause >nul
exit /b 0
