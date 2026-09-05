@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA FIX PAINEL AGORA
color 0A
set "ROOT=%CD%"

echo ================================================================
echo  FIX PAINEL — Control:8790 + Bridge:8080
echo  ROOT=%ROOT%
echo ================================================================

REM ---- Python: venv preferido, senao py -3.11 / python ----
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
if not defined VPY where python >nul 2>&1 && set "VPY=python"

if not defined VPY (
  echo [ERRO] Nenhum Python 3.10/3.11 encontrado.
  echo Instale Python 3.11 e rode: AURA_REBUILD_HERMES.bat
  pause
  exit /b 1
)

echo [PY] %VPY%
%VPY% -c "import sys; print(sys.version)"

REM Recriar venv se ausente
if not exist "%ROOT%\engine\venv\Scripts\python.exe" (
  echo [VENV] Criando engine\venv ...
  if not exist "%ROOT%\engine" mkdir "%ROOT%\engine"
  %VPY% -m venv "%ROOT%\engine\venv"
  if not exist "%ROOT%\engine\venv\Scripts\python.exe" (
    echo [ERRO] Falha a criar venv
    pause
    exit /b 2
  )
  set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
  echo [PIP] deps minimas...
  "%VPY%" -m pip install --upgrade pip
  if exist "%ROOT%\hermes_v10\requirements-minimal.txt" (
    "%VPY%" -m pip install -r "%ROOT%\hermes_v10\requirements-minimal.txt"
  ) else (
    "%VPY%" -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8" "httpx>=0.27" "psutil>=5.9"
  )
)

set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [ERRO] venv ainda ausente apos create
  pause
  exit /b 3
)

set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"

echo.
echo [CHECK] ficheiros
if exist "%ROOT%\scripts\aura_tools_control_api.py" (echo   OK scripts\aura_tools_control_api.py) else (echo   FALTA scripts\aura_tools_control_api.py)
if exist "%ROOT%\bridge\server.py" (echo   OK bridge\server.py) else (echo   FALTA bridge\server.py)

REM --- Control API 8790 ---
echo.
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8790 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if errorlevel 1 (
  if not exist "%ROOT%\scripts\aura_tools_control_api.py" (
    echo [ERRO] Nao posso subir Control API — script em falta. Extraia o ZIP COMPLETO.
  ) else (
    echo [START] Control API :8790  (janela fica aberta)
    start "AURA-Control-API" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u scripts\aura_tools_control_api.py"
  )
) else (
  echo [SKIP] Control API ja LISTEN :8790
)

REM --- Bridge 8080 ---
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8080 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if errorlevel 1 (
  if not exist "%ROOT%\bridge\server.py" (
    echo [ERRO] Nao posso subir Bridge — bridge\server.py em falta. Extraia o ZIP COMPLETO.
  ) else (
    echo [START] Bridge :8080  (janela fica aberta)
    start "AURA-Bridge" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u bridge\server.py --host 127.0.0.1 --port 8080"
  )
) else (
  echo [SKIP] Bridge ja LISTEN :8080
)

echo.
echo Aguardando 8s...
timeout /t 8 /nobreak >nul

echo.
echo ===== PORTAS =====
powershell -NoProfile -Command "8080,8765,8790,8099,8777|ForEach-Object{$c=Get-NetTCPConnection -LocalPort $_ -State Listen -EA SilentlyContinue; if($c){'  LISTEN '+$_}else{'  OFF    '+$_}}"

echo.
echo ===== HEALTH =====
echo Control:
curl -s -m 3 http://127.0.0.1:8790/health 2>nul || echo FALHA
echo.
echo Bridge:
curl -s -m 3 http://127.0.0.1:8080/health 2>nul || echo FALHA
echo.
echo Engine:
curl -s -m 3 http://127.0.0.1:8765/api/health 2>nul || echo FALHA
echo.

echo Hub: http://127.0.0.1:8766/tools-hub.html  — clique Atualizar tudo
start "" "http://127.0.0.1:8766/tools-hub.html"
echo.
echo Se Control/Bridge OFF: leia a janela cmd aberta (traceback em vermelho).
pause
endlocal
