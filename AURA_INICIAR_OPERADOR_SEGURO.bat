@echo off
setlocal EnableExtensions
chcp 65001 >nul
TITLE AURA - Operador Local Seguro

set "AURA_ROOT=C:\aura"
set "AURA_SCRIPTS=%AURA_ROOT%\scripts"
set "HARNESS=%AURA_ROOT%\AURA_HARNESS_CORE.py"
if not exist "%HARNESS%" set "HARNESS=%AURA_SCRIPTS%\AURA_HARNESS_CORE.py"
set "FIX=%AURA_ROOT%\sitecustomize.py"
set "CONFIG=%AURA_ROOT%\config\harness_policy.json"

if not exist "%AURA_ROOT%" (
  echo [FALHA] Pasta ausente: %AURA_ROOT%
  pause
  exit /b 1
)
if not exist "%HARNESS%" (
  echo [FALHA] AURA_HARNESS_CORE.py nao encontrado em:
  echo         %AURA_ROOT%
  echo         %AURA_SCRIPTS%
  pause
  exit /b 1
)

if not exist "%FIX%" if exist "%AURA_SCRIPTS%\sitecustomize.py" copy /Y "%AURA_SCRIPTS%\sitecustomize.py" "%FIX%" >nul
set "PYTHONPATH=%AURA_ROOT%;%AURA_SCRIPTS%"
set "NO_PROXY=127.0.0.1,localhost"
set "no_proxy=127.0.0.1,localhost"

 echo [1/4] Validando Python...
python -m py_compile "%HARNESS%"
if errorlevel 1 (
  echo [FALHA] AURA_HARNESS_CORE.py possui erro de sintaxe.
  pause
  exit /b 2
)

 echo [2/4] Testando Ollama em 127.0.0.1:11434...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet; if(-not $t){exit 1}"
if errorlevel 1 (
  echo [FALHA] Ollama nao esta acessivel em 127.0.0.1:11434.
  echo Inicie o Ollama e execute este arquivo novamente.
  pause
  exit /b 3
)

 echo [3/4] Validando politica local...
if exist "%CONFIG%" (
  echo [OK] Politica encontrada: %CONFIG%
) else (
  echo [AVISO] Politica ausente: %CONFIG%
  echo [AVISO] O harness sera iniciado sem assumir permissoes adicionais.
)

 echo [4/4] Iniciando AURA em modo operador local...
cd /d "%AURA_ROOT%"
python "%HARNESS%" %*
set "EXITCODE=%ERRORLEVEL%"

echo.
echo AURA encerrada com codigo %EXITCODE%.
pause
exit /b %EXITCODE%
