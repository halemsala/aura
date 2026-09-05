@echo off
setlocal
cd /d "%~dp0.."
set "VENV_PY=%CD%\engine\venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERRO] venv nao encontrado. Execute AURA_TUDO_EM_UM.bat primeiro.
  exit /b 1
)
echo [INFO] Instalando dependencias V23 infra...
"%VENV_PY%" -m pip install pynvml psutil apscheduler python-telegram-bot httpx beautifulsoup4 lxml
echo [OK] Dependencias instaladas.
