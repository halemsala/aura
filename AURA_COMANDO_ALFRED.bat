@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AURA Alfred - Comandos
if not exist "data\alfred" mkdir "data\alfred" >nul 2>&1

echo Alfred online em http://127.0.0.1:8791
 echo Escreve um comando. Para sair, escreve SAIR.
echo Exemplos: Alfred, estado ^| Alfred, lista ficheiros ^| Alfred, abre uma pesquisa sobre Aura
echo.
:loop
set "CMD="
set /p "CMD=Alfred^> "
if /I "%CMD%"=="SAIR" exit /b 0
if not defined CMD goto loop
set "ALFRED_CMD=%CMD%"
powershell.exe -NoLogo -NoProfile -Command "$b=@{message=$env:ALFRED_CMD;session_id='cmd';authorized=$false}|ConvertTo-Json -Depth 5; try { Invoke-RestMethod 'http://127.0.0.1:8791/ask' -Method Post -ContentType 'application/json' -Body $b | ConvertTo-Json -Depth 12 } catch { Write-Host ('ERRO: '+$_.Exception.Message) -ForegroundColor Red }"
echo.
goto loop
