@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AURA Alfred - Stop
set "ROOT=%~dp0"
cd /d "%ROOT%"
python -m alfred.service stop
if errorlevel 1 ( echo AVISO: stop devolveu erro - ver mensagem acima. & pause & exit /b 1 )
echo Alfred parado ^(apenas o PID registado foi terminado^).
pause
exit /b 0
