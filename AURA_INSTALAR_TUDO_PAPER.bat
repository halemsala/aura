@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA INSTALAR TUDO PAPER
color 0B

set "ROOT=%CD%"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "GLM_ADVISORY_ONLY=1"
set "HERMES_REQUIRE_AUTH=0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"

if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
set "LOG=%ROOT%\logs_supervisor\install_tudo_paper.log"
echo ==== %DATE% %TIME% INSTALAR TUDO PAPER ROOT=%ROOT% ====>> "%LOG%"

echo ================================================================
echo  AURA INSTALAR TUDO — PAPER ONLY
echo  1) Python 3.11 + recria engine\venv
echo  2) pip deps (Hermes minimal + engine se existir)
echo  3) Matriz UI (extrai do ZIP se faltar)
echo  4) Sobe Bridge Engine Matriz Hermes Control Voice
echo  5) Health + relatorio
echo  paper_trade=true  execution_allowed=false
echo ================================================================
echo.

REM ---------- 0) precheck ficheiros criticos ----------
echo [0/6] Precheck...
set "MISS=0"
if not exist "%ROOT%\bridge\server.py" (echo   FALTA bridge\server.py & set "MISS=1")
if not exist "%ROOT%\scripts\aura_tools_control_api.py" (echo   FALTA scripts\aura_tools_control_api.py & set "MISS=1")
if not exist "%ROOT%\scripts\aura_serve_matriz.py" (echo   FALTA scripts\aura_serve_matriz.py & set "MISS=1")
if not exist "%ROOT%\hermes_v10\AURA_RUN_HERMES.py" (echo   FALTA hermes_v10\AURA_RUN_HERMES.py & set "MISS=1")
if "!MISS!"=="1" (
  echo.
  echo [ERRO] Pacote incompleto em %ROOT%
  echo Extraia AURA_QUANT_X_V37.3.54_COMPLETO_FIXED.zip por cima de C:\aura
  pause
  exit /b 1
)
echo   OK ficheiros base

REM ---------- 1) Python 3.11 ----------
echo [1/6] Python 3.11...
set "PYLA=py -3.11"
%PYLA% -c "import sys; assert sys.version_info[:2]==(3,11); print(sys.version)" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] py -3.11 nao disponivel. Instale Python 3.11 e marque "py launcher".
  py -0p 2>nul
  pause
  exit /b 2
)
%PYLA% -c "import sys; print(sys.version)"

REM ---------- 2) SEMPRE recria venv ----------
echo [2/6] Recriar engine\venv (sempre)...
if exist "%ROOT%\engine\venv" (
  echo   Removendo venv antigo...
  rmdir /s /q "%ROOT%\engine\venv" 2>nul
)
if not exist "%ROOT%\engine" mkdir "%ROOT%\engine"
%PYLA% -m venv "%ROOT%\engine\venv" >> "%LOG%" 2>&1
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [ERRO] venv nao criado
  type "%LOG%" | more
  pause
  exit /b 3
)
echo   VPY=%VPY%
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1

echo [3/6] pip deps...
if exist "%ROOT%\hermes_v10\requirements-minimal.txt" (
  "%VPY%" -m pip install -r "%ROOT%\hermes_v10\requirements-minimal.txt" >> "%LOG%" 2>&1
) else (
  "%VPY%" -m pip install "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "pydantic>=2.8,<3" "httpx>=0.27,<1" "python-multipart" "python-dotenv" "pyyaml" "psutil>=5.9,<7" >> "%LOG%" 2>&1
)
if exist "%ROOT%\engine\requirements.txt" (
  echo   + engine\requirements.txt (pode demorar)
  "%VPY%" -m pip install -r "%ROOT%\engine\requirements.txt" >> "%LOG%" 2>&1
)
"%VPY%" -c "import fastapi,uvicorn,pydantic,httpx; print('deps OK', fastapi.__version__)"
if errorlevel 1 (
  echo [ERRO] deps
  pause
  exit /b 4
)

