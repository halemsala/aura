@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "URL=http://127.0.0.1:8777/chat"
echo A verificar Hermes em %URL% ...
curl.exe -s --max-time 5 -o nul -w "HTTP=%%{http_code}\n" "%URL%"
if errorlevel 1 (
  echo [AVISO] Hermes nao respondeu. O Alfred pode estar online, mas o chat Hermes nao esta activo.
  echo Para iniciar o Alfred local: FINALIZAR_AURA_ALFRED_QWEN3.bat
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -Command "Start-Process '%URL%'"
exit /b 0
