@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AURA Alfred - Start
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PIDFILE=data\alfred\alfred.pid"
if exist "%PIDFILE%" (
  set /p PID=<"%PIDFILE%"
  tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
  if not errorlevel 1 (
    echo Alfred ja esta a correr ^(PID %PID%^). Nada a fazer.
    pause
    exit /b 0
  )
)
echo A iniciar Alfred API em 127.0.0.1:8791 ^(sem abrir navegador^)...
start "AURA Alfred" /min cmd /c "python -m alfred.api 2>>data\alfred\stderr.log"
timeout /t 4 /nobreak >nul
python -m alfred.service status
echo.
echo Se o /health estiver INDISPONIVEL, consulta data\alfred\stderr.log
pause
exit /b 0
