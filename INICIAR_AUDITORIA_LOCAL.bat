@echo off
title HARNESS AGENT + LM STUDIO
color 0A

echo =======================================================
echo          PREPARANDO AMBIENTE LOCAL DE AUDITORIA        
echo =======================================================
echo.

:: 1. Cria uma pasta limpa para o RAG do LM Studio ler sem lixo
if not exist "C:\aura\auditoria_harness" (
    echo [Harness] Criando pasta de indexacao local...
    mkdir "C:\aura\auditoria_harness"
)

:: 2. Copia o Manual de Governança para contextualizar o modelo
echo [Harness] Sincronizando regras do sistema...
copy /Y "C:\aura\MANUAL.md" "C:\aura\auditoria_harness\MANUAL_REGRAS.md" > nul

:: 3. Converte os logs dinâmicos mais recentes para TXT (Formato nativo do LM Studio RAG)
echo [Harness] Convertendo logs recentes da Bridge...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'C:\aura\bridge\live_feed.jsonl') { Get-Content -Tail 200 'C:\aura\bridge\live_feed.jsonl' | Out-File 'C:\aura\auditoria_harness\logs_recentes.txt' -Encoding utf8 } else { Write-Host 'Aguardando telemetria ativa para gerar logs...' -ForegroundColor Yellow }"

echo.
echo =======================================================
echo      LOGS PRONTOS! ABRINDO O INTERFACE DO LM STUDIO     
echo =======================================================
echo.
echo DICA: No LM Studio, use o menu 'Local Documents' e aponte
echo para a pasta: C:\aura\auditoria_harness
echo.

:: 4. Executa o LM Studio instalado via WinGet
start "" "%USERPROFILE%\AppData\Local\Programs\lm-studio\LM Studio.exe"

timeout /t 5
exit
