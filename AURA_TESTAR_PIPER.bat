@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
set "PIPER_DIR=%ROOT%\bridge\jarvis\voices\piper"
set "OUT=%ROOT%\logs_supervisor\piper_teste.wav"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor"
echo === Teste Piper pt-BR ===
if exist "%PIPER_DIR%\piper.exe" (
  echo Usando piper.exe + Faber...
  echo A pressao subiu no segundo tempo, linha de escanteios ainda tem valor.|"%PIPER_DIR%\piper.exe" --model "%PIPER_DIR%\pt_BR-faber-medium.onnx" --output_file "%OUT%"
) else (
  echo piper.exe ausente — tentando python -m piper...
  "%VPY%" -m piper --model "%PIPER_DIR%\pt_BR-faber-medium.onnx" --output_file "%OUT%" "A pressao subiu no segundo tempo, linha de escanteios ainda tem valor."
)
if exist "%OUT%" (
  echo OK: %OUT%
  start "" "%OUT%"
) else (
  echo FALHA na sintese Piper
)
pause
endlocal
