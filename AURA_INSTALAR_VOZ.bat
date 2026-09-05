@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if not exist "%CD%\engine\server.py" if exist "C:\aura\engine\server.py" cd /d C:\aura
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "PIPER_DIR=%ROOT%\bridge\jarvis\voices\piper"
set "HERCULES_ONNX=%PIPER_DIR%\pt_BR-faber-medium.onnx"
echo === AURA VOZ HERCULES (Piper Faber pt-BR) ===
echo Antonio Neural fica fora do padrao.
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
if not exist "%HERCULES_ONNX%" (
  echo Baixando modelo Hercules/Faber...
  curl.exe -L --fail --retry 3 -o "%HERCULES_ONNX%" "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
)
echo {"voice_name":"hercules","preferred_engine":"piper","profile":"hercules","rate":"-12%%","pitch":"-8Hz"}> "%ROOT%\logs_supervisor\aura_voice_pref.json"
(
echo KANTEIRO_NEURAL_VOICE=hercules
echo AURA_TTS_ENGINE=piper
echo AURA_PIPER_MODEL=%HERCULES_ONNX%
echo AURA_PIPER_CONFIG=%HERCULES_ONNX%.json
) > "%ROOT%\logs_supervisor\aura_voice.env"
set KANTEIRO_NEURAL_VOICE=hercules
set AURA_TTS_ENGINE=piper
set "AURA_PIPER_MODEL=%HERCULES_ONNX%"
set "AURA_PIPER_CONFIG=%HERCULES_ONNX%.json"
set AURA_ROOT=%ROOT%
set PAPER_TRADE=true
set EXECUTION_ALLOWED=false
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8099 -State Listen -EA SilentlyContinue; if($c){exit 0}else{exit 1}}catch{exit 1}"
if errorlevel 1 (
  echo Subindo Voice :8099 com HERCULES
  start "AURA-Voice-8099" /MIN cmd /c "cd /d %ROOT% && set AURA_ROOT=%ROOT%&& set KANTEIRO_NEURAL_VOICE=hercules&& set AURA_TTS_ENGINE=piper&& set AURA_PIPER_MODEL=%HERCULES_ONNX%&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "%VPY%" -u bridge\jarvis_voice_server.py --host 127.0.0.1 --port 8099 --lazy >> "%ROOT%\logs_supervisor\voice.log" 2>&1"
  timeout /t 4 /nobreak >nul
) else (
  echo Voice ja LISTEN :8099 — reinicie o processo Voice para aplicar HERCULES
)
echo.
echo Voz default: HERCULES  (piper pt_BR-faber-medium)
echo Health: http://127.0.0.1:8099/api/voice/health
endlocal
exit /b 0
