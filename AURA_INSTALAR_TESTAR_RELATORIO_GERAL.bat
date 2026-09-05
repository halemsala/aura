@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Operator OS V37.3.1 - Installer corrigido
color 0A

set "ROOT=%CD%"
if not exist "%ROOT%\engine\server.py" if exist "%ROOT%\AURA_QUANT_X_12.7.62_HERMES_FIXED\engine\server.py" set "ROOT=%ROOT%\AURA_QUANT_X_12.7.62_HERMES_FIXED"
cd /d "%ROOT%"

set "FORCE="
if /I "%~1"=="/FORCE" set "FORCE=1"

set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "MASTERLOG=%LOGDIR%\AURA_OPERATOR_OS_LAUNCHER.log"
echo ==== %DATE% %TIME% INSTALL V37.3.1 ROOT=%ROOT% FORCE=%FORCE% ====>> "%MASTERLOG%"

echo ================================================================
echo  AURA 12.7.62 V37.3.1 — instalador corrigido
echo  paper_trade=true  execution_allowed=false  GLM_ADVISORY_ONLY=true
echo  /FORCE recria venv. Sem flag, preserva venv se imports OK.
echo ================================================================
echo ROOT=%ROOT%
echo.

if not exist "%ROOT%\engine\server.py" (
  echo [ERRO CRITICO] engine\server.py ausente. Extraia o ZIP completo.
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)
if not exist "%ROOT%\bridge\server.py" (
  echo [ERRO CRITICO] bridge\server.py ausente.
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)
if not exist "%ROOT%\desktop\ui\matriz_v22\index.html" (
  echo [ERRO CRITICO] Interface V25Q nao encontrada: desktop\ui\matriz_v22\index.html
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)

echo [1/14] Liberar portas AURA (NÃO mata Ollama :11434)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\AURA_SAFE_FREE_PORTS.ps1" >> "%MASTERLOG%" 2>&1
timeout /t 2 /nobreak >nul

echo [2/14] Cache WebView2 so se /FORCE...
if defined FORCE (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\AURA_SAFE_FREE_PORTS.ps1" -IncludeWebViewCache >> "%MASTERLOG%" 2>&1
) else (
  echo       skip cache (use /FORCE para limpar desktop_data)
)

echo [3/14] Detectando Python 3.10/3.11...
set "HOST_PY="
where py >nul 2>&1 && ( py -3.11 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.11" )
if not defined HOST_PY where py >nul 2>&1 && ( py -3.10 -c "import sys" >nul 2>&1 && set "HOST_PY=py -3.10" )
if not defined HOST_PY where python >nul 2>&1 && set "HOST_PY=python"
if not defined HOST_PY (
  echo [ERRO] Python 3.10 ou 3.11 nao encontrado no PATH
  echo.
  echo [AURA] Erro acima. Janela mantida.
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
    echo [4/14] venv existente OK — preservada
  )
)
if defined NEED_VENV (
  echo [4/14] Criando/recriando venv...
  if exist "%VENV_DIR%" if defined FORCE rmdir /s /q "%VENV_DIR%" 2>nul
  %HOST_PY% -c "import sys; v=sys.version_info; raise SystemExit(0 if v.major==3 and 10<=v.minor<=11 else 1)"
  if not "!ERRORLEVEL!"=="0" (
    echo [ERRO] Use apenas Python 3.10.x ou 3.11.x
    echo.
    echo [AURA] Erro acima. Janela mantida.
    pause
    exit /b 2
  )
  if not exist "%VENV_PY%" %HOST_PY% -m venv "%VENV_DIR%"
  if not exist "%VENV_PY%" (
    echo [ERRO] Falha ao criar venv
    exit /b 3
  )
  echo [5/14] Instalando dependencias...
  "%VENV_PY%" -m pip install --upgrade pip setuptools wheel >> "%MASTERLOG%" 2>&1
  "%VENV_PY%" -m pip uninstall -y nome cleo clikit crashtest pastel pylev >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt" >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\engine\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\engine\requirements.txt" >> "%MASTERLOG%" 2>&1
  if exist "%ROOT%\bridge\requirements.txt" "%VENV_PY%" -m pip install -r "%ROOT%\bridge\requirements.txt" >> "%MASTERLOG%" 2>&1
  "%VENV_PY%" -m pip install "requests>=2.32,<3" "pydantic>=2.8,<3" "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "python-multipart>=0.0.9" "httpx>=0.27" psutil >> "%MASTERLOG%" 2>&1
) else (
  echo [5/14] skip pip
)
"%VENV_PY%" -c "import pydantic,fastapi,uvicorn,httpx,requests,psutil; print('CRITICAL_OK')"
if not "!ERRORLEVEL!"=="0" (
  echo [ERRO] Imports criticos falharam. Veja: %MASTERLOG%
  echo Dica: rode de novo com /FORCE
  exit /b 4
)

echo [6/14] Ambiente paper-only...
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "AURA_PAPER_ONLY=1"
set "GLM_ADVISORY_ONLY=true"
set "AURA_GLM_ENABLED=0"
set "AURA_LLM_BACKEND=hermes"
set "CORNERAI_CHAT_MODEL=llama3.2:3b"
set "CORNERAI_ADMIN_MODEL=llama3.2:3b"
set "AURA_HERMES_MODEL=llama3.2:3b"
set "AURA_OLLAMA_MODEL=llama3.2:3b"
set "AURA_OLLAMA_FALLBACK=llama3.2:1b"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
set "AURA_HERMES_GPU=0"
set "OLLAMA_NUM_GPU=0"

