@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "PKG=%CD%"
set "ROOT=%CD%"
if exist "C:\aura\engine\server.py" set "ROOT=C:\aura"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=llama3.2:3b"
set "MODE=%~1"
if not defined MODE set "MODE=help"
where python >nul 2>&1 || (echo [FATAL] python & exit /b 127)
echo HERMES V10 ULTRA COMPLETE mode=!MODE! ROOT=!ROOT!
if /I "!MODE!"=="setup" (python "%PKG%\scripts\hermes_setup_validator.py" --root "!ROOT!" & exit /b)
if /I "!MODE!"=="test" (python "%PKG%\tests\test_core.py" & exit /b)
if /I "!MODE!"=="security" (python "%PKG%\security\hermes_integrity_guard.py" --root "%PKG%" & exit /b)
if /I "!MODE!"=="constitution" (python "%PKG%\core\hermes_constitution_engine.py" --root "!ROOT!" --check status & exit /b)
if /I "!MODE!"=="orch" (python "%PKG%\orchestrator\hermes_orchestrator_v10.py" --root "!ROOT!" --once & exit /b)
if /I "!MODE!"=="anomaly" (python "%PKG%\core\hermes_anomaly_detector.py" --root "!ROOT!" --train & exit /b)
if /I "!MODE!"=="chat" (
  start "" http://127.0.0.1:8777/chat
  python "%PKG%\scripts\hermes_v10_chat_api.py"
  exit /b
)
if /I "!MODE!"=="dash" (
  start "" http://127.0.0.1:8778/
  python "%PKG%\dashboard\hermes_dashboard_ultra.py"
  exit /b
)
if /I "!MODE!"=="ultra" (
  start "" python "%PKG%\dashboard\hermes_dashboard_ultra.py"
  timeout /t 1 >nul
  start "" http://127.0.0.1:8778/
  start "" http://127.0.0.1:8777/chat
  python "%PKG%\scripts\hermes_v10_chat_api.py"
  exit /b
)
echo setup test security constitution orch anomaly chat dash ultra
echo sbom: python core/hermes_sbom_attestation.py
exit /b 0
