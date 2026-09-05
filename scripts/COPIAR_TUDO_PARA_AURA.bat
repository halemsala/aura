@echo off
chcp 65001 >nul
setlocal
set AURA_ROOT=C:\aura
if not "%~1"=="" set AURA_ROOT=%~1
set SRC=%~dp0..

echo ========================================
echo  AURA COMPLETE v12.7.46 - Instalacao
echo  Destino: %AURA_ROOT%
echo  Flags permanecem DESLIGADAS
echo ========================================
echo.

if not exist "%AURA_ROOT%\engine" (
  echo ERRO: %AURA_ROOT% nao parece ser a pasta do AURA.
  exit /b 1
)

echo [1/6] Patch Hermes Supervisor...
if exist "%SRC%\patches\hermes_supervisor_agent.py" (
  if not exist "%AURA_ROOT%\engine\agents" mkdir "%AURA_ROOT%\engine\agents"
  copy /Y "%SRC%\patches\hermes_supervisor_agent.py" "%AURA_ROOT%\engine\agents\hermes_supervisor_agent.py" >nul
  echo      OK
) else (
  echo      (patch ausente)
)

echo [2/6] engine\agents + aura_hermes_router + hooks...
if not exist "%AURA_ROOT%\engine\agents" mkdir "%AURA_ROOT%\engine\agents"
copy /Y "%SRC%\engine\agents\*.py" "%AURA_ROOT%\engine\agents\" >nul
echo      OK

echo [3/6] engine\agents_glm ...
xcopy /E /I /Y "%SRC%\engine\agents_glm" "%AURA_ROOT%\engine\agents_glm" >nul
echo      OK

echo [4/6] bridge\jarvis + telegram ...
xcopy /E /I /Y "%SRC%\bridge\jarvis" "%AURA_ROOT%\bridge\jarvis" >nul
if not exist "%AURA_ROOT%\bridge\telegram" mkdir "%AURA_ROOT%\bridge\telegram"
copy /Y "%SRC%\bridge\telegram\*.py" "%AURA_ROOT%\bridge\telegram\" >nul 2>nul
echo      OK

echo [5/6] tools ...
if not exist "%AURA_ROOT%\tools" mkdir "%AURA_ROOT%\tools"
copy /Y "%SRC%\tools\*.py" "%AURA_ROOT%\tools\" >nul 2>nul
echo      OK

echo [6/6] Documentacao ...
copy /Y "%SRC%\LEIA-ME_INSTALACAO_COMPLETA.md" "%AURA_ROOT%\" >nul
copy /Y "%SRC%\CHANGELOG.txt" "%AURA_ROOT%\CHANGELOG_v12.7.46.txt" >nul 2>nul
echo      OK

echo.
echo ========================================
echo  CONCLUIDO
echo  Nenhuma flag foi ativada.
echo  Leia LEIA-ME_INSTALACAO_COMPLETA.md
echo ========================================
echo.
echo Teste:
echo   cd /d %AURA_ROOT%
echo   set PYTHONUTF8=1
echo   set PYTHONPATH=%AURA_ROOT%;%AURA_ROOT%\engine;%AURA_ROOT%\bridge
echo   engine\venv\Scripts\python.exe -m engine.agents.hermes_supervisor_agent --once
