@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title AURA INSTALAR TUDO V37.3.25
color 0A

set "FORCE="
if /I "%~1"=="/FORCE" set "FORCE=1"

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=C:\aura"

echo ================================================================
echo  AURA QUANT-X 12.7.62 V37.3.25 — INSTALAR TUDO
echo  paper_trade=true   execution_allowed=false
echo  Sequencia: LIMPEZA ^> INSTALACAO ^> CHECK ^> SERVICOS ^> CHECK
echo             ^> HERMES CHAT ^> DESKTOP ^> CHECK
echo ================================================================
echo SRC =%SRC%
echo DEST=%DEST%
if defined FORCE echo MODO=/FORCE (recria venv)
echo.

if not exist "%SRC%\engine\server.py" (
  echo [ERRO] engine\server.py nao esta junto deste BAT.
  echo Extraia o ZIP completo e rode INSTALAR_TUDO.bat de dentro da pasta extraida.
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)
if not exist "%SRC%\bridge\server.py" (
  echo [ERRO] bridge\server.py ausente no pacote extraido.
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)

echo [0] Preparar C:\aura ...
if not exist "%DEST%" mkdir "%DEST%"
if /I not "%SRC%"=="%DEST%" (
  echo       Copiando pacote para C:\aura ^(preserva engine\venv^)
  robocopy "%SRC%" "%DEST%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /XD engine\venv venv node_modules .git __pycache__ logs_supervisor /XF *.pyc >nul
  set "RC=!ERRORLEVEL!"
  if !RC! GEQ 8 (
    echo [ERRO] robocopy falhou com codigo !RC!
    echo.
    echo [AURA] Erro acima. Janela mantida.
    pause
    exit /b 1
  )
) else (
  echo       Ja esta em C:\aura — sem copia
)
cd /d "%DEST%"
set "ROOT=%DEST%"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
set "LOG=%ROOT%\logs_supervisor\INSTALAR_TUDO.log"
echo ==== %DATE% %TIME% INSTALAR_TUDO ROOT=%ROOT% FORCE=%FORCE% ====>> "%LOG%"

if not exist "%ROOT%\engine\server.py" (
  echo [ERRO] Copia incompleta: falta %ROOT%\engine\server.py
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)
if not exist "%ROOT%\desktop\ui\matriz_v22\index.html" (
  echo [AVISO] desktop\ui\matriz_v22\index.html ausente — Matriz pode falhar
)

echo.
echo ========== 1 LIMPEZA COMPLETA ==========
if exist "%ROOT%\LIMPEZA_COMPLETA.bat" (
  call "%ROOT%\LIMPEZA_COMPLETA.bat"
) else if exist "%ROOT%\scripts\AURA_SAFE_FREE_PORTS.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\AURA_SAFE_FREE_PORTS.ps1"
)
timeout /t 2 /nobreak >nul
echo.

echo ========== 2 INSTALACAO ==========
set "HOST_PY="
py -3.11 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.11"
if not defined HOST_PY py -3.10 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.10"
if not defined HOST_PY (
  python -c "import sys; raise SystemExit(0 if sys.version_info.major==3 and 10<=sys.version_info.minor<=12 else 1)" >nul 2>&1 && set "HOST_PY=python"
)
if not defined HOST_PY (
  echo [ERRO] Python 3.10/3.11 nao encontrado no PATH.
  echo Instale Python 3.11 x64 e marque "Add python.exe to PATH".
  echo Log: %LOG%
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 2
)
echo       Python host: %HOST_PY%

set "VENV_DIR=%ROOT%\engine\venv"
set "VPY=%VENV_DIR%\Scripts\python.exe"
set "NEED_VENV=1"
if not defined FORCE if exist "%VPY%" (
  "%VPY%" -c "import fastapi,uvicorn,pydantic,requests,httpx,psutil" >nul 2>&1
  if "!ERRORLEVEL!"=="0" (
    set "NEED_VENV="
    echo       venv existente OK — preservada
  ) else (
    echo       venv existente com imports em falta — vai reparar pip
  )
)

if defined FORCE if exist "%VENV_DIR%" (
  echo       /FORCE : a apagar venv antiga
  rmdir /s /q "%VENV_DIR%" 2>nul
)

if not exist "%VPY%" (
  echo       a criar venv ...
  %HOST_PY% -m venv "%VENV_DIR%" >> "%LOG%" 2>&1
)
if not exist "%VPY%" (
  echo [ERRO] Falha ao criar engine\venv
  echo Veja %LOG%
  exit /b 3
)

echo       pip + dependencias criticas ...
"%VPY%" -m pip install --disable-pip-version-check --upgrade pip wheel setuptools >> "%LOG%" 2>&1
if exist "%ROOT%\requirements.txt" "%VPY%" -m pip install --disable-pip-version-check -r "%ROOT%\requirements.txt" >> "%LOG%" 2>&1
if exist "%ROOT%\engine\requirements.txt" "%VPY%" -m pip install --disable-pip-version-check -r "%ROOT%\engine\requirements.txt" >> "%LOG%" 2>&1
if exist "%ROOT%\bridge\requirements.txt" "%VPY%" -m pip install --disable-pip-version-check -r "%ROOT%\bridge\requirements.txt" >> "%LOG%" 2>&1
"%VPY%" -m pip install --disable-pip-version-check "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "pydantic>=2.8,<3" "requests>=2.32,<3" "httpx>=0.27" "python-multipart>=0.0.9" psutil pyyaml websockets >> "%LOG%" 2>&1
"%VPY%" -c "import fastapi,uvicorn,pydantic,requests,httpx,psutil; print('CRITICAL_OK')" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Imports criticos falharam. Rode INSTALAR_TUDO.bat /FORCE
  echo Log: %LOG%
  exit /b 4
)
echo       pip OK

