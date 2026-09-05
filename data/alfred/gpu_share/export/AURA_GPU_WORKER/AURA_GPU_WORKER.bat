@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AURA GPU WORKER
set AURA_GPU_SHARE_MAX_PCT=60
where python.exe >nul 2>&1 || (echo Instala Python 3.11+ & pause & exit /b 2)
echo Este PC vai oferecer ate 60%% da VRAM ao Aura. Pausa automatica com jogos.
echo Por defeito so localhost. Para LAN neste PC: AURA_GPU_WORKER.bat lan
set LAN=
if /I "%~1"=="lan" set LAN=--lan
python worker.py --token gGyQBw_1ayIyIYHfH9zCQ6Ir_AQ-ab_l --port 8795 --max-pct 60 %LAN%
pause
