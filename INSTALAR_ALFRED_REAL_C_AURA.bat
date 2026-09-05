@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "HERE=%~dp0"
set "ZIP=%HERE%ALFRED_AURA_COMPLETO_QWEN3.zip"
set "TARGET=C:\aura"
set "PS1=%HERE%INSTALAR_ALFRED_REAL_C_AURA.ps1"
set "LOG=%TARGET%\logs_supervisor\alfred_real_install.log"
if not exist "%ZIP%" if exist "%USERPROFILE%\Downloads\ALFRED_AURA_COMPLETO_QWEN3.zip" set "ZIP=%USERPROFILE%\Downloads\ALFRED_AURA_COMPLETO_QWEN3.zip"
if not exist "%ZIP%" (
  echo [ERRO] ALFRED_AURA_COMPLETO_QWEN3.zip nao encontrado.
  echo Coloca o ZIP ao lado deste BAT ou em Downloads.
  pause
  exit /b 2
)
if not exist "%PS1%" (
  echo [ERRO] INSTALAR_ALFRED_REAL_C_AURA.ps1 nao encontrado.
  echo Coloca o PS1 ao lado deste BAT.
  pause
  exit /b 2
)
if not exist "%TARGET%\logs_supervisor" mkdir "%TARGET%\logs_supervisor" >nul 2>&1

echo ================================================================
echo INSTALADOR REAL ALFRED COMPLETO / QWEN3
 echo ZIP: %ZIP%
echo DESTINO: %TARGET%
echo ================================================================
echo.
echo A janela permanecera aberta para mostrar qualquer erro.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Zip "%ZIP%" -Target "%TARGET%" -Log "%LOG%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [OK] CODIGOS INSTALADOS EM C:\aura.
  echo [INFO] Para iniciar: C:\aura\FINALIZAR_AURA_ALFRED_QWEN3.bat
) else (
  echo [ERRO] Instalacao terminou com codigo %RC%.
  echo [INFO] Log: %LOG%
)
echo.
echo Pressiona uma tecla para fechar esta janela.
pause >nul
exit /b %RC%
