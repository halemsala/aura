@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA START ALL
echo ================================================================
echo  AURA START ALL - Bridge + Engine + Matriz + Hermes
echo                 + Control API :8790 + Voz :8099
echo ================================================================
call "%~dp0AURA_TUDO_EM_UM.bat" NOPAUSE
call "%~dp0AURA_HERMES_V10_ULTRA.bat" bg
call "%~dp0AURA_TOOLS_CONTROL_API.bat" NOPAUSE
call "%~dp0AURA_SUBIR_VOZ.bat"
call "%~dp0AURA_ABRIR_DESKTOP.bat"
timeout /t 3 >nul
echo.
echo ===== PORTAS =====
powershell -NoProfile -Command "8080,8765,8777,8778,8766,8099,8790,11434|%%{$c=Get-NetTCPConnection -LocalPort $_ -State Listen -EA SilentlyContinue; if($c){'LISTEN '+$_}else{'OFF    '+$_}}"
echo.
echo   http://127.0.0.1:8080/health
echo   http://127.0.0.1:8765/api/health
echo   http://127.0.0.1:8766/index.html
echo   http://127.0.0.1:8777/chat
echo   http://127.0.0.1:8790/health
echo.
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
