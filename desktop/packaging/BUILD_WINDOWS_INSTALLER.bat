@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "INNO=%~1"
if defined INNO if not exist "%INNO%" set "INNO="
if not defined INNO for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined INNO set "INNO=%%I"
if not defined INNO if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "INNO=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined INNO if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "INNO=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined INNO if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "INNO=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined INNO (
  echo ================================================================
  echo AURA QUANT-X V25 - WINDOWS INSTALLER BUILD
  echo ================================================================
  echo.
  echo [ERROR] Inno Setup 6 was not found.
  echo Install Inno Setup 6+ or run this file with the full path to ISCC.exe.
  echo Example:
  echo BUILD_WINDOWS_INSTALLER.bat "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  echo.
  exit /b 3
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows PowerShell was not found.
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD_WINDOWS_INSTALLER.ps1" -InnoSetupPath "%INNO%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ERROR] Build failed with code %RC%.
  echo See desktop\packaging\README_WINDOWS_INSTALLER_V25.md.
  exit /b %RC%
)

echo.
echo [OK] Installer created in "%ROOT%\dist_installer".
endlocal & exit /b 0
