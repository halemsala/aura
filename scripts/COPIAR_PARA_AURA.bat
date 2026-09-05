@echo off
chcp 65001 >nul
setlocal
set AURA_ROOT=C:\aura
if not "%~1"=="" set AURA_ROOT=%~1
set SRC=%~dp0..

if not exist "%AURA_ROOT%\engine" (
  echo ERRO: %AURA_ROOT% invalido
  exit /b 1
)

echo [1] engine\agents_glm ...
xcopy /E /I /Y "%SRC%\engine\agents_glm" "%AURA_ROOT%\engine\agents_glm" >nul

echo [2] engine\agents extras ...
copy /Y "%SRC%\engine\agents\dynamic_thresholds.py" "%AURA_ROOT%\engine\agents\" >nul
copy /Y "%SRC%\engine\agents\hermes_red_team_hooks.py" "%AURA_ROOT%\engine\agents\" >nul

echo [3] bridge extras ...
if not exist "%AURA_ROOT%\bridge\jarvis\memory" mkdir "%AURA_ROOT%\bridge\jarvis\memory"
copy /Y "%SRC%\bridge\jarvis\memory\semantic_memory.py" "%AURA_ROOT%\bridge\jarvis\memory\" >nul
if not exist "%AURA_ROOT%\bridge\jarvis\skills\plugins" mkdir "%AURA_ROOT%\bridge\jarvis\skills\plugins"
copy /Y "%SRC%\bridge\jarvis\skills\plugins\windows_native.py" "%AURA_ROOT%\bridge\jarvis\skills\plugins\" >nul

echo [4] docs ...
copy /Y "%SRC%\LEIA-ME_SUPERVISAO.md" "%AURA_ROOT%\LEIA-ME_AGENTS_GLM.md" >nul

echo OK. Flags continuam OFF.
