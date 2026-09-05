# Auditoria da distribuição completa AURA Quant-X

## Status

**CORRIGIDO ESTATICAMENTE; RUNTIME WINDOWS PENDENTE DE NOVA EXECUÇÃO**

## Causa raiz confirmada

O log recebido em 22/08/2026 às 01:24:28 mostra que o pré-teste passou e que a instalação da venv, PyTorch CUDA 12.6, dependências, imports, preflight do Voice, Ollama e GLM-4 passaram. A falha ocorreu na etapa de abertura do Bridge, com `Launcher de Bridge` não abrindo.

A inspeção da árvore de trabalho usada na restauração mostrou que essa cópia estava incompleta: faltavam `ARQUIVO_LEGADO/BAT_PS1/AURA_RUN_BRIDGE.bat`, `ARQUIVO_LEGADO/BAT_PS1/AURA_RUN_ENGINE.bat`, `bridge/server.py` e `engine/server.py`, embora o BAT mestre e o instalador arquivado exigissem esses arquivos. O ZIP final anterior continha esses arquivos; a pasta de trabalho restaurada foi reconstruída a partir dele.

## Correções aplicadas

- Restaurados os servidores `bridge/server.py` e `engine/server.py` a partir da distribuição completa.
- Restaurados `AURA_RUN_BRIDGE.bat` e `AURA_RUN_ENGINE.bat` em `ARQUIVO_LEGADO/BAT_PS1`.
- Corrigido o comando `start` do BAT mestre para usar `cmd.exe /d /k call "%SVC_BAT%"` com uma única camada de aspas.
- Mantida a inicialização na ordem Bridge `8080`, Engine `8765`, Voice `8099`.
- Mantido o bloqueio de processo antigo: health sem o build correto ou porta ocupada sem health válido não é aceito.
- Corrigida a atualização do manual para usar `AURA_MANUAL_ROOT`, sem passar caminho com barra invertida final como argumento frágil.
- Criado um marcador de release inequívoco: `AURA-QUANT-X-12.7.0-FULL-BRIDGE-ENGINE-VOICE-V1`.
- BATs normalizados em CRLF.

## Evidência de validação

| Camada | Resultado |
|---|---|
| Arquivos canônicos Bridge/Engine/launchers | Presentes na árvore restaurada |
| Contratos Voice/Desktop/Installer | 16 testes aprovados |
| Sintaxe Python | Aprovada |
| Pré-teste estático da distribuição | Aprovado |
| Teste real no Windows após a recuperação | Pendente; exige nova execução do ZIP |

## Limites

O sandbox não possui Windows, GPU NVIDIA, Ollama local, microfone ou WebView2. Portanto, não declarar Bridge, Engine, Voice, CUDA, áudio, captura SokkerPRO ou Desktop como operantes até o próximo log do Windows confirmar os health checks e o diagnóstico do Voice.

O sistema continua **PAPER TRADE ONLY**. Nenhuma correção desta auditoria libera ordens reais.
