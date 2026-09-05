---
name: aura-operator-autonomo
version: 37.3.47
description: Instalador autonomo AURA QUANT-X para C:\AURA_V25. Preflight, cura de ficheiros em falta, arranque paper-only, evidencia e janela que nao fecha.
entrypoint: AURA_INSTALAR_TESTAR_AUTONOMO.bat
engine: AURA_MOTOR_AUTONOMO.ps1
---

# AURA Operator Autonomo

Usar quando o utilizador esta em Windows PowerShell, o BAT fecha, ou faltam `hermes_v10`, Matriz ou Voz.

## Invariantes
paper_trade=true · execution_allowed=false · GLM_ADVISORY_ONLY · bind 127.0.0.1

## Ponto de entrada
Na raiz C:\AURA_V25 (ficheiros ja copiados, sem Expand-Archive):

    AURA_INSTALAR_TESTAR_AUTONOMO.bat

O BAT so valida PowerShell e chama `AURA_MOTOR_AUTONOMO.ps1`. Nunca fecha sem `pause`.

## O que o motor faz
1. Confirma ROOT com engine\server.py
2. Inventario: engine, bridge, matriz, hermes_v10_chat_api, jarvis_voice_server, smoke, relatorio
3. Cura: copia de caminhos alternativos ou procura no disco e coloca no sitio
4. Arranque via cmd.exe /c (evita o bug PowerShell `$args` + Start-Process ArgumentList)
5. Health HTTP + smoke + relatorio geral
6. Escreve logs_supervisor\MOTOR_AUTONOMO_LATEST.txt

## Portas
8080 Bridge · 8765 Engine · 8766 Matriz · 8777 Hermes · 8099 Voice · 11434 Ollama

## Erros conhecidos que este pack corrige
- ZIP com pasta AURA_COMPLETE_... — Hermes nao cai em C:\AURA_V25\hermes_v10
- Comandos BAT colados no PowerShell (`start /MIN`, `curl -m`, `%PY%`)
- Start-Process -ArgumentList $args (variavel reservada → ArgumentList null)
- BAT LF-only + exit sem pause
- scripts\aura_serve_matriz.py em falta na instalacao antiga

## Nao fazer
Nao pedir Expand-Archive se o utilizador ja colocou os ficheiros na pasta.
Nao matar Ollama.
Nao ativar execution real.

## Encoding
Motor em ASCII + UTF-8 BOM. Nao usar travessao nem aspas curvas (quebra PowerShell 5.1).

## Hermes 8777
Exige pasta hermes_v10 COMPLETA com core\hermes_llm_engine.py.
Launcher: hermes_v10\AURA_RUN_HERMES.py
Python so 3.10/3.11 (nunca py default 3.14).
