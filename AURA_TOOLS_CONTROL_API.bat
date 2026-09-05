@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Control API :8790
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "AURA_ROOT=%ROOT%"
set "PYTHONUTF8=1"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"

powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8790 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if not errorlevel 1 (
  echo Control API ja em :8790
  curl -s http://127.0.0.1:8790/health
  echo.
  goto FIM
)

if not exist "%ROOT%\scripts\aura_tools_control_api.py" (
  echo [ERRO] scripts\aura_tools_control_api.py ausente
  pause
  exit /b 1
)

echo [START] Control API :8790
REM aspas corretas — o BAT antigo partia o start com "%ROOT%" aninhado
start "AURA-Control-API" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u scripts\aura_tools_control_api.py"

timeout /t 3 /nobreak >nul
echo.
curl -s http://127.0.0.1:8790/health
echo.
echo Se vazio: veja a janela AURA-Control-API (traceback).
echo Depois no hub: Atualizar tudo
echo   http://127.0.0.1:8766/tools-hub.html
:FIM
if /I "%~1"=="NOPAUSE" goto :EOF
pause
endlocal
