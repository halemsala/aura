@echo off
cd /d C:\aura 2>nul
if exist engine\venv\Scripts\python.exe (
  engine\venv\Scripts\python.exe scripts\aura_ops_status_write.py
) else (
  py -3.11 scripts\aura_ops_status_write.py
)
echo ops_status.json atualizado
