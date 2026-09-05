@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d C:\aura
title DeepSeek Harness LOCAL Aura
set "DSH_HOME=%USERPROFILE%\.dsh"
set "DSH_PERMISSION_MODE=workspace-write"
set "DSH_TELEMETRY_DISABLED=1"
set "AURA_NO_BROWSER=1"
echo Harness LOCAL http://127.0.0.1:3080  workspace=C:\aura  modelo=qwen3:8b
:LOOP
dsh --profile web --host 127.0.0.1 --port 3080 --no-open
echo Harness saiu — a relancar em 5s
timeout /t 5 /nobreak >nul
goto LOOP
