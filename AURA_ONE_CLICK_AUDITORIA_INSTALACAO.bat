@echo off
cd /d "%~dp0"
call "%~dp0AURA_INSTALACAO_LIMPA_SILENCIOSA.bat"
exit /b %ERRORLEVEL%

if /I "%~1"=="NOPAUSE" goto :AURA_EOF
echo.
echo [AURA] Resumo acima. Esta janela NAO fecha sozinha.
echo        Pressiona uma tecla para sair.
pause
:AURA_EOF
