@echo off
setlocal
cd /d C:\aura 2>nul
if "%AURA_TELEGRAM_OPERATOR_TOKEN%"=="" (
  echo Defina AURA_TELEGRAM_OPERATOR_TOKEN e passe o mesmo em --operator-token
  exit /b 1
)
set PYTHONPATH=%CD%\addons\telegram_intel_optin\src;%PYTHONPATH%
if exist engine\venv\Scripts\python.exe (
  engine\venv\Scripts\python.exe -m telegram_intel.worker_main --grant-session --operator-token %AURA_TELEGRAM_OPERATOR_TOKEN%
) else (
  py -3.11 -m telegram_intel.worker_main --grant-session --operator-token %AURA_TELEGRAM_OPERATOR_TOKEN%
)
endlocal
