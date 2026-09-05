@echo off
cd /d C:\aura 2>nul
if exist engine\venv\Scripts\python.exe (
  engine\venv\Scripts\python.exe scripts\aura_vram_report.py
) else (
  py -3.11 scripts\aura_vram_report.py
)
pause
