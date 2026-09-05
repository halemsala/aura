@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%CD%"
set "EXE=%ROOT%\desktop\publish\Aura.QuantX.Desktop.exe"
if exist "%EXE%" (
  echo [Desktop] %EXE%
  start "" "%EXE%"
  echo F1 Matriz ^| F2 SokkerPRO ^| F11 max
  goto :eof
)
echo [AVISO] EXE em falta: desktop\publish\Aura.QuantX.Desktop.exe
echo Fallback: Matriz no browser :8766
if exist "%ROOT%\ABRIR_MATRIZ.bat" call "%ROOT%\ABRIR_MATRIZ.bat"
echo Para gerar o EXE: COMPILAR_E_ABRIR_DESKTOP.bat  (precisa .NET 8 SDK + WebView2)
endlocal
