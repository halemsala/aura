@echo off
setlocal
rem ============================================================
rem  Ativa o Harness Supervisor Pro (AURA_HARNESS_UNICO.py)
rem  Só prepara o ambiente e abre o programa. Subir os servicos
rem  (Engine/Bridge/Voice/Ollama) continua exigindo que voce
rem  digite "iniciar tudo" e depois confirme dentro do Harness -
rem  isso e proposital, e a trava de seguranca do projeto.
rem ============================================================

cd /d "%~dp0"

echo Verificando Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] Sua versao de Python e mais antiga que 3.10.
    echo O script usa recursos de Python 3.10+. Atualize e tente de novo.
    echo.
    pause
    exit /b 1
)

echo Verificando dependencia opcional "rich" (interface colorida)...
python -c "import rich" >nul 2>&1
if errorlevel 1 (
    echo Instalando "rich"...
    python -m pip install --quiet rich
) else (
    echo "rich" ja instalado.
)

echo.
echo ============================================================
echo  Abrindo o Harness. Assim que o menu aparecer, para subir
echo  Engine, Bridge, Voice e checar o Ollama de uma vez, digite:
echo.
echo      iniciar tudo
echo.
echo  E confirme quando ele pedir (CONFIRMAR INICIAR TUDO).
echo ============================================================
echo.

python AURA_HARNESS_UNICO.py

echo.
echo Harness encerrado.
pause