echo [GPU] NVIDIA/CUDA...
nvidia-smi -L >nul 2>&1
if errorlevel 1 (
  echo       NVIDIA nao detectada: CPU seguro.
  echo [GPU FALLBACK] CPU>> "%MASTERLOG%"
) else (
  echo       NVIDIA detectada.
  set "AURA_HERMES_GPU=1"
  set "OLLAMA_NUM_GPU=99"
  set "CUDA_VISIBLE_DEVICES=0"
  set "AURA_CUDA_DEVICE=0"
  set "AURA_OLLAMA_KEEP_ALIVE=30m"
  nvidia-smi -L >> "%MASTERLOG%" 2>&1
)

echo [7/14] Diagnostico GPU (se existir)...
if exist "%ROOT%\scripts\aura_gpu_diagnostic.py" "%VENV_PY%" "%ROOT%\scripts\aura_gpu_diagnostic.py" >> "%LOGDIR%\gpu_diagnostic.log" 2>&1

echo [8/14] Bridge :8080...
start "AURA-Bridge-8080" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PYTHONUNBUFFERED=1&& set PYTHONUTF8=1&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& "%VENV_PY%" -u bridge\server.py --host 127.0.0.1 --port 8080 >> "%LOGDIR%\bridge.log" 2>&1"

echo [9/14] Engine :8765...
start "AURA-Engine-8765" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PYTHONUNBUFFERED=1&& set PYTHONUTF8=1&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_EXECUTION_ALLOWED=0&& set AURA_UNLOCK_LIVE=0&& set AURA_PAPER_ONLY=1&& set GLM_ADVISORY_ONLY=true&& set AURA_PRIORITY=MATRIZ&& "%VENV_PY%" -u engine\server.py --host 127.0.0.1 --port 8765 >> "%LOGDIR%\engine.log" 2>&1"

if exist "%ROOT%\bridge\jarvis_voice_server.py" (
  echo [9b/14] Voice :8099 via jarvis_voice_server.py...
  start "AURA-Voice" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& "%VENV_PY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%LOGDIR%\voice.log" 2>&1"
) else if exist "%ROOT%\voice\server.py" (
  echo [9b/14] Voice :8099 via voice\server.py...
  start "AURA-Voice" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& "%VENV_PY%" -u voice\server.py >> "%LOGDIR%\voice.log" 2>&1"
) else (
  echo [9b/14] Voice ausente — skip
)

echo [10/14] Health ate 80s...
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){ $b=$false;$e=$false; try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null;$b=$true}catch{}; try{Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null;$e=$true}catch{}; if($b -and $e){Write-Host '      OK Bridge+Engine'; exit 0}; Start-Sleep 2}; Write-Host '      [AVISO] health incompleto'; exit 0"

if exist "%ROOT%\scripts\aura_auto_heal.py" (
  echo [10b/14] auto-heal...
  "%VENV_PY%" "%ROOT%\scripts\aura_auto_heal.py" >> "%LOGDIR%\auto_heal.log" 2>&1
)

echo [11/14] Hermes V10 chat :8777...
if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" (
  call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
) else if exist "%ROOT%\engine\agents\hermes_supervisor_agent.py" (
  start "AURA-Hermes-Supervisor" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& "%VENV_PY%" -m engine.agents.hermes_supervisor_agent --loop 30s >> "%LOGDIR%\hermes_loop.log" 2>&1"
)

if exist "%ROOT%\scripts\aura_activate_safe.py" (
  echo [12/14] activate safe...
  "%VENV_PY%" "%ROOT%\scripts\aura_activate_safe.py" >> "%LOGDIR%\activation.log" 2>&1
)

echo [12b/14] Matriz HTTP :8766...
start "AURA-Matriz-8766" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& "%VENV_PY%" -u scripts\aura_serve_matriz.py >> "%LOGDIR%\matriz8766.log" 2>&1"

echo [13/14] Desktop...
set "EXE=%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe"
if not exist "%EXE%" (
  echo       EXE ausente. Tentando publish se houver .NET 8...
  where dotnet >nul 2>&1
  if not errorlevel 1 if exist "%ROOT%\desktop\packaging\PUBLISH_WINDOWS.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\desktop\packaging\PUBLISH_WINDOWS.ps1" >> "%MASTERLOG%" 2>&1
  )
)
if exist "%EXE%" (
  echo       Abrindo %EXE%
  start "AURA Operator OS V25Q" "%EXE%"
) else (
  echo [AVISO] Sem EXE — Matriz no browser.
  start "" http://127.0.0.1:8766/index.html
  echo       Para gerar EXE: COMPILAR_E_ABRIR_DESKTOP.bat
)

echo [14/14] Smoke...
if exist "%ROOT%\scripts\smoke_test.py" (
  "%VENV_PY%" "%ROOT%\scripts\smoke_test.py" >> "%LOGDIR%\smoke.log" 2>&1
  if !ERRORLEVEL! equ 0 (echo       Smoke: PASSOU) else (echo       Smoke: FALHOU — veja logs)
) else (echo       smoke_test.py ausente — skip)

echo.
echo ================================================================
echo  RESUMO V37.3.1
echo ================================================================
powershell -NoProfile -Command "foreach($x in @(@('Bridge','http://127.0.0.1:8080/health'),@('Engine','http://127.0.0.1:8765/api/health'),@('Matriz','http://127.0.0.1:8766/health'),@('Hermes','http://127.0.0.1:8777/chat'))){ try{Invoke-WebRequest $x[1] -UseBasicParsing -TimeoutSec 2|Out-Null; Write-Host ('  {0} OK' -f $x[0])}catch{Write-Host ('  {0} OFF' -f $x[0])} }"
echo  Log: %MASTERLOG%
echo  paper_trade=true / execution_allowed=false
echo ================================================================
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
