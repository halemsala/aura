@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title AURA GROK - INSTALL
cd /d C:\aura 2>nul
if not exist "engine\server.py" (
  echo [ERRO] C:\aura nao tem o pacote AURA.
  echo Extraia o ZIP completo e rode INSTALAR_TUDO.bat a partir da pasta extraida.
  exit /b 1
)
echo ================================================================
echo  AURA GROK INSTALL — encaminha para INSTALAR_TUDO.bat
echo  paper_trade=true  execution_allowed=false
echo ================================================================
if exist "INSTALAR_TUDO.bat" (
  call INSTALAR_TUDO.bat %*
) else (
  echo [ERRO] INSTALAR_TUDO.bat ausente em C:\aura
  exit /b 1
)
echo.
echo [AURA] Seguinte: CHECK.bat  depois  AURA_GROK_ACTIVATE.bat
endlocal
exit /b 0
