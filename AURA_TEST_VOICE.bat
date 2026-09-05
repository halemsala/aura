@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA TEST VOICE
echo ================================================================
echo  TESTE VOZ — porta 8099 (processo UP != TTS pronto)
echo ================================================================
echo.

powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort 8099 -State Listen -EA SilentlyContinue; if($c){'LISTEN 8099 PID='+$c[0].OwningProcess}else{'OFF 8099'}}catch{'OFF 8099'}"

echo.
echo --- /api/voice/health ---
powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:8099/api/voice/health' -UseBasicParsing -TimeoutSec 5; $r.Content}catch{Write-Host ('FALHA: '+$_.Exception.Message)}"

echo.
echo --- /api/health ---
powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:8099/api/health' -UseBasicParsing -TimeoutSec 5; $r.Content}catch{Write-Host ('FALHA: '+$_.Exception.Message)}"

echo.
echo --- voice.log tail ---
if exist logs_supervisor\voice.log (
  powershell -NoProfile -Command "Get-Content logs_supervisor\voice.log -Tail 40"
) else (
  echo [sem logs_supervisor\voice.log]
)

echo.
echo Interpretação:
echo   process_up=true + engineReady=false → servidor no ar, TTS/STT ainda lazy ou a falhar load
echo   error preenchido → ler mensagem e AURA_INSTALAR_VOZ.bat
echo   OFF 8099 → AURA_SUBIR_VOZ.bat
echo.
echo Comandos:
echo   AURA_INSTALAR_VOZ.bat
echo   AURA_SUBIR_VOZ.bat
echo   No Hermes chat:  voz status
echo.
pause
endlocal
