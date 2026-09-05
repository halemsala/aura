@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Subir Stack Completo
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "AURA_EXECUTION_ALLOWED=0"
set "PYTHONUTF8=1"
set "CORNERAI_BRIDGE_REQUIRE_TOKEN=0"
if not defined AURA_JARVIS_MODEL set "AURA_JARVIS_MODEL=qwen2.5:3b-instruct"
if not defined AURA_OLLAMA_MODEL set "AURA_OLLAMA_MODEL=qwen2.5:3b-instruct"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"

echo ================================================================
echo  AURA STACK COMPLETO
echo  Bridge + Engine + Matriz + Hermes + Control API + Voz
echo  paper_trade=true  execution_allowed=false
echo ================================================================

call "%ROOT%\AURA_TUDO_EM_UM.bat"
call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
call "%ROOT%\AURA_TOOLS_CONTROL_API.bat"
call "%ROOT%\AURA_SUBIR_VOZ.bat"

timeout /t 3 >nul
echo.
echo ===== PORTAS =====
powershell -NoProfile -Command "8080,8765,8766,8777,8099,8790,11434|%%{$c=Get-NetTCPConnection -LocalPort $_ -State Listen -EA SilentlyContinue; if($c){'LISTEN '+$_}else{'OFF    '+$_}}"
echo.
echo   Bridge   http://127.0.0.1:8080/health
echo   Engine   http://127.0.0.1:8765/api/health
echo   Matriz   http://127.0.0.1:8766/index.html
echo   Hermes   http://127.0.0.1:8777/chat
echo   Control  http://127.0.0.1:8790/health
echo.
echo Logs: %ROOT%\logs_supervisor\
pause
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
