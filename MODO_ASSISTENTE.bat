@echo off
title AURA - Modo Assistente
echo.
echo ========================================
echo   ATIVANDO MODO ASSISTENTE
echo   (AURA de trading sera desligado)
echo ========================================
echo.

cd /d C:\aura

python -c "from bridge.jarvis.governor.resource_governor import GOVERNOR; print(GOVERNOR.switch_to_assistant_mode())"

echo.
echo Pressione qualquer tecla para fechar...
pause >nul
