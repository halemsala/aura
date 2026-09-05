@echo off
cd /d "%~dp0"
echo AURA — a iniciar instalacao via PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALAR_AGORA.ps1"
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
pause
