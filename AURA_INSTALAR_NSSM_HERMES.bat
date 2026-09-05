@echo off
REM AURA QUANT-X — instalar Hermes como servico Windows (NSSM)
REM Requer: nssm.exe no PATH ou na pasta atual; terminal Admin
setlocal
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

where nssm >nul 2>&1
if errorlevel 1 (
  echo [ERRO] nssm.exe nao encontrado no PATH.
  echo Baixe em https://nssm.cc/download e coloque nssm.exe nesta pasta ou no PATH.
  pause
  exit /b 1
)

set PY=
if exist "%ROOT%\engine\venv\Scripts\python.exe" set PY=%ROOT%\engine\venv\Scripts\python.exe
if not defined PY if exist "%ROOT%\venv\Scripts\python.exe" set PY=%ROOT%\venv\Scripts\python.exe
if not defined PY (
  where python >nul 2>&1 && for /f "delims=" %%i in ('where python') do set PY=%%i
)
if not defined PY (
  echo [ERRO] Python nao encontrado. Rode a instalacao completa primeiro.
  pause
  exit /b 1
)

set SCRIPT=%ROOT%\scripts\hermes_v10_chat_api.py
if not exist "%SCRIPT%" set SCRIPT=%ROOT%\hermes_v10\scripts\hermes_v10_chat_api.py
if not exist "%SCRIPT%" (
  echo [ERRO] hermes_v10_chat_api.py nao encontrado.
  pause
  exit /b 1
)

echo Instalando servico AuraHermes...
nssm stop AuraHermes >nul 2>&1
nssm remove AuraHermes confirm >nul 2>&1
nssm install AuraHermes "%PY%" "-u" "%SCRIPT%"
nssm set AuraHermes AppDirectory "%ROOT%"
nssm set AuraHermes AppExit Default Restart
nssm set AuraHermes AppRestartDelay 10000
nssm set AuraHermes Start SERVICE_AUTO_START
nssm set AuraHermes AppStdout "%ROOT%\logs_supervisor\hermes_service_stdout.log"
nssm set AuraHermes AppStderr "%ROOT%\logs_supervisor\hermes_service_stderr.log"
nssm start AuraHermes
echo.
echo OK. Servico AuraHermes instalado e iniciado.
echo  - Sobe no boot do Windows
echo  - Auto-restart se crashar
echo  - Logs: logs_supervisor\hermes_service_*.log
echo.
echo Comandos uteis:
echo   nssm status AuraHermes
echo   nssm stop AuraHermes
echo   nssm restart AuraHermes
pause
