@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA START ALL
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "LOG=%ROOT%\logs_supervisor\grok_audit\start_all.log"
if not exist "%ROOT%\logs_supervisor\grok_audit" mkdir "%ROOT%\logs_supervisor\grok_audit" >nul 2>&1
echo ================================================================
echo AURA START ALL  root=%ROOT%
echo Log=%LOG%
echo Nao abre navegador. Sobe supervisor que mantem Alfred+Hermes.
echo Chat: AURA_OPEN_CHAT.bat
echo ================================================================
if not exist "%ROOT%\alfred\api.py" (
  echo [ERRO] Falta alfred\api.py. Esta pasta nao e C:\aura.
  echo Log: %LOG%
  pause
  exit /b 2
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao esta no PATH.
  pause
  exit /b 3
)
python -m alfred.boot start
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERRO] arranque falhou. Consulta %LOG%
  echo        e data\alfred\stderr.log / logs_supervisor\hermes_v10.log
  pause
  exit /b %RC%
)
echo Arranque OK. Esta janela nao fecha sozinha.
pause
exit /b 0
