@echo off
setlocal
cd /d "%~dp0"
if not exist "%CD%\scripts\aura_serve_matriz.py" if exist "C:\aura\scripts\aura_serve_matriz.py" cd /d C:\aura
set "ROOT=%CD%"
set "AURA_ROOT=%ROOT%"
set "PYTHONUTF8=1"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
echo Matriz http://127.0.0.1:8766/index.html
"%VPY%" -u "%ROOT%\scripts\aura_serve_matriz.py"
endlocal
