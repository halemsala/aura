@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Alfred sempre ligado
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "AURA_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%;%ROOT%\bridge"
set "PYTHONUTF8=1"
set "AURA_TTS_ENGINE=edge"
set "KANTEIRO_NEURAL_VOICE=pt-BR-HumbertoNeural"
set "AURA_NO_BROWSER=1"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "OLLAMA_KEEP_ALIVE=-1"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_NUM_PARALLEL=1"
set "KANTEIRO_NEURAL_PITCH=-18Hz"
set "KANTEIRO_NEURAL_RATE=-15%"

echo Alfred sempre ligado — nao precisa do Desktop Aura aberto.
echo Sobe supervisor (Alfred :8791 + Hermes :8777). Ollama nunca e morto.
echo Chat: http://127.0.0.1:8777/chat
echo.

if /I "%~1"=="inicio" (
  set "ST=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
  if not exist "%ST%" mkdir "%ST%" >nul 2>&1
  echo @echo off> "%ST%\AURA_Alfred.bat"
  echo cd /d "%ROOT%">> "%ST%\AURA_Alfred.bat"
  echo start "" /MIN "%ROOT%\AURA_ALFRED_SEMPRE_LIGADO.bat" silent>> "%ST%\AURA_Alfred.bat"
  reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v AURA_Alfred /t REG_SZ /d "\"%ROOT%\AURA_ALFRED_SEMPRE_LIGADO.bat\" silent" /f >nul 2>&1
  echo Atalho de arranque Windows criado em:
  echo   %ST%\AURA_Alfred.bat
  echo   HKCU\...\Run\AURA_Alfred
  echo.
)

if /I "%~1"=="silent" goto RUN
python -m alfred.boot start
if errorlevel 1 (
  echo Falha no boot. Tentando so o supervisor...
)
:RUN
pythonw -m alfred.supervise
if errorlevel 1 python -m alfred.supervise
if /I not "%~1"=="silent" (
  echo.
  echo Para iniciar com o Windows: AURA_ALFRED_SEMPRE_LIGADO.bat inicio
  pause
)
exit /b 0
