@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%CD%"
set "VENV_PY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=python"
set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_PAPER_TRADE=1"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "GLM_ADVISORY_ONLY=true"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
set "PYTHONUTF8=1"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
echo ================================================================
echo  AURA ARRANQUE DIARIO — nao destroi venv, nao mata Ollama
echo ================================================================
echo [check] se Bridge+Engine ja estao UP, nao religa por cima
powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null; Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if not errorlevel 1 (
  echo   Bridge+Engine ja OK — skip start
  goto AFTER_CORE
)
echo [Bridge :8080]
start "AURA-Bridge" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set CORNERAI_BRIDGE_REQUIRE_TOKEN=0&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u bridge\server.py --host 127.0.0.1 --port 8080 >> "%LOGDIR%\bridge.log" 2>&1"
echo [Engine :8765]
start "AURA-Engine" /MIN cmd /c "cd /d %ROOT% && set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set AURA_EXECUTION_ALLOWED=0&& set AURA_UNLOCK_LIVE=0&& set GLM_ADVISORY_ONLY=true&& set PYTHONUTF8=1&& set AURA_ROOT=%ROOT%&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u engine\server.py --host 127.0.0.1 --port 8765 >> "%LOGDIR%\engine.log" 2>&1"
echo Aguardando health...
powershell -NoProfile -Command "for($i=0;$i -lt 20;$i++){ $b=$false;$e=$false; try{Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 2|Out-Null;$b=$true}catch{}; try{Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2|Out-Null;$e=$true}catch{}; if($b -and $e){Write-Host '  Bridge+Engine OK'; exit 0}; Start-Sleep 2}; Write-Host '  [AVISO] health incompleto'"
:AFTER_CORE
powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8766/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if errorlevel 1 (
  echo [Matriz :8766]
  start "AURA-Matriz-8766" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& set PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge&& "%VENV_PY%" -u scripts\aura_serve_matriz.py >> "%LOGDIR%\matriz8766.log" 2>&1"
)
echo Pronto. Depois: .\AURA_HERMES_V10_ULTRA.bat bg
echo Desktop: .\AURA_ABRIR_DESKTOP.bat
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
