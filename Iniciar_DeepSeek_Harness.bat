@echo off
title DeepSeek Harness - AURA
cd /d C:\aura\deepseek-harness

echo.
echo  Iniciando DeepSeek Harness...
echo  URL: http://127.0.0.1:3080
echo.

pnpm dsh web

pause
