@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if not exist "%CD%\engine\server.py" if exist "C:\aura\engine\server.py" cd /d C:\aura
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
title AURA ASSISTENTE COMPLETO
echo ================================================================
echo  AURA assistente completo — NAO mata Hermes :8777 nem Ollama
echo ================================================================
if exist "%ROOT%\AURA_INSTALAR_VOZ.bat" call "%ROOT%\AURA_INSTALAR_VOZ.bat"
echo Activar agentes + monitor...
"%VPY%" -c "import sys; from pathlib import Path; r=Path(r'%ROOT%'); sys.path.insert(0,str(r/'scripts')); import aura_chat_agents as a; print(a.activate_analysis_agents()); print(a.start_system_monitor())"
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if errorlevel 1 (
  echo Hermes OFF — a subir sem derrubar o que ja existe
  if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
) else (
  echo Hermes ja LISTEN :8777 — nao reinicia (evita o chat cair)
)
echo.
echo Matriz  http://127.0.0.1:8766/index.html
echo Hermes  http://127.0.0.1:8777/chat
echo Voz     http://127.0.0.1:8099/api/voice/health
echo paper_trade=true  execution_allowed=false
endlocal
exit /b 0
