@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title AURA SILENT INSTALL
color 0A

set "ROOT=%CD%"
set "LOGDIR=%ROOT%\logs_supervisor"
set "LOG=%LOGDIR%\silent_install.log"
set "VENV=%ROOT%\engine\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPIP=%VENV%\Scripts\pip.exe"
set "FAIL=0"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ==== SILENT INSTALL %DATE% %TIME% ROOT=%ROOT% > "%LOG%"

set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "GLM_ADVISORY_ONLY=true"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "PYTHONUTF8=1"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge;%ROOT%\hermes_v10"
if not defined AURA_JARVIS_MODEL set "AURA_JARVIS_MODEL=qwen2.5:3b-instruct"
if not defined AURA_OLLAMA_MODEL set "AURA_OLLAMA_MODEL=qwen2.5:3b-instruct"

echo [1/7] STOP
echo [1/7] STOP >> "%LOG%"
for %%P in (8080 8765 8777 8099 8790) do for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":%%P" ^| findstr "LISTENING"') do taskkill /F /PID %%A >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/7] AUDIT
echo [2/7] AUDIT >> "%LOG%"
if not exist "%ROOT%\engine\server.py" goto :ERR_ENGINE
if not exist "%ROOT%\bridge\server.py" goto :ERR_BRIDGE
if exist "%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py" goto :AUDIT_OK
if exist "%ROOT%\scripts\hermes_v10_chat_api.py" goto :AUDIT_OK
goto :ERR_HERMES
:AUDIT_OK
echo OK ficheiros >> "%LOG%"

echo [3/7] PYTHON
echo [3/7] PYTHON >> "%LOG%"
set "PYBASE="
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYBASE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYBASE if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYBASE=%LocalAppData%\Programs\Python\Python310\python.exe"
if not defined PYBASE for /f "delims=" %%I in ('where python 2^>nul') do if not defined PYBASE set "PYBASE=%%I"
if not defined PYBASE goto :ERR_PYTHON
"%PYBASE%" -c "import sys;v=sys.version_info;raise SystemExit(0 if v.major==3 and v.minor in (10,11) else 1)" >> "%LOG%" 2>&1
if errorlevel 1 goto :ERR_PYVER
echo PYBASE=%PYBASE% >> "%LOG%"

echo [4/7] VENV
echo [4/7] VENV >> "%LOG%"
if exist "%VENV%" rmdir /s /q "%VENV%" >> "%LOG%" 2>&1
"%PYBASE%" -m venv "%VENV%" >> "%LOG%" 2>&1
if not exist "%VPY%" goto :ERR_VENV
"%VPY%" -m pip install -q --upgrade pip wheel setuptools >> "%LOG%" 2>&1

echo [5/7] DEPS
echo [5/7] DEPS >> "%LOG%"
if exist "%ROOT%\engine\requirements.txt" "%VPIP%" install -q -r "%ROOT%\engine\requirements.txt" >> "%LOG%" 2>&1
if not exist "%ROOT%\engine\requirements.txt" if exist "%ROOT%\requirements.txt" "%VPIP%" install -q -r "%ROOT%\requirements.txt" >> "%LOG%" 2>&1
if not exist "%ROOT%\engine\requirements.txt" if not exist "%ROOT%\requirements.txt" "%VPIP%" install -q fastapi "uvicorn[standard]" httpx requests pydantic psutil aiofiles structlog prometheus-client pywin32 plyer >> "%LOG%" 2>&1
"%VPIP%" install -q plyer fastapi "uvicorn[standard]" httpx pydantic aiofiles websockets >> "%LOG%" 2>&1

echo [6/7] START
echo [6/7] START >> "%LOG%"

start "AURA-Bridge" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& %VPY% -u bridge\server.py --host 127.0.0.1 --port 8080 >> %LOGDIR%\bridge.log 2>&1"

start "AURA-Engine" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_EXECUTION_ALLOWED=0&& set GLM_ADVISORY_ONLY=true&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine&& %VPY% -u engine\server.py --host 127.0.0.1 --port 8765 >> %LOGDIR%\engine.log 2>&1"

if exist "%ROOT%\scripts\aura_serve_matriz.py" start "AURA-Matriz" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& %VPY% -u scripts\aura_serve_matriz.py >> %LOGDIR%\matriz8766.log 2>&1"

if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" goto :HERMES_ULTRA
goto :HERMES_FALLBACK

:HERMES_ULTRA
call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg >> "%LOG%" 2>&1
goto :AFTER_HERMES

:HERMES_FALLBACK
start "AURA-Hermes" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%&& set AURA_JARVIS_MODEL=%AURA_JARVIS_MODEL%&& set AURA_OLLAMA_MODEL=%AURA_OLLAMA_MODEL%&& %VPY% -u scripts\hermes_v10_chat_api.py >> %LOGDIR%\hermes_v10.log 2>&1"

:AFTER_HERMES
if exist "%ROOT%\AURA_TOOLS_CONTROL_API.bat" start "AURA-Control" /MIN cmd /c "cd /d %ROOT% && call AURA_TOOLS_CONTROL_API.bat"

echo [7/7] HEALTH
echo [7/7] HEALTH >> "%LOG%"
set "B=0"
set "E=0"
set "H=0"
for /L %%I in (1,1,20) do (
  powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1 && set "B=1"
  powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1 && set "E=1"
  powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8777/health' -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1 && set "H=1"
  if "!B!"=="1" if "!E!"=="1" if "!H!"=="1" goto :HEALTH_DONE
  timeout /t 2 /nobreak >nul
)
:HEALTH_DONE

echo.
echo ========== RESULTADO ==========
if "!B!"=="1" (echo Bridge  OK  :8080) else (echo Bridge  OFF :8080& set FAIL=1)
if "!E!"=="1" (echo Engine  OK  :8765) else (echo Engine  OFF :8765& set FAIL=1)
if "!H!"=="1" (echo Hermes  OK  :8777) else (echo Hermes  OFF :8777& set FAIL=1)
echo Log: %LOG%
echo Bridge !B! Engine !E! Hermes !H! >> "%LOG%"
if "!FAIL!"=="0" goto :OK
goto :FAIL

:ERR_ENGINE
echo FALHA engine server.py
echo FALHA engine >> "%LOG%"
set FAIL=1
goto :FAIL
:ERR_BRIDGE
echo FALHA bridge server.py
echo FALHA bridge >> "%LOG%"
set FAIL=1
goto :FAIL
:ERR_HERMES
echo FALHA hermes chat_api
echo FALHA hermes >> "%LOG%"
set FAIL=1
goto :FAIL
:ERR_PYTHON
echo FALHA Python 3.10/3.11
echo FALHA python >> "%LOG%"
set FAIL=1
goto :FAIL
:ERR_PYVER
echo FALHA versao Python
echo FALHA pyver >> "%LOG%"
set FAIL=1
goto :FAIL
:ERR_VENV
echo FALHA venv
echo FALHA venv >> "%LOG%"
set FAIL=1
goto :FAIL

:OK
echo STATUS: OK
start "" "http://127.0.0.1:8777/chat" >nul 2>&1
exit /b 0

:FAIL
echo STATUS: FALHAS - ver %LOG%
echo Ver tambem logs_supervisor\hermes_v10.log
echo.
echo [AURA] Erro acima. Janela mantida.
pause
exit /b 1

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
