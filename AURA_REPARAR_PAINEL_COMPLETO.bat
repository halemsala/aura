@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA REPARAR PAINEL COMPLETO
color 0B
set "ROOT=%CD%"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  AURA REPARAR PAINEL — testes + sobe servicos + relatorio
echo  paper_trade=true  execution_allowed=false
echo ================================================================

if not exist "%ROOT%\scripts\aura_reparar_painel_completo.py" (
  echo [ERRO] scripts\aura_reparar_painel_completo.py ausente
  echo Extraia o ZIP FIXED completo para C:\aura
  pause
  exit /b 1
)

set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [VENV] a criar...
  py -3.11 -m venv "%ROOT%\engine\venv"
  set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
)

"%VPY%" -u "%ROOT%\scripts\aura_reparar_painel_completo.py"
set RC=%ERRORLEVEL%

echo.
echo Relatorio:
echo   %ROOT%\logs_supervisor\RELATORIO_REPARO_PAINEL_LATEST.md
echo   %ROOT%\logs_supervisor\RELATORIO_REPARO_PAINEL_LATEST.json
echo.
if exist "%ROOT%\logs_supervisor\RELATORIO_REPARO_PAINEL_LATEST.md" (
  type "%ROOT%\logs_supervisor\RELATORIO_REPARO_PAINEL_LATEST.md"
)

echo.
echo Hub: http://127.0.0.1:8766/tools-hub.html
if %RC%==0 start "" "http://127.0.0.1:8766/tools-hub.html"
pause
endlocal
exit /b %RC%
