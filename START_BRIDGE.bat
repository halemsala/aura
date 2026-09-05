@echo off
setlocal
cd /d "%~dp0"
if not exist "%CD%\bridge\server.py" if exist "C:\aura\bridge\server.py" cd /d C:\aura
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
echo AURA Bridge :8080
"%VPY%" -u "%ROOT%\bridge\server.py" --host 127.0.0.1 --port 8080
endlocal