if not exist "%ROOT%\engine\data" mkdir "%ROOT%\engine\data"
if not exist "%ROOT%\engine\prompts" mkdir "%ROOT%\engine\prompts"
if not exist "%ROOT%\bridge" mkdir "%ROOT%\bridge"

set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "AURA_PAPER_ONLY=1"
set "GLM_ADVISORY_ONLY=true"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
echo       flags paper-only aplicadas
echo.

echo ========== 3 CHECK ==========
call "%ROOT%\CHECK.bat" files
echo.

echo ========== 4 SERVICOS ==========
echo       Bridge :8080
start "AURA-Bridge-8080" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PYTHONUNBUFFERED=1&& set PYTHONUTF8=1&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& "%VPY%" -u bridge\server.py --host 127.0.0.1 --port 8080 >> "%ROOT%\logs_supervisor\bridge.log" 2>&1"

echo       Engine :8765
start "AURA-Engine-8765" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PYTHONUNBUFFERED=1&& set PYTHONUTF8=1&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_EXECUTION_ALLOWED=0&& set AURA_UNLOCK_LIVE=0&& set AURA_PAPER_ONLY=1&& set GLM_ADVISORY_ONLY=true&& "%VPY%" -u engine\server.py --host 127.0.0.1 --port 8765 >> "%ROOT%\logs_supervisor\engine.log" 2>&1"

if exist "%ROOT%\bridge\jarvis_voice_server.py" (
  echo       Voice :8099
  start "AURA-Voice-8099" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PYTHONUTF8=1&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& "%VPY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%ROOT%\logs_supervisor\voice.log" 2>&1"
) else (
  echo       Voice ausente — skip
)

echo       Matriz :8766
start "AURA-Matriz-8766" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& "%VPY%" -u scripts\aura_serve_matriz.py >> "%ROOT%\logs_supervisor\matriz8766.log" 2>&1"

echo       a aguardar health Bridge+Engine+Matriz ...
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){ $b=$false;$e=$false;$m=$false; try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null;$b=$true}catch{}; try{Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null;$e=$true}catch{}; try{Invoke-WebRequest 'http://127.0.0.1:8766/health' -UseBasicParsing -TimeoutSec 2|Out-Null;$m=$true}catch{}; if($b -and $e){ Write-Host ('      health b={0} e={1} m={2}' -f $b,$e,$m); exit 0 }; Start-Sleep 2 }; Write-Host '      [AVISO] health incompleto apos 80s — veja logs_supervisor'; exit 0"
echo.

echo ========== 5 CHECK ==========
call "%ROOT%\CHECK.bat" services
echo.

echo ========== 6 HERMES CHAT ==========
if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" (
  call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
) else if exist "%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py" (
  echo       fallback direto hermes_v10_chat_api.py
  start "AURA-Hermes-Chat" /MIN cmd /c "cd /d %ROOT%\hermes_v10 && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%\hermes_v10;%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "%VPY%" -u scripts\hermes_v10_chat_api.py >> "%ROOT%\logs_supervisor\hermes_v10.log" 2>&1"
  timeout /t 3 /nobreak >nul
  start "" http://127.0.0.1:8777/chat
) else (
  echo [AVISO] Hermes V10 ausente neste pacote
)
echo.

echo ========== 7 DESKTOP ==========
set "EXE=%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe"
if not exist "%EXE%" (
  where dotnet >nul 2>&1
  if not errorlevel 1 if exist "%ROOT%\desktop\packaging\PUBLISH_WINDOWS.ps1" (
    echo       EXE ausente — a tentar publish .NET ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\desktop\packaging\PUBLISH_WINDOWS.ps1" >> "%LOG%" 2>&1
  )
)
if exist "%EXE%" (
  echo       Abrindo %EXE%
  start "AURA Operator OS" "%EXE%"
) else (
  echo [AVISO] Desktop EXE nao existe neste ZIP.
  echo       Fallback: Matriz no browser
  start "" http://127.0.0.1:8766/index.html
  echo       Para gerar o EXE depois: COMPILAR_E_ABRIR_DESKTOP.bat
)
echo.

echo ========== 8 CHECK ==========
timeout /t 4 /nobreak >nul
call "%ROOT%\CHECK.bat" final

echo.
echo ================================================================
echo  INSTALACAO CONCLUIDA
echo ================================================================
echo  Matriz  http://127.0.0.1:8766/index.html
echo  Engine  http://127.0.0.1:8765/api/health
echo  Bridge  http://127.0.0.1:8080/health
echo  Hermes  http://127.0.0.1:8777/chat
echo  Log     %LOG%
echo  paper_trade=true  execution_allowed=false
echo  Dia a dia: AURA_START_ALL.bat
echo ================================================================
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
