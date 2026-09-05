@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA ALFRED COMMAND
if "%~1"=="" (
  echo Uso: AURA_ALFRED_COMMAND.bat Alfred, estado
  echo      AURA_ALFRED_COMMAND.bat "Alfred, abre tres pesquisas sobre automacao"
  pause
  exit /b 2
)
python -m alfred.boot ask %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERRO] comando Alfred falhou.
  pause
  exit /b %RC%
)
pause
exit /b 0
