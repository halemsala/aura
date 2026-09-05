@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title AURA INSTALL TO C:\aura
if "%~1"=="" (
  echo Uso: AURA_INSTALL_TO_C_AURA.bat CAMINHO\pacote.zip
  echo Expande o ZIP para C:\aura sem apagar a instalacao existente.
  pause
  exit /b 2
)
if not exist "%~1" (
  echo [ERRO] ZIP nao encontrado: %~1
  pause
  exit /b 3
)
if not exist "C:\aura" mkdir "C:\aura"
echo A expandir "%~1" para C:\aura
powershell.exe -NoLogo -NoProfile -Command "Expand-Archive -LiteralPath '%~1' -DestinationPath 'C:\aura' -Force"
if errorlevel 1 (
  echo [ERRO] Expand-Archive falhou.
  pause
  exit /b 4
)
cd /d C:\aura
if not exist "alfred\api.py" (
  echo [ERRO] ZIP extraido mas falta alfred\api.py em C:\aura.
  pause
  exit /b 5
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao esta no PATH.
  pause
  exit /b 6
)
python -m pip install -r requirements-alfred.txt
if errorlevel 1 (
  echo [ERRO] pip install falhou.
  pause
  exit /b 7
)
echo Instalacao concluida. Corre C:\aura\AURA_START_ALL.bat
pause
exit /b 0
