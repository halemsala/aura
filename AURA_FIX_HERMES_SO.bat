@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AURA FIX HERMES
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo STOP 8777
for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":8777" ^| findstr "LISTENING"') do taskkill /F /PID %%A >nul 2>&1
timeout /t 1 /nobreak >nul

echo START Hermes
if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" goto :ULTRA
goto :FB

:ULTRA
call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
goto :CHK

:FB
start "AURA-Hermes" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& %VPY% -u scripts\hermes_v10_chat_api.py >> %LOGDIR%\hermes_v10.log 2>&1"
timeout /t 5 /nobreak >nul

:CHK
powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8777/health' -TimeoutSec 5|Out-Null; Write-Host Hermes_OK}catch{Write-Host Hermes_OFF}"
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
