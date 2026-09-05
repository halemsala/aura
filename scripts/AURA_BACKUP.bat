@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
if exist "engine\venv\Scripts\python.exe" (
  set PY=engine\venv\Scripts\python.exe
) else (
  set PY=python
)
if "%1"=="" (
  echo Uso:
  echo   AURA_BACKUP.bat backup
  echo   AURA_BACKUP.bat backup email
  echo   AURA_BACKUP.bat list
  echo   AURA_BACKUP.bat restore caminho\arquivo.zip
  echo   AURA_BACKUP.bat restore-dry caminho\arquivo.zip
  exit /b 0
)
if /I "%1"=="backup" (
  if /I "%2"=="email" (
    %PY% tools\aura_backup_restore.py backup --email
  ) else (
    %PY% tools\aura_backup_restore.py backup
  )
  exit /b %ERRORLEVEL%
)
if /I "%1"=="list" (
  %PY% tools\aura_backup_restore.py list
  exit /b %ERRORLEVEL%
)
if /I "%1"=="restore" (
  %PY% tools\aura_backup_restore.py restore --file "%2"
  exit /b %ERRORLEVEL%
)
if /I "%1"=="restore-dry" (
  %PY% tools\aura_backup_restore.py restore --file "%2" --dry-run
  exit /b %ERRORLEVEL%
)
if /I "%1"=="init-email" (
  %PY% tools\aura_backup_restore.py init-email
  exit /b %ERRORLEVEL%
)
echo Comando desconhecido: %1
exit /b 1
