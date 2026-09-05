@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA - Abrir Matriz
set "ROOT=%CD%"
set "AURA_ROOT=%ROOT%"
set "VENV_PY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=python"
echo [Matriz] Nao reinstala. Sobe :8766 se estiver OFF e abre o browser.
powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:8766/health' -TimeoutSec 2|Out-Null; exit 0}catch{exit 1}"
if errorlevel 1 (
  echo [Matriz] subindo http://127.0.0.1:8766/
  start "AURA-Matriz-8766" /MIN cmd /c "cd /d "%ROOT%" && set AURA_ROOT=%ROOT%&& set PYTHONUTF8=1&& "%VENV_PY%" -u scripts\aura_serve_matriz.py >> "%ROOT%\logs_supervisor\matriz8766.log" 2>&1"
  timeout /t 2 /nobreak >nul
)
if exist "%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe" (
  start "" "%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe"
) else (
  start "" http://127.0.0.1:8766/index.html
)
echo F1 Matriz no Desktop ^| browser: http://127.0.0.1:8766/index.html
endlocal
