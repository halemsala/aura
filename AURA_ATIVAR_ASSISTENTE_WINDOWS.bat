@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if not exist "%CD%\engine\server.py" if exist "C:\aura\engine\server.py" cd /d C:\aura
set "ROOT=%CD%"
set "VPY=%ROOT%\engine\venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
set "AURA_ROOT=%ROOT%"
set "PAPER_TRADE=true"
set "EXECUTION_ALLOWED=false"
set "GLM_ADVISORY_ONLY=true"
set "PYTHONUTF8=1"
set "AURA_SKILLS_ENABLED=1"
set "AURA_SAFE_EXECUTOR=1"
title AURA ASSISTENTE PESSOAL + CONTROLO WINDOWS
color 0B

echo ================================================================
echo  AURA ASSISTENTE PESSOAL — CONTROLO WINDOWS (opt-in)
echo  Invariantes: paper_trade=true  execution_allowed=false
echo  Anti-Bet Shield activo (nao interage com casas de apostas)
echo  Gates: whitelist + AUTORIZO + FaceID + panico 60s
echo ================================================================
echo ROOT=%ROOT%
echo.

REM --- 1) Dependencias de controlo Windows ---
echo [1/6] Dependencias (pyautogui, pygetwindow, opencv, edge-tts)...
"%VPY%" -m pip install --quiet pyautogui pygetwindow psutil opencv-contrib-python edge-tts pywin32 2>nul
if errorlevel 1 (
  echo [AVISO] pip falhou parcialmente — continue se ja instalado.
)

REM --- 2) Ativar SKILLS_ENABLED no skill_manager ---
echo [2/6] Ativar SKILLS_ENABLED no skill_manager.py...
if exist "%ROOT%\bridge\jarvis\skills\skill_manager.py" (
  "%VPY%" -c "from pathlib import Path; p=Path(r'%ROOT%')/'bridge'/'jarvis'/'skills'/'skill_manager.py'; t=p.read_text(encoding='utf-8'); t2=t.replace('SKILLS_ENABLED = False','SKILLS_ENABLED = True'); p.write_text(t2,encoding='utf-8'); print('SKILLS_ENABLED =', 'True' if 'SKILLS_ENABLED = True' in t2 else 'False')"
) else (
  echo [AVISO] skill_manager.py nao encontrado.
)

REM --- 3) Flag de ambiente persistente (sessao) ---
echo [3/6] Flags de sessao...
setx AURA_SKILLS_ENABLED 1 >nul 2>&1
setx AURA_SAFE_EXECUTOR 1 >nul 2>&1
setx PAPER_TRADE true >nul 2>&1
setx EXECUTION_ALLOWED false >nul 2>&1

REM --- 4) Voz (opcional) ---
echo [4/6] Voz...
if exist "%ROOT%\AURA_INSTALAR_VOZ.bat" call "%ROOT%\AURA_INSTALAR_VOZ.bat"

REM --- 5) Assistente + Hermes (sem matar Ollama/Hermes) ---
echo [5/6] Assistente + Hermes...
if exist "%ROOT%\AURA_ASSISTENTE_COMPLETO.bat" (
  call "%ROOT%\AURA_ASSISTENTE_COMPLETO.bat"
) else (
  echo [AVISO] AURA_ASSISTENTE_COMPLETO.bat ausente — a tentar Hermes directo.
  if exist "%ROOT%\AURA_HERMES_V10_ULTRA.bat" call "%ROOT%\AURA_HERMES_V10_ULTRA.bat" bg
)

REM --- 6) Smoke das skills Windows ---
echo [6/6] Smoke skills Windows...
"%VPY%" -c "import sys; from pathlib import Path; r=Path(r'%ROOT%'); sys.path.insert(0,str(r)); sys.path.insert(0,str(r/'bridge')); from jarvis.skills.skill_manager import SkillManager, SKILLS_ENABLED; m=SkillManager(str(r/'bridge'/'jarvis'/'skills'/'plugins')); print('SKILLS_ENABLED=', SKILLS_ENABLED); print('skills=', list(m.installed_skills.keys()) or '(nenhuma — reinicie apos patch)'); from jarvis.security.safe_executor import SAFE_EXECUTOR; print('SafeExecutor=OK', bool(SAFE_EXECUTOR))" 2>nul
if errorlevel 1 (
  echo [AVISO] Smoke parcial (imports). Confirme apos reinicio do bridge/voz.
)

echo.
echo ================================================================
echo  ASSISTENTE ATIVO (modo opt-in)
echo  - Skills Windows: open_app, focus_window, minimize_all, tile_windows
echo  - SafeExecutor: mouse/teclado com Anti-Bet Shield
echo  - Para accoes perigosas diga: AUTORIZO
echo  - Panico: diga \"para de mexer\" (bloqueio 60s)
echo  - FaceID: python tools\register_face.py --name Admin
echo  - Matriz  http://127.0.0.1:8766/index.html
echo  - Hermes  http://127.0.0.1:8777/chat
echo  - Voz     http://127.0.0.1:8099/api/voice/health
echo  paper_trade=true  execution_allowed=false  (INTOCADO)
echo ================================================================
endlocal
exit /b 0
