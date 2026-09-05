@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AURA Alfred - Install
set "ROOT=%~dp0"
cd /d "%ROOT%"
if not exist "requirements-alfred.txt" (
  echo ERRO: %CD% nao parece ser a pasta do projecto ^(falta requirements-alfred.txt^).
  goto :fail
)
echo [1/5] Verificar Python...
python --version >nul 2>&1
if errorlevel 1 ( echo ERRO: Python nao encontrado no PATH. & goto :fail )
python --version
echo [2/5] Backup de instalacao anterior...
if exist "alfred" xcopy "alfred" "data\alfred\backups\alfred-prev\" /E /I /Y /Q >nul
if exist "config\alfred.json" if not exist "data\alfred\backups\config" mkdir "data\alfred\backups\config"
if exist "config\alfred.json" copy /Y "config\alfred.json" "data\alfred\backups\config\" >nul
echo [3/5] Instalar dependencias...
python -m pip install -r requirements-alfred.txt
if errorlevel 1 goto :fail
echo [4/5] Compilar modulos...
python -m compileall -q -f alfred
if errorlevel 1 goto :fail
echo [5/5] Verificar import do bridge...
python -c "from alfred import tools; from alfred.bridge import try_handle; print('bridge OK')"
if errorlevel 1 goto :fail
echo.
echo INSTALACAO CONCLUIDA. Usa AURA_ALFRED_START.bat para arrancar.
pause
exit /b 0
:fail
echo.
echo *** FALHA NA INSTALACAO - ver mensagens acima ***
pause
exit /b 1
