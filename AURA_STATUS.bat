@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA STATUS
echo Ollama :11434  Alfred :8791  Hermes :8777
python -m alfred.boot status
set "RC=%ERRORLEVEL%"
echo.
echo Chat: http://127.0.0.1:8777/chat
echo Logs: data\alfred\  logs_supervisor\
if not "%RC%"=="0" (
  echo [AVISO] pelo menos um servico falhou o health check.
)
pause
exit /b %RC%
