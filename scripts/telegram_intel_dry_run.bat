@echo off
setlocal
cd /d C:\aura 2>nul
echo [Telegram Intel] DRY-RUN status — nao envia mensagens se DRY_RUN=1 ou ENABLED=0
set PYTHONPATH=%CD%\addons\telegram_intel_optin\src;%PYTHONPATH%
if exist engine\venv\Scripts\python.exe (
  engine\venv\Scripts\python.exe -m telegram_intel.worker_main --status
) else (
  py -3.11 -m telegram_intel.worker_main --status
)
endlocal
