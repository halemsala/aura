@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if not exist "%CD%\hermes_v10\scripts\hermes_v10_chat_api.py" if exist "C:\aura\hermes_v10\scripts\hermes_v10_chat_api.py" cd /d C:\aura
set "ROOT=%CD%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach($p in 8777,8778){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | ForEach-Object { if($_.OwningProcess -gt 4){ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue } } }"
if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" (
  call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
) else (
  echo [ERRO] AURA_HERMES_V10_ULTRA.bat ausente
  echo.
  echo [AURA] Erro acima. Janela mantida.
  pause
  exit /b 1
)
endlocal

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