REM ---------- 4) Matriz UI ----------
echo [4/6] Matriz UI...
if not exist "%ROOT%\desktop\ui\matriz_v22\index.html" (
  echo   index.html ausente — a extrair do ZIP FIXED se existir...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$z=Get-ChildItem -Path $env:USERPROFILE\Downloads,$env:USERPROFILE\Desktop,'%ROOT%' -Filter '*V37.3.54*.zip' -File -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; ^
     if(-not $z){Write-Host 'ZIP nao encontrado'; exit 1}; ^
     Write-Host ('ZIP '+$z.FullName); ^
     Add-Type -AssemblyName System.IO.Compression.FileSystem; ^
     $zip=[System.IO.Compression.ZipFile]::OpenRead($z.FullName); ^
     foreach($e in $zip.Entries){ if($e.FullName -like 'desktop/ui/matriz_v22/*' -and $e.FullName -notlike '*/'){ ^
       $dest=Join-Path '%ROOT%' ($e.FullName -replace '/','\'); ^
       $dir=Split-Path $dest; if(-not (Test-Path $dir)){New-Item -ItemType Directory -Force -Path $dir|Out-Null}; ^
       [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e,$dest,$true) } }; ^
     $zip.Dispose(); ^
     if(Test-Path '%ROOT%\desktop\ui\matriz_v22\index.html'){Write-Host 'OK index.html'}else{Write-Host 'FALHA index'; exit 2}"
  if errorlevel 1 (
    echo   [AVISO] Nao extraiu matriz — coloque o ZIP FIXED em Downloads ou C:\aura e rode de novo
  )
) else (
  echo   OK index.html
)

REM ---------- 5) Libera portas e sobe servicos ----------
echo [5/6] Subir servicos...
for %%P in (8080 8765 8766 8777 8790 8099) do (
  powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %%P -State Listen -EA SilentlyContinue | ForEach-Object { if($_.OwningProcess -gt 4){ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue } }" >> "%LOG%" 2>&1
)
timeout /t 2 /nobreak >nul

set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge;%ROOT%\hermes_v10"

start "AURA-Bridge" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PYTHONPATH=%PYTHONPATH% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u bridge\server.py --host 127.0.0.1 --port 8080"
timeout /t 2 /nobreak >nul

if exist "%ROOT%\engine\server.py" (
  start "AURA-Engine" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PYTHONPATH=%PYTHONPATH% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set AURA_EXECUTION_ALLOWED=0 & set PYTHONUTF8=1 & "%VPY%" -u engine\server.py --host 127.0.0.1 --port 8765"
  timeout /t 2 /nobreak >nul
)

start "AURA-Matriz" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PYTHONUTF8=1 & "%VPY%" -u scripts\aura_serve_matriz.py"
timeout /t 2 /nobreak >nul

start "AURA-Control" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u scripts\aura_tools_control_api.py"
timeout /t 2 /nobreak >nul

if exist "%ROOT%\hermes_v10\AURA_RUN_HERMES.py" (
  start "AURA-Hermes" cmd /k "cd /d %ROOT%\hermes_v10 & set AURA_ROOT=%ROOT% & set PYTHONPATH=%ROOT%\hermes_v10;%ROOT% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set HERMES_API_PORT=8777 & set HERMES_REQUIRE_AUTH=0 & set PYTHONUTF8=1 & "%VPY%" -u AURA_RUN_HERMES.py"
  timeout /t 2 /nobreak >nul
)

if exist "%ROOT%\bridge\jarvis_voice_server.py" (
  start "AURA-Voice" cmd /k "cd /d %ROOT% & set AURA_ROOT=%ROOT% & set PYTHONPATH=%PYTHONPATH% & set PAPER_TRADE=true & set EXECUTION_ALLOWED=false & set PYTHONUTF8=1 & "%VPY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy"
)

REM ---------- 6) Health ----------
echo [6/6] Health (20s)...
timeout /t 20 /nobreak >nul

set "REP=%ROOT%\logs_supervisor\RELATORIO_INSTALAR_TUDO_LATEST.txt"
echo RELATORIO INSTALAR TUDO %DATE% %TIME% > "%REP%"
echo ROOT=%ROOT%>> "%REP%"
echo paper_trade=true execution_allowed=false>> "%REP%"
echo.>> "%REP%"

echo.
echo ===== PORTAS / HEALTH =====
for %%U in (
  "8080|/health|Bridge"
  "8765|/api/health|Engine"
  "8766|/health|Matriz"
  "8777|/health|Hermes"
  "8790|/health|Control"
  "8099|/api/voice/health|Voice"
) do (
  for /f "tokens=1,2,3 delims=|" %%a in (%%U) do (
    powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:%%a%%b' -UseBasicParsing -TimeoutSec 3; 'OK   %%c :%%a'}catch{'OFF  %%c :%%a'}" 
    powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:%%a%%b' -UseBasicParsing -TimeoutSec 3; 'OK   %%c :%%a'}catch{'OFF  %%c :%%a'}" >> "%REP%"
  )
)

echo.
echo Relatorio: %REP%
echo Log pip:   %LOG%
echo.
echo Hub:  http://127.0.0.1:8766/tools-hub.html
echo Chat: http://127.0.0.1:8777/chat
start "" "http://127.0.0.1:8766/tools-hub.html"

echo.
echo Janelas abertas = processos. Se algum OFF, leia a janela desse servico.
pause
endlocal
