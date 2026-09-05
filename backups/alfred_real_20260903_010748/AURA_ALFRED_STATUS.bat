@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AURA Alfred - Status
set "ROOT=%~dp0"
cd /d "%ROOT%"
python -m alfred.service status
echo.
echo Ollama (porta 11434):
python -c "import requests;print('ollama:', requests.get('http://127.0.0.1:11434/api/tags',timeout=3).status_code)" 2>nul || echo ollama: INDISPONIVEL
pause
exit /b 0
