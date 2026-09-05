@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo === AURA V23 PATCH APPLY ===
if not exist "..\engine\server.py" (
  echo ERRO: rode este BAT de dentro da pasta do sistema AURA ^(ou ajuste o caminho^).
  echo Estrutura esperada: AURA_ROOT\engine\server.py
  exit /b 1
)
echo [1/4] Backup rapido...
if not exist "..\_backup_pre_v23" mkdir "..\_backup_pre_v23"
xcopy /Y /I "bridge\server.py" "..\_backup_pre_v23\bridge\" >nul 2>&1
xcopy /Y /I "engine\*.py" "..\_backup_pre_v23\engine\" >nul 2>&1
xcopy /Y /I "desktop\MainForm.cs" "..\_backup_pre_v23\desktop\" >nul 2>&1

echo [2/4] Overlay arquivos V23...
xcopy /Y /E /I "bridge\*" "..\bridge\"
xcopy /Y /E /I "engine\*" "..\engine\"
xcopy /Y /E /I "desktop\*" "..\desktop\"
xcopy /Y /E /I "scripts\*" "..\scripts\"
xcopy /Y /E /I "agents\*" "..\agents\"

echo [3/4] httpx...
if exist "..\engine\venv\Scripts\pip.exe" (
  "..\engine\venv\Scripts\pip.exe" install httpx
) else (
  echo AVISO: venv nao encontrada - instale httpx manualmente depois.
)

echo [4/4] Ativar agentes...
if exist "..\engine\venv\Scripts\python.exe" (
  "..\engine\venv\Scripts\python.exe" "..\scripts\aura_activate_max.py"
) else (
  python "..\scripts\aura_activate_max.py"
)

echo.
echo V23 aplicado. Reinicie Bridge+Engine+Desktop.
