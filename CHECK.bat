@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title AURA CHECK
cd /d "%~dp0"
if exist "%CD%\engine\server.py" (
  set "ROOT=%CD%"
) else if exist "C:\aura\engine\server.py" (
  cd /d C:\aura
  set "ROOT=C:\aura"
) else (
  echo [FALTA] engine\server.py
  exit /b 1
)
set "MODE=final"
if /I "%~1"=="files" set "MODE=files"
if /I "%~1"=="services" set "MODE=services"
if /I "%~1"=="final" set "MODE=final"
if /I "%~1"=="/FILES" set "MODE=files"
if /I "%~1"=="/SERVICOS" set "MODE=services"
if /I "%~1"=="/FINAL" set "MODE=final"

if exist "%ROOT%\scripts\AURA_CHECK.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\AURA_CHECK.ps1" -Root "%ROOT%" -Mode %MODE%
) else (
  echo ===== CHECK fallback =====
  if exist engine\server.py (echo [OK] engine\server.py) else echo [FALTA] engine\server.py
  if exist bridge\server.py (echo [OK] bridge\server.py) else echo [FALTA] bridge\server.py
  if exist engine\venv\Scripts\python.exe (echo [OK] venv) else echo [FALTA] venv
  echo.
  echo ===== PORTAS =====
  for %%P in (8080 8765 8766 8777 8778 8099 11434) do (
    netstat -ano ^| findstr /R /C:":%%P .*LISTENING" >nul
    if errorlevel 1 (echo OFF    %%P) else (echo LISTEN %%P)
  )
  echo Bridge  http://127.0.0.1:8080/health
  echo Engine  http://127.0.0.1:8765/api/health
  echo Matriz  http://127.0.0.1:8766/index.html
  echo Hermes  http://127.0.0.1:8777/chat
)
endlocal
exit /b 0
