@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA REBUILD HERMES V10
color 0B

set "ROOT=%CD%"
if not exist "%ROOT%\hermes_v10\core\hermes_llm_engine.py" (
  echo [ERRO] hermes_v10\core incompleto. Extraia o ZIP COMPLETO para C:\aura
  pause
  exit /b 1
)
if not exist "%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py" (
  echo [ERRO] hermes_v10\scripts\hermes_v10_chat_api.py ausente
  pause
  exit /b 1
)

set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\hermes_rebuild.log"
echo ==== %DATE% %TIME% REBUILD HERMES ROOT=%ROOT% ====>> "%LOG%"

echo [1/6] Liberar porta 8777...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue | ForEach-Object { if($_.OwningProcess -gt 4){ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue } }" >> "%LOG%" 2>&1
timeout /t 2 /nobreak >nul

echo [2/6] Detectar Python 3.10/3.11 (venv preferido)...
set "VPY="
if exist "%ROOT%\engine\venv\Scripts\python.exe" set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not defined VPY if exist "%ROOT%\hermes_v10\venv\Scripts\python.exe" set "VPY=%ROOT%\hermes_v10\venv\Scripts\python.exe"
if not defined VPY (
  where py >nul 2>&1 && (
    py -3.11 -c "import sys" >nul 2>&1 && set "VPY=py -3.11"
  )
)
if not defined VPY (
  where py >nul 2>&1 && (
    py -3.10 -c "import sys" >nul 2>&1 && set "VPY=py -3.10"
  )
)
if not defined VPY set "VPY=python"

echo       Python launcher: %VPY%
%VPY% -c "import sys; v=sys.version_info; assert v[:2] in ((3,10),(3,11)), v; print('OK',sys.version)" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Precisa Python 3.10 ou 3.11. Nao use 3.12+.
  pause
  exit /b 2
)

echo [3/6] Garantir venv engine...
if not exist "%ROOT%\engine\venv\Scripts\python.exe" (
  echo       Criando engine\venv ...
  %VPY% -m venv "%ROOT%\engine\venv" >> "%LOG%" 2>&1
)
set "VENV_PY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERRO] venv nao criado
  pause
  exit /b 3
)

echo [4/6] Instalar deps minimas Hermes no venv...
"%VENV_PY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
if exist "%ROOT%\hermes_v10\requirements-minimal.txt" (
  "%VENV_PY%" -m pip install -r "%ROOT%\hermes_v10\requirements-minimal.txt" >> "%LOG%" 2>&1
) else if exist "%ROOT%\hermes_v10\requirements.txt" (
  "%VENV_PY%" -m pip install -r "%ROOT%\hermes_v10\requirements.txt" >> "%LOG%" 2>&1
)
if exist "%ROOT%\engine\requirements.txt" (
  "%VENV_PY%" -m pip install -r "%ROOT%\engine\requirements.txt" >> "%LOG%" 2>&1
)

echo [5/6] Preflight import core...
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%\hermes_v10;%ROOT%;%ROOT%\hermes_v10\scripts"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
"%VENV_PY%" -c "import sys; sys.path.insert(0,r'%ROOT%\hermes_v10'); from core.hermes_llm_engine import HermesLLMEngine; print('core OK')" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [AVISO] Import core falhou — Hermes sobe em modo degradado se soft-import ativo. Veja %LOG%
)

echo [6/6] Subir Hermes via AURA_RUN_HERMES.py ...
start "AURA-Hermes-Rebuild" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& set HERMES_API_PORT=8777&& "%VENV_PY%" -u AURA_RUN_HERMES.py >> "%LOGDIR%\hermes_v10.log" 2>&1"

echo Aguardando health :8777 ...
set "H=OFF"
for /L %%i in (1,1,25) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8777/health' -UseBasicParsing -TimeoutSec 2|Out-Null; 'OK'}catch{'OFF'}" > "%TEMP%\hermes_h.txt" 2>nul
  set /p H=<"%TEMP%\hermes_h.txt"
  if /I "!H!"=="OK" goto :OK
  timeout /t 2 /nobreak >nul
)

echo [FALHA] Hermes nao respondeu em :8777
echo Veja: %LOGDIR%\hermes_v10.log
echo       %LOG%
type "%LOGDIR%\hermes_v10.log" | more
pause
exit /b 1

:OK
echo [OK] Hermes ON  http://127.0.0.1:8777/chat
echo      Health     http://127.0.0.1:8777/health
echo      API        http://127.0.0.1:8777/api/system
echo.
if /I "%~1"=="NOPAUSE" goto :EOF
pause
endlocal
