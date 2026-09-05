@echo off
chcp 65001 >nul
title AURA Local AIOps
cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File "%~dp0ATIVAR_TUDO.ps1"
pause
