@echo off
setlocal
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%
set N=%1
if "%N%"=="" set N=500

set PY=
if exist "%ROOT%\engine\venv\Scripts\python.exe" set PY=%ROOT%\engine\venv\Scripts\python.exe
if not defined PY if exist "%ROOT%\venv\Scripts\python.exe" set PY=%ROOT%\venv\Scripts\python.exe
if not defined PY set PY=python

echo === AURA GYM — sessao de %N% cenarios (SIMULADOR, offline) ===
"%PY%" -u "%ROOT%\hermes_v10\core\aura_gym.py" %N% --root "%ROOT%"
if errorlevel 1 "%PY%" -u "%ROOT%\core\aura_gym.py" %N% --root "%ROOT%"
echo.
echo Ledger: %ROOT%\logs_supervisor\gym_ledger.jsonl
echo Destilar playbooks: "%PY%" -u "%ROOT%\hermes_v10\core\aura_gym.py" --distill --root "%ROOT%"
pause
