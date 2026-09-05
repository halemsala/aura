@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "FINAL_LOG=%ROOT%\logs_supervisor\finalizacao_aura.log"
if not exist "%ROOT%\logs_supervisor" mkdir "%ROOT%\logs_supervisor" >nul 2>&1

echo ================================================================
echo FINALIZAR AURA + HERMES + ALFRED / QWEN3
echo ================================================================
echo ROOT=%ROOT%
echo.

if not exist "%ROOT%\AURA_CORRIGIR_HERMES_MAX.bat" (
  echo [ERRO] AURA_CORRIGIR_HERMES_MAX.bat nao encontrado.
  echo Copia este BAT para a raiz C:\aura, ao lado dos outros ficheiros.
  pause
  exit /b 2
)
if not exist "%ROOT%\AURA_ALFRED_MAX.bat" (
  echo [ERRO] AURA_ALFRED_MAX.bat nao encontrado.
  pause
  exit /b 2
)

echo [%date% %time%] INICIO > "%FINAL_LOG%"
echo [1/4] A corrigir e iniciar Hermes/core...
call "%ROOT%\AURA_CORRIGIR_HERMES_MAX.bat" /AUTO_CLOSE
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERRO] Hermes/core falhou com codigo %RC%.
  echo [INFO] Log: %ROOT%\logs_supervisor\aura_max_fix.log
  echo [INFO] A janela vai permanecer aberta.
  pause
  exit /b %RC%
)

echo [2/4] A iniciar ALFRED ligado ao qwen3:8b...
call "%ROOT%\AURA_ALFRED_MAX.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERRO] ALFRED/qwen3 falhou com codigo %RC%.
  echo [INFO] Verifica alfred_qwen3_test.json e alfred_install.log.
  pause
  exit /b %RC%
)

echo [3/4] A validar modelo e portas...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $checks=@(@{n='ollama';u='http://127.0.0.1:11434/api/tags'},@{n='bridge';u='http://127.0.0.1:8080/health'},@{n='engine';u='http://127.0.0.1:8765/api/health'},@{n='hermes';u='http://127.0.0.1:8777/'},@{n='alfred';u='http://127.0.0.1:8791/health'}); $out=@(); foreach($c in $checks){try{$r=Invoke-WebRequest -UseBasicParsing -Uri $c.u -TimeoutSec 5; $out += [pscustomobject]@{service=$c.n;ok=($r.StatusCode -ge 200 -and $r.StatusCode -lt 400);status=$r.StatusCode}}catch{$out += [pscustomobject]@{service=$c.n;ok=$false;status=0;error=$_.Exception.Message}}}; $tags=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; $model=(@($tags.models | %% {$_.name}) -contains 'qwen3:8b'); $out | ConvertTo-Json -Depth 4 | Tee-Object -FilePath '%FINAL_LOG%' -Append; if(-not $model){throw 'qwen3:8b nao detectado'}; if(@($out | Where-Object {-not $_.ok}).Count -gt 0){throw 'um ou mais servicos OFF'}"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERRO] Validacao final falhou.
  echo [INFO] Log: %FINAL_LOG%
  pause
  exit /b %RC%
)

echo [4/4] SISTEMA ONLINE: qwen3 + Hermes + ALFRED.
echo [INFO] Nao foi aberto navegador.
echo [INFO] Log final: %FINAL_LOG%
exit /b 0
