@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA LIMPEZA + INSTALA + VERIFICA TUDO
color 0A

set "ROOT=%CD%"
if not exist "%ROOT%\engine\server.py" if exist "%ROOT%\AURA_QUANT_X_12.7.62_HERMES_FIXED\engine\server.py" set "ROOT=%ROOT%\AURA_QUANT_X_12.7.62_HERMES_FIXED"
cd /d "%ROOT%"

set "FORCE="
if /I "%~1"=="/FORCE" set "FORCE=1"

set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "MASTERLOG=%LOGDIR%\AURA_LIMPEZA_INSTALA_VERIFICA.log"
echo ==== %DATE% %TIME% LIMPEZA_INSTALA_VERIFICA ROOT=%ROOT% FORCE=%FORCE% ====>> "%MASTERLOG%"

echo ================================================================
echo  AURA — LIMPEZA + INSTALA + VERIFICA TODOS OS SERVICOS
echo  paper_trade=true  execution_allowed=false  GLM_ADVISORY_ONLY=true
echo  Uso: AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat [/FORCE]
echo  /FORCE = limpa cache Desktop + recria venv se necessario
echo ================================================================
echo ROOT=%ROOT%
echo.

if not exist "%ROOT%\engine\server.py" (
  echo [ERRO CRITICO] engine\server.py ausente. Extraia o ZIP completo para C:\aura
  pause
  exit /b 1
)
if not exist "%ROOT%\bridge\server.py" (
  echo [ERRO CRITICO] bridge\server.py ausente.
  pause
  exit /b 1
)

echo [1/12] Liberar portas AURA (8080/8765/8766/8099/8777/8778)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach($p in 8080,8765,8766,8099,8777,8778,8790){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | ForEach-Object { if($_.OwningProcess -gt 4){ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue } } }" >> "%MASTERLOG%" 2>&1
timeout /t 2 /nobreak >nul

echo [2/12] Cache Desktop / WebView2...
if defined FORCE (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -Recurse -Force \"$env:LOCALAPPDATA\AURA_QUANT_X\" -EA SilentlyContinue; Write-Host '  cache limpo'"
) else (
  echo       skip cache (use /FORCE para limpar %%LOCALAPPDATA%%\AURA_QUANT_X)
)

echo [3/12] Detectando Python 3.10/3.11...
set "HOST_PY="
where py >nul 2>&1 && ( py -3.11 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.11" )
if not defined HOST_PY where py >nul 2>&1 && ( py -3.10 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.10" )
if not defined HOST_PY where python >nul 2>&1 && set "HOST_PY=python"
if not defined HOST_PY (
  echo [ERRO] Python 3.10 ou 3.11 nao encontrado no PATH
  pause
  exit /b 2
)
%HOST_PY% -c "import sys; v=sys.version_info; raise SystemExit(0 if v[:2] in ((3,10),(3,11)) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Precisa Python 3.10 ou 3.11. Nao use 3.12+. Detectado:
  %HOST_PY% -c "import sys; print(sys.version)"
  pause
  exit /b 2
)

set "VENV_DIR=%ROOT%\engine\venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "NEED_VENV=1"
if not defined FORCE if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import pydantic,fastapi,uvicorn,httpx,requests,psutil" >nul 2>&1
  if "!ERRORLEVEL!"=="0" (
    set "NEED_VENV="
    echo [4/12] venv existente OK — preservada
  )
)
if defined NEED_VENV (
  echo [4/12] Criando/recriando venv...
  if exist "%VENV_DIR%" if defined FORCE rmdir /s /q "%VENV_DIR%" 2>nul
  if not exist "%VENV_PY%" %HOST_PY% -m venv "%VENV_DIR%"
  if not exist "%VENV_PY%" (
    echo [ERRO] Falha ao criar venv
    pause
    exit /b 3
  )
  echo [5/12] Instalando dependencias criticas...
  "%VENV_PY%" -m pip install --upgrade pip setuptools wheel >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt" >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\engine\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\engine\requirements.txt" >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\bridge\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\bridge\requirements.txt" >> "%MASTERLOG%" 2>&1
  "%VENV_PY%" -m pip install "requests>=2.32,<3" "pydantic>=2.8,<3" "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "python-multipart>=0.0.9" "httpx>=0.27" psutil structlog prometheus-client python-dotenv pyyaml aiofiles websockets >> "%MASTERLOG%" 2>&1
) else (
  echo [5/12] skip pip
)
"%VENV_PY%" -c "import pydantic,fastapi,uvicorn,httpx,requests,psutil; print('CRITICAL_OK')"
if not "!ERRORLEVEL!"=="0" (
  echo [ERRO] Imports criticos falharam. Rode de novo com /FORCE
  pause
  exit /b 4
)

echo [6/12] Ambiente paper-only...
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_PAPER_TRADE=1"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "AURA_PAPER_ONLY=1"
set "GLM_ADVISORY_ONLY=true"
set "AURA_GLM_ENABLED=0"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge;%ROOT%\hermes_v10"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"

echo [7/12] Bridge :8080...
start "AURA-Bridge" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_PAPER_TRADE=1&& set AURA_EXECUTION_ALLOWED=0&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u bridge\server.py --host 127.0.0.1 --port 8080 >> "%LOGDIR%\bridge.log" 2>&1"

echo [8/12] Engine :8765...
start "AURA-Engine" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_PAPER_TRADE=1&& set AURA_EXECUTION_ALLOWED=0&& set AURA_UNLOCK_LIVE=0&& set GLM_ADVISORY_ONLY=true&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u engine\server.py --host 127.0.0.1 --port 8765 >> "%LOGDIR%\engine.log" 2>&1"

