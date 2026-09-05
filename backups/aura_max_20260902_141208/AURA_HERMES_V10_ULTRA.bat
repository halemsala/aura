@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%CD%"
set "PKG=%ROOT%\hermes_v10"
set "VENV_PY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=python"
if not exist "%PKG%\scripts\hermes_v10_chat_api.py" (echo [FATAL] hermes_v10 em falta & exit /b 1)
set "MODE=%~1"
if not defined MODE set "MODE=bg"
echo [Hermes V10] Python=%VENV_PY% mode=!MODE!
"%VENV_PY%" -m pip install --disable-pip-version-check -q fastapi "uvicorn[standard]" pydantic httpx structlog prometheus-client python-dotenv pyyaml aiofiles websockets numpy scikit-learn psutil 2>nul
set "PYTHONPATH=%PKG%;%ROOT%"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
if /I "!MODE!"=="bg" (
  powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
  if not errorlevel 1 (
    echo Hermes ja em :8777 — skip restart para o chat nao cair
    start "" http://127.0.0.1:8777/chat
    goto :eof
  )
  start "AURA-Hermes-Chat" /MIN cmd /c "cd /d %PKG% & set AURA_ROOT=%ROOT%& set PYTHONPATH=%PKG%;%ROOT%& set PAPER_TRADE=true& set EXECUTION_ALLOWED=false& set PYTHONUTF8=1& %VENV_PY% -u scripts\hermes_v10_chat_api.py >> %ROOT%\logs_supervisor\hermes_v10.log 2>&1"
  timeout /t 3 >nul
  start "" http://127.0.0.1:8777/chat
  echo Hermes Chat em background :8777
  echo Log: logs_supervisor\hermes_v10.log
  goto :eof
)
if /I "!MODE!"=="chat" (
  start "" http://127.0.0.1:8777/chat
  cd /d "%PKG%"
  "%VENV_PY%" -u scripts\hermes_v10_chat_api.py
  goto :eof
)
if /I "!MODE!"=="dash" (
  start "" http://127.0.0.1:8778/
  cd /d "%PKG%"
  "%VENV_PY%" -u dashboard\hermes_dashboard_ultra.py
  goto :eof
)
:: ultra = bg chat + try dash
start "AURA-Hermes-Dash" /MIN cmd /c "cd /d %PKG% && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%PKG%;%ROOT%&& set PYTHONUTF8=1&& %VENV_PY% -u dashboard\hermes_dashboard_ultra.py >> %ROOT%\logs_supervisor\hermes_dash.log 2>&1"
start "AURA-Hermes-Chat" /MIN cmd /c "cd /d %PKG% & set AURA_ROOT=%ROOT%& set PYTHONPATH=%PKG%;%ROOT%& set PAPER_TRADE=true& set EXECUTION_ALLOWED=false& set PYTHONUTF8=1& %VENV_PY% -u scripts\hermes_v10_chat_api.py >> %ROOT%\logs_supervisor\hermes_v10.log 2>&1"
timeout /t 3 >nul
start "" http://127.0.0.1:8777/chat
start "" http://127.0.0.1:8778/
echo Hermes ultra em background
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
