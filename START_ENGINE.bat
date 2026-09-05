@echo off
setlocal
cd /d "%~dp0"
if not exist "%CD%\engine\server.py" if exist "C:\aura\engine\server.py" cd /d C:\aura
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "PYTHONPATH=%ROOT%;%ROOT%\engine;%ROOT%\bridge"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "AURA_UNLOCK_LIVE=0"
set "GLM_ADVISORY_ONLY=true"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
echo AURA Engine :8765
"%VPY%" -u "%ROOT%\engine\server.py" --host 127.0.0.1 --port 8765
endlocal