echo [9/12] Voice :8099...
if exist "%ROOT%\bridge\jarvis_voice_server.py" (
  start "AURA-Voice" /MIN cmd /c "cd /d %ROOT% && set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%LOGDIR%\voice.log" 2>&1"
) else (
  echo       Voice script nao encontrado — skip
)

echo [10/12] Hermes V10 :8777...
set "HERMES_ENTRY="
if exist "%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py" set "HERMES_ENTRY=%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py"
if not defined HERMES_ENTRY if exist "%ROOT%\scripts\hermes_v10_chat_api.py" set "HERMES_ENTRY=%ROOT%\scripts\hermes_v10_chat_api.py"
if not defined HERMES_ENTRY if exist "%ROOT%\hermes_v10\AURA_RUN_HERMES.py" set "HERMES_ENTRY=%ROOT%\hermes_v10\AURA_RUN_HERMES.py"

if defined HERMES_ENTRY (
  start "AURA-Hermes-Chat" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "%VENV_PY%" -u "%HERMES_ENTRY%" >> "%LOGDIR%\hermes_v10.log" 2>&1"
  echo       Hermes iniciado. Log: logs_supervisor\hermes_v10.log
) else (
  echo       [AVISO] hermes entry nao encontrado
)

echo [11/12] Matriz HTTP :8766...
start "AURA-Matriz-8766" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u scripts\aura_serve_matriz.py >> "%LOGDIR%\matriz8766.log" 2>&1"

echo [12/12] Aguardando health (ate ~60s)...
set "B=OFF"
set "E=OFF"
set "M=OFF"
set "H=OFF"
set "V=OFF"

for /L %%i in (1,1,20) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8080/health' -UseBasicParsing -TimeoutSec 2|Out-Null; 'B_OK'}catch{'B_OFF'}" > "%TEMP%\ah_b.txt" 2>nul
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 2|Out-Null; 'E_OK'}catch{'E_OFF'}" > "%TEMP%\ah_e.txt" 2>nul
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8766/health' -UseBasicParsing -TimeoutSec 2|Out-Null; 'M_OK'}catch{'M_OFF'}" > "%TEMP%\ah_m.txt" 2>nul
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8777/chat' -UseBasicParsing -TimeoutSec 2|Out-Null; 'H_OK'}catch{'H_OFF'}" > "%TEMP%\ah_h.txt" 2>nul
  powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8099/api/voice/health' -UseBasicParsing -TimeoutSec 2|Out-Null; 'V_OK'}catch{'V_OFF'}" > "%TEMP%\ah_v.txt" 2>nul
  findstr /C:"B_OK" "%TEMP%\ah_b.txt" >nul && set "B=OK"
  findstr /C:"E_OK" "%TEMP%\ah_e.txt" >nul && set "E=OK"
  findstr /C:"M_OK" "%TEMP%\ah_m.txt" >nul && set "M=OK"
  findstr /C:"H_OK" "%TEMP%\ah_h.txt" >nul && set "H=OK"
  findstr /C:"V_OK" "%TEMP%\ah_v.txt" >nul && set "V=OK"
  if "!B!"=="OK" if "!E!"=="OK" if "!H!"=="OK" (
    echo       Health core OK na tentativa %%i
    goto :AFTER_WAIT
  )
  timeout /t 3 /nobreak >nul
)
:AFTER_WAIT

if /I not "!H!"=="OK" (
  echo [RETRY] Hermes OFF — segundo arranque...
  powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }" >nul 2>&1
  timeout /t 1 /nobreak >nul
  if defined HERMES_ENTRY (
    start "AURA-Hermes-Chat" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "%VENV_PY%" -u "%HERMES_ENTRY%" >> "%LOGDIR%\hermes_v10.log" 2>&1"
    timeout /t 6 /nobreak >nul
    powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8777/chat' -UseBasicParsing -TimeoutSec 3|Out-Null; exit 0}catch{exit 1}"
    if not errorlevel 1 set "H=OK"
  )
)

REM final refresh
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8080/health' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" & if not errorlevel 1 set "B=OK"
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8765/api/health' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" & if not errorlevel 1 set "E=OK"
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8766/health' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" & if not errorlevel 1 set "M=OK"
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8777/chat' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" & if not errorlevel 1 set "H=OK"
powershell -NoProfile -Command "try{Invoke-WebRequest 'http://127.0.0.1:8099/api/voice/health' -UseBasicParsing -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}" & if not errorlevel 1 set "V=OK"

echo.
echo ================================================================
echo  RESUMO FINAL
echo ================================================================
echo  Bridge  :8080   = !B!
echo  Engine  :8765   = !E!
echo  Matriz  :8766   = !M!
echo  Hermes  :8777   = !H!
echo  Voice   :8099   = !V!
echo  paper_trade=true / execution_allowed=false
echo ================================================================
echo  Matriz  http://127.0.0.1:8766/index.html
echo  Hermes  http://127.0.0.1:8777/chat
echo  Logs    %LOGDIR%
echo ================================================================

if /I not "!H!"=="OK" (
  echo [AVISO] Hermes OFF. Rode: AURA_HERMES_V10_ULTRA.bat
  echo         Log: type %LOGDIR%\hermes_v10.log
)

if exist "%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe" (
  start "" "%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe"
) else (
  start "" "http://127.0.0.1:8766/index.html"
)

echo.
echo [AURA] Pressiona uma tecla para sair.
pause
endlocal
