@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA STACK PAPER-ONLY
color 0B

set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [ERRO] engine\venv ausente. Rode AURA_REBUILD_HERMES.bat primeiro.
  pause
  exit /b 1
)

set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge;%ROOT%\hermes_v10"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "GLM_ADVISORY_ONLY=1"
set "HERMES_REQUIRE_AUTH=0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"

if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
set "LOG=%ROOT%\logs_supervisor\stack_paper.log"
echo ==== %DATE% %TIME% STACK PAPER ROOT=%ROOT% ====>> "%LOG%"

echo ================================================================
echo  AURA STACK PAPER-ONLY
echo  Bridge:8080  Engine:8765  Hermes:8777  Control:8790
echo  paper_trade=true  execution_allowed=false
echo  Voice:8099 NAO incluida (opcional depois)
echo ================================================================
echo.

call :ensure_port 8080 "AURA-Bridge" "bridge\server.py" "--host 127.0.0.1 --port 8080"
call :ensure_port 8765 "AURA-Engine" "engine\server.py" "--host 127.0.0.1 --port 8765"
call :ensure_hermes
call :ensure_control

echo.
echo [WAIT] Health checks (ate 90s)...
set /a OKB=0 & set /a OKE=0 & set /a OKH=0 & set /a OKC=0
for /L %%i in (1,1,30) do (
  call :probe 8080 /health OKB
  call :probe 8765 /api/health OKE
  call :probe 8777 /health OKH
  call :probe 8790 /health OKC
  if !OKB!==1 if !OKE!==1 if !OKH!==1 if !OKC!==1 goto :ALL_OK
  timeout /t 3 /nobreak >nul
)

echo.
echo [AVISO] Nem todos responderam a tempo. Estado atual:
call :status
goto :END

:ALL_OK
echo.
echo [OK] Stack paper-only ONLINE
call :status
start "" "http://127.0.0.1:8766/tools-hub.html"
start "" "http://127.0.0.1:8777/chat"
goto :END

:END
echo.
echo Logs: %ROOT%\logs_supervisor\
echo   stack_paper.log  bridge/engine logs  hermes_v10.log  control_api.log
echo.
if /I "%~1"=="NOPAUSE" goto :EOF
pause
endlocal
goto :EOF

REM ---------- helpers ----------
:is_listen
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort %~1 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
exit /b %ERRORLEVEL%

:ensure_port
set "PORT=%~1"
set "TITLE=%~2"
set "SCRIPT=%~3"
set "ARGS=%~4"
call :is_listen %PORT%
if not errorlevel 1 (
  echo [SKIP] %TITLE% ja em :%PORT%
  exit /b 0
)
if not exist "%ROOT%\%SCRIPT%" (
  echo [ERRO] Falta %SCRIPT%
  exit /b 1
)
echo [START] %TITLE% :%PORT%
start "%TITLE%" cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%PYTHONPATH%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_EXECUTION_ALLOWED=0&& set PYTHONUTF8=1&& set PYTHONUNBUFFERED=1&& "%VPY%" -u %SCRIPT% %ARGS% >> "%ROOT%\logs_supervisor\%TITLE%.log" 2>&1"
timeout /t 2 /nobreak >nul
exit /b 0

:ensure_hermes
call :is_listen 8777
if not errorlevel 1 (
  echo [SKIP] Hermes ja em :8777
  exit /b 0
)
if not exist "%ROOT%\hermes_v10\AURA_RUN_HERMES.py" (
  echo [ERRO] hermes_v10\AURA_RUN_HERMES.py ausente
  exit /b 1
)
echo [START] Hermes :8777
start "AURA-Hermes" cmd /c "cd /d "%ROOT%\hermes_v10" && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set HERMES_API_PORT=8777&& set HERMES_REQUIRE_AUTH=0&& set PYTHONUTF8=1&& "%VPY%" -u AURA_RUN_HERMES.py >> "%ROOT%\logs_supervisor\hermes_v10.log" 2>&1"
timeout /t 3 /nobreak >nul
exit /b 0

:ensure_control
call :is_listen 8790
if not errorlevel 1 (
  echo [SKIP] Control API ja em :8790
  exit /b 0
)
if not exist "%ROOT%\scripts\aura_tools_control_api.py" (
  echo [ERRO] scripts\aura_tools_control_api.py ausente
  exit /b 1
)
echo [START] Control API :8790
start "AURA-Control-API" cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "%VPY%" -u scripts\aura_tools_control_api.py >> "%ROOT%\logs_supervisor\control_api.log" 2>&1"
timeout /t 2 /nobreak >nul
exit /b 0

:probe
REM %1=port %2=path %3=varname to set 1 if ok
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:%~1%~2' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if not errorlevel 1 set "%~3=1"
exit /b 0

:status
powershell -NoProfile -Command "8080,8765,8777,8790,8766,8099,11434|ForEach-Object{$c=Get-NetTCPConnection -LocalPort $_ -State Listen -EA SilentlyContinue; if($c){'  LISTEN '+$_}else{'  OFF    '+$_}}"
echo.
echo   Bridge   http://127.0.0.1:8080/health
echo   Engine   http://127.0.0.1:8765/api/health
echo   Hermes   http://127.0.0.1:8777/health
echo   Control  http://127.0.0.1:8790/health
echo   Hub      http://127.0.0.1:8766/tools-hub.html
exit /b 0
