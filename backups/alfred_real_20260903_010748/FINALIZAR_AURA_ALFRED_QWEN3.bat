@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title AURA Alfred - Arranque Limpo
if not exist "alfred\api.py" (
  echo [ERRO] Falta alfred\api.py em %CD%.
  echo Esta pasta nao e a raiz correcta do Aura.
  pause
  exit /b 2
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao esta no PATH.
  pause
  exit /b 3
)
if not exist "data\alfred" mkdir "data\alfred" >nul 2>&1

echo ================================================================
echo AURA / ALFRED / QWEN3 - ARRANQUE LIMPO
echo ================================================================
echo ROOT=%CD%
python --version

echo [1/3] A verificar qwen3:8b no Ollama...
curl.exe -s --max-time 5 http://127.0.0.1:11434/api/tags | findstr /C:"qwen3:8b" >nul
if errorlevel 1 (
  echo [ERRO] qwen3:8b nao foi encontrado no Ollama.
  pause
  exit /b 4
 )
echo qwen3:8b OK

curl.exe -s --max-time 2 http://127.0.0.1:8791/health >nul 2>&1
if not errorlevel 1 goto online

echo [2/3] A iniciar Alfred em 127.0.0.1:8791...
start "AURA Alfred" /min cmd /c "python -m alfred.api >> data\alfred\stdout.log 2>> data\alfred\stderr.log"
for /L %%N in (1,1,20 ) do (
  curl.exe -s --max-time 2 http://127.0.0.1:8791/health >nul 2>&1
  if not errorlevel 1 goto online
  timeout /t 1 /nobreak >nul
 )
echo [ERRO] Alfred nao respondeu na porta 8791.
echo [INFO] Consulta data\alfred\stderr.log
pause
exit /b 5

:online
echo [3/3] ALFRED ONLINE COM qwen3:8b.
echo API: http://127.0.0.1:8791/health
echo Log: data\alfred\stderr.log
echo.
echo Este BAT nao contem codigo Python nem abre navegador.
echo Pressiona uma tecla para fechar.
pause >nul
exit /b 0
