@echo off
title HARNESS AGENT - AUDITORIA
color 0A

echo =======================================================
echo          INICIANDO VARREDURA DOS LOGS DO AURA          
echo =======================================================
echo.

:: Tenta rodar direto a linha do PowerShell de forma simples
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'engine\runtime_events.jsonl') { Get-Content -Tail 40 'engine\runtime_events.jsonl' | ollama.exe run llama3.1:8b-instruct-q8_0 'Analise esses logs do AURA QUANT-X.' } else { Write-Host 'Arquivo de log da Engine nao encontrado. Certifique-se de rodar na raiz do AURA e que o sistema ja foi iniciado hoje.' -ForegroundColor Yellow }"

echo.
echo =======================================================
echo              SESSAO DE AUDITORIA FINALIZADA            
echo =======================================================
echo Se a janela nao pausar, verifique o arquivo log_harness.txt
pause
