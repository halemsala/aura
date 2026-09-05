@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA STOP ALL
echo A parar apenas Alfred :8791 e Hermes :8777. Ollama nao e tocado.
python -m alfred.boot stop
if errorlevel 1 (
  echo [ERRO] stop falhou. Log: logs_supervisor\grok_audit\start_all.log
  pause
  exit /b 1
)
echo Stop OK.
pause
exit /b 0
