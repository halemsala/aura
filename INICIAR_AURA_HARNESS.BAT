@echo off
:: ==============================================================================
:: ORQUESTRAÇÃO DE STARTUP ROOT - AURA QUANT-X V8.1
:: AMBIENTE: WINDOWS 11 ADMIN | GPU NVIDIA RTX 4050 (6GB VRAM)
:: ==============================================================================
TITLE SYSTEM CORE - AURA HARNESS V8.1

echo [*] Validando Token de Administrador...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ALERTA] Direitos insuficientes. Injetando prompt de elevacao UAC...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [*] Aplicando Tabela UTF-8 Global...
chcp 65001 >nul

echo [*] Mapeando topologia em C:\aura...
if not exist "C:\aura\scripts\AURA_HARNESS_CORE.py" (
    echo [FATAL] Arquivo Master Ausente (C:\aura\scripts\AURA_HARNESS_CORE.py).
    pause
    exit /b
)

echo [*] Pingando API do Motor de Inferência (Ollama - TCP 11434)...
powershell -Command "$t = New-Object System.Net.Sockets.TCPClient; try { $t.Connect('127.0.0.1', 11434); echo '[OK] Porta Livre.' } catch { exit 1 }" >nul 2>&1
if %errorLevel% neq 0 (
    echo [SISTEMA] Motor offline. Lancando instancia invisivel...
    start "" /b "ollama" serve
    timeout /t 5 >nul
)

echo [*] Executando Purga de Hardware - Desalocando VRAM da RTX 4050...
powershell -Command "Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -Body '{\"model\":\"llama3.2:1b\",\"keep_alive\":0}' -Headers @{'Content-Type'='application/json'}" >nul 2>&1
powershell -Command "Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -Body '{\"model\":\"llama3.1:8b-instruct-q4_K_M\",\"keep_alive\":0}' -Headers @{'Content-Type'='application/json'}" >nul 2>&1

echo ==============================================================================
echo                      TRANSFERINDO CONTROLE PARA A.I
echo ==============================================================================
cd /d "C:\aura\scripts"
python AURA_HARNESS_CORE.py

echo ==============================================================================
echo [SISTEMA] Processo encerrado. Realizando dump de segurança da memoria RAM/VRAM.
pause