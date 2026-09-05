@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA OPEN CHAT
curl.exe -s --max-time 3 http://127.0.0.1:8777/health >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Hermes nao responde em http://127.0.0.1:8777/health
  echo Corre AURA_START_ALL.bat primeiro.
  pause
  exit /b 1
)
echo A abrir http://127.0.0.1:8777/chat
start "" "http://127.0.0.1:8777/chat"
exit /b 0
