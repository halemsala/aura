@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA GPU SHARE EXPORT
echo Gera o ZIP do worker para copiar para outro PC.
echo Nao abre browser. Nao expoe a porta 8791.
python -m alfred.gpu_share.export
echo.
echo Pasta: data\alfred\gpu_share\export\
pause
exit /b 0
