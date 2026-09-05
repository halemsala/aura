@echo off
title AURA - Modo Trading
echo.
echo ========================================
echo   ATIVANDO MODO TRADING
echo   (Assistente Pessoal sera desligado)
echo ========================================
echo.

cd /d C:\aura

python -c "from bridge.jarvis.governor.resource_governor import GOVERNOR; print(GOVERNOR.switch_to_trading_mode())"

echo.
echo Pressione qualquer tecla para fechar...
pause >nul
