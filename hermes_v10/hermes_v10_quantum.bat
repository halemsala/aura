@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "MODE=%~1"
if not defined MODE set "MODE=help"
set "ROOT=%CD%"
if exist "C:\aura\engine\server.py" set "ROOT=C:\aura"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
set "PKG=%~dp0"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=llama3.2:3b"

where python >nul 2>&1 || (echo [FATAL] python & exit /b 127)

echo HERMES V10 QUANTUM mode=!MODE! ROOT=!ROOT!

if /I "!MODE!"=="help" goto HELP
if /I "!MODE!"=="seal" (
  python "%PKG%core\hermes_constitution_engine_quantum.py" --root "%PKG%." --seal
  exit /b
)
if /I "!MODE!"=="attest" (
  python "%PKG%core\hermes_constitution_engine_quantum.py" --root "%PKG%." --check
  exit /b
)
if /I "!MODE!"=="bus" (
  python "%PKG%core\hermes_event_bus.py"
  exit /b
)
if /I "!MODE!"=="pipeline" (
  set "ISSUE=%~2"
  if not defined ISSUE set "ISSUE=arruma homepage 404"
  python "%PKG%agents\hermes_correction_pipeline_quantum.py" --root "!ROOT!" --issue "!ISSUE!"
  exit /b
)
if /I "!MODE!"=="pipeline-apply" (
  set "HERMES_ALLOW_APPLY=1"
  set "HERMES_HITL_AUTO=1"
  set "ISSUE=%~2"
  if not defined ISSUE set "ISSUE=arruma homepage 404"
  python "%PKG%agents\hermes_correction_pipeline_quantum.py" --root "!ROOT!" --issue "!ISSUE!" --apply
  exit /b
)
if /I "!MODE!"=="anomaly" (
  python "%PKG%core\hermes_anomaly_detector.py" --root "!ROOT!" --train
  exit /b
)
if /I "!MODE!"=="chat" (
  start "" http://127.0.0.1:8777/chat
  if exist "%PKG%scripts\hermes_v10_chat_api.py" python "%PKG%scripts\hermes_v10_chat_api.py"
  exit /b
)
if /I "!MODE!"=="ultra-llm" (
  if exist "%PKG%..\hermes_v10_ultra_llm\hermes_v10_ultra_llm.bat" (
    call "%PKG%..\hermes_v10_ultra_llm\hermes_v10_ultra_llm.bat" ultra-llm
  ) else if exist "%PKG%agents\hermes_diagnostic_agent_llm.py" (
    python "%PKG%agents\hermes_diagnostic_agent_llm.py" --root "!ROOT!" --context "Diagnostico AURA"
  )
  exit /b
)

:HELP
echo Hermes V10 QUANTUM:
echo   seal            - grava attestation de boot
echo   attest          - verifica attestation
echo   bus             - teste event bus WAL
echo   pipeline "..."  - propose+sandbox+HITL sem aplicar
echo   pipeline-apply  - aplica se ALLOW_APPLY+HITL
echo   anomaly         - IsolationForest
echo   chat            - API 8777
exit /b 0
