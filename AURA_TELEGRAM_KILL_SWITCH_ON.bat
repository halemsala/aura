@echo off
cd /d C:\aura 2>nul
mkdir data\telegram_intel 2>nul
echo 1> data\telegram_intel\kill_switch.on
setx AURA_TELEGRAM_KILL_SWITCH 1 >nul 2>&1
echo KILL_SWITCH ON (ficheiro + env)
if exist scripts\aura_ops_status_write.py (
  if exist engine\venv\Scripts\python.exe engine\venv\Scripts\python.exe scripts\aura_ops_status_write.py
)
