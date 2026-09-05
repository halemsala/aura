@echo off
setlocal
REM AURA LAB — atalho para configurar Agendador + AURA_LAB_ROOT
REM Clique duplo ou: INSTALL_OPS_DAEMON_WINDOWS.bat

cd /d "%~dp0\.."
set "LAB=%CD%"

echo.
echo Pasta LAB: %LAB%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_OPS_DAEMON_WINDOWS.ps1" -LabRoot "%LAB%" -IntervalMinutes 5
if errorlevel 1 (
  echo.
  echo Falhou. Abra PowerShell como usuario normal e rode:
  echo   Set-ExecutionPolicy -Scope Process Bypass
  echo   cd /d %LAB%
  echo   .\tools\INSTALL_OPS_DAEMON_WINDOWS.ps1
  pause
  exit /b 1
)

echo.
pause
endlocal
