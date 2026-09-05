@echo off
chcp 65001 >NUL
cd /d C:\aura
echo.
echo === AURA REPARAR OLLAMA (nao cole HTTPConnection no PowerShell) ===
echo.

where python >NUL 2>&1
if errorlevel 1 (
  echo [ERRO] python nao esta no PATH.
  echo Instale Python 3.10/3.11 e reabra o terminal como Administrador.
  pause
  exit /b 1
)

if not exist "C:\aura\AURA_REPARAR_OLLAMA.py" (
  echo [ERRO] Falta C:\aura\AURA_REPARAR_OLLAMA.py
  echo Copie AURA_REPARAR_OLLAMA.py para C:\aura e rode este BAT de novo.
  pause
  exit /b 1
)

echo [1] Teste TCP 127.0.0.1 porta 11434
python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1',11434)); s.close(); print('TCP OK')"
if errorlevel 1 (
  echo [ERRO] Ollama nao esta escutando na porta 11434.
  echo Abra o Ollama na bandeja ou rode: ollama serve
  pause
  exit /b 2
)

echo.
echo [2] Ciclo VRAM CONTROL
python "C:\aura\AURA_REPARAR_OLLAMA.py"
echo.
pause
