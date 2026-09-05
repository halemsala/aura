@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PYTHON="
if exist "%ROOT%\engine\venv\Scripts\python.exe" set "PYTHON=%ROOT%\engine\venv\Scripts\python.exe"
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON (
  echo [ERRO] Python nao encontrado.
  echo Instala Python 3.11+ ou cria engine\venv.
  pause
  exit /b 2
)

set "AURA_ROOT=%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PYTHONPATH=%ROOT%;%ROOT%\scripts;%ROOT%\hermes_v10"
set "ALFRED_HOST=127.0.0.1"
set "ALFRED_PORT=8791"
set "AURA_NO_BROWSER=1"
set "AURA_AUTO_OPEN_UI=0"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "OLLAMA_MODEL=qwen3:8b"
set "AURA_OLLAMA_MODEL=qwen3:8b"
set "HERMES_ALLOW_CLOUD=0"
set "AURA_GLM_ENABLED=0"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor" >nul 2>&1

if not exist "%ROOT%\alfred_capabilities.py" (
  echo [ERRO] Falta alfred_capabilities.py na raiz.
  pause
  exit /b 3
)

"%PYTHON%" -m py_compile "%ROOT%\alfred_capabilities.py" "%ROOT%\alfred_install.py"
if errorlevel 1 (
  echo [ERRO] Falha de sintaxe no codigo ALFRED.
  pause
  exit /b 4
)

powershell.exe -NoLogo -NoProfile -Command "$t=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; if (@($t.models | %% { $_.name }) -contains 'qwen3:8b') { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [ERRO] qwen3:8b nao foi detectado no Ollama local.
  echo [INFO] O ALFRED nao vai arrancar com um modelo de fallback.
  pause
  exit /b 7
)

echo [OK] qwen3:8b detectado no Ollama local.
"%PYTHON%" "%ROOT%\alfred_capabilities.py" --ask "Responde apenas OK." > "%ROOT%\logs_supervisor\alfred_qwen3_test.json" 2>&1
if errorlevel 1 (
  echo [ERRO] O qwen3:8b foi encontrado, mas falhou no teste de inferencia.
  type "%ROOT%\logs_supervisor\alfred_qwen3_test.json"
  pause
  exit /b 8
)
echo [OK] Inferencia real qwen3:8b concluida.

"%PYTHON%" "%ROOT%\alfred_install.py" > "%ROOT%\logs_supervisor\alfred_install.log" 2>&1
if errorlevel 1 (
  echo [ERRO] A ponte ALFRED nao foi instalada.
  type "%ROOT%\logs_supervisor\alfred_install.log"
  pause
  exit /b 5
)

if exist "%ROOT%\logs_supervisor\alfred.pid" (
  set /p OLD_PID=<"%ROOT%\logs_supervisor\alfred.pid"
  tasklist /FI "PID eq !OLD_PID!" 2>nul | findstr /I "!OLD_PID!" >nul
  if not errorlevel 1 goto :already_running
)

if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor" >nul 2>&1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$out=Join-Path $env:ROOT 'logs_supervisor\alfred.out.log'; $err=Join-Path $env:ROOT 'logs_supervisor\alfred.err.log'; $script=Join-Path $env:ROOT 'alfred_capabilities.py'; $p=Start-Process -FilePath $env:PYTHON -ArgumentList @('-u',$script,'--serve') -WorkingDirectory $env:ROOT -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru; Set-Content -LiteralPath (Join-Path $env:ROOT 'logs_supervisor\alfred.pid') -Value $p.Id"
if errorlevel 1 (
  echo [ERRO] Nao foi possivel iniciar o processo ALFRED.
  pause
  exit /b 6
)

:already_running
set "HEALTH="
for /L %%N in (1,1,20) do (
  for /f "usebackq delims=" %%H in (`powershell.exe -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8791/health' -TimeoutSec 1).StatusCode } catch { 0 }"`) do set "HEALTH=%%H"
  if "!HEALTH!"=="200" goto :ok
  >nul timeout /t 1 /nobreak
)

echo [ERRO] ALFRED nao ficou online na porta 8791.
echo [INFO] Verifica logs_supervisor\alfred_install.log e data\alfred\actions.jsonl.
pause
exit /b 6

:ok
exit /b 0
