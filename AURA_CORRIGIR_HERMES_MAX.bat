@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PS1=%ROOT%\AURA_CORRIGIR_HERMES_MAX.ps1"

echo ================================================================
echo AURA MAX - CORRIGIR HERMES / SEM POPUPS DE NAVEGADOR
echo ================================================================
echo ROOT=%ROOT%
echo.

if not exist "%PS1%" (
  echo [ERRO] Falta AURA_CORRIGIR_HERMES_MAX.ps1 na raiz do pacote.
  echo Copie os dois ficheiros para a mesma pasta e tente novamente.
  pause
  exit /b 2
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Windows PowerShell nao encontrado.
  pause
  exit /b 2
)

set "EXTRA="
set "AUTO_CLOSE=0"
if /I "%~1"=="/KEEP_HERMES" set "EXTRA=-NoRestartHermes"
if /I "%~1"=="-NoRestartHermes" set "EXTRA=-NoRestartHermes"
if /I "%~1"=="/AUTO_CLOSE" set "AUTO_CLOSE=1"

set "AURA_NO_BROWSER=1"
set "AURA_AUTO_OPEN_UI=0"
set "AURA_OLLAMA_MODEL=qwen3:8b"
set "OLLAMA_MODEL=qwen3:8b"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Root "%ROOT%" %EXTRA%
set "RC=%ERRORLEVEL%"

echo.
echo ================================================================
if "%RC%"=="0" (
  echo [OK] AURA MAX online: Bridge + Engine + Hermes.
) else if "%RC%"=="1" (
  echo [AVISO] Arranque parcial. Consulte logs_supervisor\aura_max_fix.log.
) else (
  echo [ERRO] Falha de correcao/arranque. Consulte logs_supervisor\aura_max_fix.log.
)
echo [INFO] Nao foi aberto nenhum navegador.
echo [INFO] Modelo configurado: qwen3:8b; VRAM alvo: 6 GB.
echo [INFO] Backup criado em backups\aura_max_* quando houve alteracoes.
echo ================================================================
if not "%RC%"=="0" set "AUTO_CLOSE=0"
if "%AUTO_CLOSE%"=="0" (
  echo.
  echo [INFO] Modo diagnostico: a janela permanece aberta para poderes ver o resultado.
  echo [INFO] Log: %ROOT%\logs_supervisor\aura_max_fix.log
  echo [INFO] Para fechar, pressiona uma tecla.
  pause
)
exit /b %RC%
