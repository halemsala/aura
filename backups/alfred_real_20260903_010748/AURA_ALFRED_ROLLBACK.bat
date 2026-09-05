@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AURA Alfred - Rollback
set "ROOT=%~dp0"
cd /d "%ROOT%"
echo Checkpoints disponiveis:
python -m alfred.checkpoint_cli list
echo.
echo A restaurar o ULTIMO checkpoint (estado actual copiado para backups\pre-restore-*)...
python -m alfred.checkpoint_cli restore-last
if errorlevel 1 ( echo *** FALHA NO ROLLBACK *** & pause & exit /b 1 )
python -m compileall -q -f alfred || ( echo *** CODIGO RESTAURADO NAO COMPILA - verifica manualmente *** & pause & exit /b 1 )
echo ROLLBACK CONCLUIDO E VERIFICADO (compileall OK).
pause
exit /b 0
