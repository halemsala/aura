@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if not exist "%CD%\engine\server.py" if exist "C:\aura\engine\server.py" cd /d C:\aura
if not exist "%CD%\engine\server.py" if exist "C:\AURA_V25\engine\server.py" cd /d C:\AURA_V25
set "ROOT=%CD%"
set "PY=python"
if exist "%ROOT%\engine\venv\Scripts\python.exe" set "PY=%ROOT%\engine\venv\Scripts\python.exe"
echo === AURA REPARAR XTTS / TRANSFORMERS / TORCHCODEC ===
echo PY=%PY%
echo.
echo Este reparo:
echo  - remove torchcodec
echo  - fixa transformers 4.57.x e huggingface-hub ^< 1
echo  - instala coqui-tts 0.27.5
echo  - NAO precisa de FFmpeg full-shared
echo.
"%PY%" "%ROOT%\scripts\instalar_deps_voz.py"
if errorlevel 1 (
  echo FALHA nas deps. Veja o output acima.
  pause
  exit /b 1
)
echo.
echo Compat check:
"%PY%" "%ROOT%\scripts\aura_xtts_compat.py"
echo.
echo Teste import TTS:
"%PY%" -c "import sys; sys.path.insert(0, r'%ROOT%\scripts'); from aura_xtts_compat import apply_all; print(apply_all()); import transformers; print('transformers', transformers.__version__); from TTS.api import TTS; print('TTS_IMPORT=OK')"
if errorlevel 1 (
  echo Import TTS ainda falhou.
  pause
  exit /b 2
)
echo.
echo Opcional: teste de sintese (1.a vez baixa pesos XTTS e demora):
echo   "%PY%" scripts\teste_xtts_referencia.py
echo.
pause
endlocal
exit /b 0
