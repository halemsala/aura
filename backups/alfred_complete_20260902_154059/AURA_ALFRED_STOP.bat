@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PIDFILE=%ROOT%\logs_supervisor\alfred.pid"
if not exist "%PIDFILE%" exit /b 0
set /p PID=<"%PIDFILE%"
if not defined PID exit /b 0
for /f "tokens=2 delims=," %%P in ('tasklist /FI "PID eq %PID%" /FO CSV /NH 2^>nul') do if "%%~P"=="%PID%" taskkill /PID %PID% /T >nul 2>&1
del /q "%PIDFILE%" >nul 2>&1
exit /b 0
