@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title AURA Operator Autonomo
color 0A
cd /d "%~dp0"
echo ================================================================
echo  AURA INSTALADOR AUTONOMO V37.3.47
echo  paper_trade=true  execution_allowed=false
echo  Esta janela NAO fecha sozinha.
echo ================================================================
echo ROOT=%CD%
where powershell >nul 2>&1
if errorlevel 1 (
  echo [FATAL] PowerShell nao encontrado.
  pause
  exit /b 1
)
if not exist "%~dp0AURA_MOTOR_AUTONOMO.ps1" (
  echo [FATAL] Falta AURA_MOTOR_AUTONOMO.ps1 nesta pasta.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AURA_MOTOR_AUTONOMO.ps1" -Root "%CD%"
set ERR=%ERRORLEVEL%
echo.
echo Codigo de saida=%ERR%
echo.
echo [AURA] Revisa o relatorio acima. Qualquer tecla fecha.
pause
exit /b %ERR%
