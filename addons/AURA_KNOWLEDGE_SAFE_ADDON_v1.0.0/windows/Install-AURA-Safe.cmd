@echo off
setlocal
set SCRIPT=%~dp0Install-AURA-Safe.ps1
if "%~1"=="" set MODE=Plan
if not "%~1"=="" set MODE=%~1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Mode "%MODE%" -AURARoot "%~2"
if errorlevel 1 exit /b %errorlevel%
endlocal
