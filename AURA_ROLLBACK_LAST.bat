@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA ROLLBACK LAST
echo Restaura o ultimo patch Alfred ou, se nao houver, o ultimo checkpoint.
echo O estado actual e copiado para data\alfred\backups\ antes do restauro.
python -m alfred.boot rollback
if errorlevel 1 (
  echo [ERRO] rollback falhou.
  pause
  exit /b 1
)
echo Rollback concluido.
pause
exit /b 0
