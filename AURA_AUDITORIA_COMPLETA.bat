@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA - Auditoria completa
set "ROOT=%CD%"
set "LOGDIR=%ROOT%\logs_supervisor"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "OUT=%LOGDIR%\AUDITORIA_COMPLETA_LATEST.txt"
echo AURA AUDITORIA %DATE% %TIME% ROOT=%ROOT%> "%OUT%"
echo paper_trade=true execution_allowed=false>> "%OUT%"
echo.>> "%OUT%"

echo === Ficheiros criticos ===>> "%OUT%"
for %%F in (
  engine\server.py
  bridge\server.py
  bridge\jarvis_voice_server.py
  desktop\ui\matriz_v22\index.html
  desktop\config\desktop.json
  desktop\capture\aura-capture.js
  desktop\publish\Aura.QuantX.Desktop.exe
  hermes_v10\scripts\hermes_v10_chat_api.py
  scripts\aura_serve_matriz.py
  scripts\AURA_SAFE_FREE_PORTS.ps1
  AURA_START_ALL.bat
  AURA_TUDO_EM_UM.bat
  AURA_ABRIR_DESKTOP.bat
  ABRIR_MATRIZ.bat
) do (
  if exist "%ROOT%\%%F" (echo OK   %%F>> "%OUT%") else (echo MISS %%F>> "%OUT%")
)

echo.>> "%OUT%"
echo === Portas ===>> "%OUT%"
powershell -NoProfile -Command "$ports=8080,8765,8777,8778,8766,8099,11434; foreach($p in $ports){ $c=Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue; if($c){'LISTEN '+$p}else{'OFF    '+$p} }" >> "%OUT%"

echo.>> "%OUT%"
echo === Health HTTP ===>> "%OUT%"
powershell -NoProfile -Command "foreach($u in 'http://127.0.0.1:8080/health','http://127.0.0.1:8765/api/health','http://127.0.0.1:8766/health','http://127.0.0.1:8777/chat'){ try{ $r=Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2; '{0} {1}' -f $r.StatusCode,$u }catch{ 'DOWN {0}' -f $u } }" >> "%OUT%"

echo.>> "%OUT%"
echo === ui/state (nao inventar fixture) ===>> "%OUT%"
powershell -NoProfile -Command "try{ $s=Invoke-RestMethod 'http://127.0.0.1:8765/api/ui/state' -TimeoutSec 3; $v=$s.snapshot.view; if(-not $v){$v=$s.view}; 'home='+$v.home+' away='+$v.away+' min='+$v.minute }catch{ 'ui/state indisponivel' }" >> "%OUT%"

echo Relatorio: %OUT%
type "%OUT%"
endlocal
