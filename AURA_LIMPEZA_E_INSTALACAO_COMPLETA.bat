@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo AURA limpeza minima - nao mata Ollama
echo paper_trade=true execution_allowed=false
echo A delegar no instalador autonomo...
if exist "%~dp0AURA_INSTALAR_TESTAR_AUTONOMO.bat" (
  call "%~dp0AURA_INSTALAR_TESTAR_AUTONOMO.bat"
) else (
  echo Falta AURA_INSTALAR_TESTAR_AUTONOMO.bat
  pause
)
