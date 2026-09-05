@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA REPARAR SISTEMA (paper-only)
color 0A

set "ROOT=%CD%"
if not exist "%ROOT%\engine\server.py" (
  echo [ERRO] engine\server.py ausente. Extraia o ZIP para C:\aura
  pause
  exit /b 1
)

set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_PAPER_TRADE=1"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "GLM_ADVISORY_ONLY=true"
set "AURA_GLM_ENABLED=0"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge;%ROOT%\hermes_v10"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"

set "VENV_PY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [AVISO] engine\venv ausente. Rode AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat
  echo         Este reparo nao recria venv nem mata Ollama.
  pause
  exit /b 2
)

"%VENV_PY%" -c "import sys; v=sys.version_info; raise SystemExit(0 if v[:2] in ((3,10),(3,11)) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] venv nao e Python 3.10/3.11
  pause
  exit /b 3
)

echo [reparo] paper_trade=true execution_allowed=false
echo [reparo] Bridge :8080 Engine :8765 Voice :8099 Matriz :8766
echo.

powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if errorlevel 1 (
  start "AURA-Bridge" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_PAPER_TRADE=1&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u bridge\server.py --host 127.0.0.1 --port 8080 >> "%LOGDIR%\bridge.log" 2>&1"
) else (
  echo   Bridge ja UP
)

powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if errorlevel 1 (
  start "AURA-Engine" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_PAPER_TRADE=1&& set AURA_EXECUTION_ALLOWED=0&& set AURA_UNLOCK_LIVE=0&& set GLM_ADVISORY_ONLY=true&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u engine\server.py --host 127.0.0.1 --port 8765 >> "%LOGDIR%\engine.log" 2>&1"
) else (
  echo   Engine ja UP
)

if exist "%ROOT%\bridge\jarvis_voice_server.py" (
  powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8099/api/voice/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
  if errorlevel 1 (
    start "AURA-Voice" /MIN cmd /c "cd /d %ROOT% && set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%LOGDIR%\voice.log" 2>&1"
  ) else (
    echo   Voice ja UP
  )
)

powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8766/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if errorlevel 1 (
  start "AURA-Matriz-8766" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u scripts\aura_serve_matriz.py >> "%LOGDIR%\matriz8766.log" 2>&1"
) else (
  echo   Matriz ja UP
)

echo.
echo Reparo disparado. Logs: %LOGDIR%
echo Nunca desligue paper_trade para "destravar".
if /I "%~1"=="NOPAUSE" goto :AURA_EOF
pause
:AURA_EOF
endlocal
