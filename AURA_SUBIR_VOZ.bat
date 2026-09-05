@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "AURA_ROOT=%ROOT%"
set "PYTHONUTF8=1"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"

powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8099 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if not errorlevel 1 (
  echo Voice ja em :8099
  goto FIM
)

if not exist "%ROOT%\bridge\jarvis_voice_server.py" (
  echo [AVISO] bridge\jarvis_voice_server.py em falta
  goto FIM
)

echo [Voice :8099]
start "AURA-Voice" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VPY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%ROOT%\logs_supervisor\voice.log" 2>&1"
timeout /t 3 >nul
:FIM
endlocal
