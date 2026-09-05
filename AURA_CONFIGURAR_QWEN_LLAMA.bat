@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AURA Configurar Qwen Llama
echo ============================================================
echo  AURA - Arquitetura de modelos (RTX 4050 6GB)
echo ============================================================
echo.
echo  LOCAL (AURA 24h):
echo    qwen2.5:3b-instruct  = cerebro principal
echo    llama3.2:3b          = especialista contexto longo
echo.
echo  NUVEM (fora do AURA):
echo    GLM = arquiteto externo (nunca no Ollama local)
echo ============================================================
echo.

setx AURA_JARVIS_MODEL "qwen2.5:3b-instruct" >nul
setx AURA_LLM_PRIMARY "qwen2.5:3b-instruct" >nul
setx AURA_LLM_JSON "qwen2.5:3b-instruct" >nul
setx AURA_LLM_LONGCTX "llama3.2:3b" >nul
setx AURA_LLM_TRADING "qwen2.5:3b-instruct" >nul
setx AURA_LLM_CREATIVE "qwen2.5:3b-instruct" >nul
setx AURA_LLM_FALLBACK_MODELS "llama3.2:3b,qwen2.5:3b,llama3.2:1b,phi3:mini" >nul
setx AURA_OLLAMA_MODEL "qwen2.5:3b-instruct" >nul
setx OLLAMA_MAX_LOADED_MODELS 2 >nul
setx AURA_OLLAMA_KEEP_ALIVE "5m" >nul
setx AURA_OLLAMA_KEEP_ALIVE_LONGCTX "0" >nul

set AURA_JARVIS_MODEL=qwen2.5:3b-instruct
set AURA_LLM_PRIMARY=qwen2.5:3b-instruct
set AURA_LLM_JSON=qwen2.5:3b-instruct
set AURA_LLM_LONGCTX=llama3.2:3b
set AURA_LLM_TRADING=qwen2.5:3b-instruct
set AURA_LLM_CREATIVE=qwen2.5:3b-instruct
set AURA_LLM_FALLBACK_MODELS=llama3.2:3b,qwen2.5:3b,llama3.2:1b,phi3:mini
set AURA_OLLAMA_MODEL=qwen2.5:3b-instruct
set OLLAMA_MAX_LOADED_MODELS=2

echo [OK] Variaveis gravadas (setx + sessao atual)
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo [AVISO] ollama nao encontrado no PATH.
  echo         Instale o Ollama e rode este BAT de novo para o pull.
  goto FIM
)

echo [PULL] Modelos locais...
ollama pull qwen2.5:3b-instruct
ollama pull llama3.2:3b
echo.
echo [LISTA]
ollama list
echo.

:FIM
echo ============================================================
echo  Proximo: reinicie o terminal e rode AURA_SUBIR_STACK_COMPLETO.bat
echo  GLM continua SO na nuvem - nao faca ollama pull glm
echo  Docs: docs\ARQUITETURA_MODELOS_QWEN_LLAMA.md
echo ============================================================
pause
endlocal
