@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Ativar Operador Humano
echo ============================================================
echo  AURA - Operador Humano OPT-IN (WhatsApp / Telegram)
echo ============================================================
echo.

setx AURA_SKILLS_ENABLED 1 >nul
setx AURA_WHATSAPP_OPERATOR_ENABLED 1 >nul
setx AURA_TELEGRAM_OPERATOR_ENABLED 1 >nul
setx OLLAMA_MAX_LOADED_MODELS 2 >nul

set AURA_SKILLS_ENABLED=1
set AURA_WHATSAPP_OPERATOR_ENABLED=1
set AURA_TELEGRAM_OPERATOR_ENABLED=1

echo [OK] AURA_SKILLS_ENABLED=1
echo [OK] AURA_WHATSAPP_OPERATOR_ENABLED=1
echo [OK] AURA_TELEGRAM_OPERATOR_ENABLED=1
echo.
echo Proximos passos:
echo   1) pip install pyautogui pygetwindow pyperclip pywin32
echo   2) python -m bridge.jarvis.tools.macro_recorder
echo   3) Reinicie AURA_SUBIR_STACK_COMPLETO.bat
echo   4) Teste no chat: Manda pro NOME: texto de teste
echo.
echo AVISO: input local e indistinguivel de humano. Use sob supervisao.
echo ============================================================
pause
endlocal
