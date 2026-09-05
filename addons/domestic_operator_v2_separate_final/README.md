# Domestic Operator v2 — instalação separada

Este addon foi instalado separadamente a partir de `pasted_content_6.txt`. Ele não substitui o `pc_operator.py`, não altera o `jarvis_voice_server.py` e não se mistura com as instalações A, B ou C.

## Escopo

O módulo confina operações de arquivo à pasta `Documentos/AURA_Domestico`, com subpastas `notas`, `listas` e `relatorios`. Caminhos absolutos fora do sandbox, traversal e symlink escapando da raiz são negados. A busca fica limitada ao sandbox e a leitura web não é exposta.

Mutação de arquivo exige plano falado e confirmação `sim`. Edição, sobrescrita e exclusão preservam cópia recuperável na lixeira doméstica e registram auditoria local. Programas só podem ser selecionados pela allowlist manual `engine/data/app_allowlist.json`; caminho ou `.exe` dito por voz é recusado. Entradas `heavy: true` podem acionar a pausa de recursos somente quando o addon for ativado manualmente.

A pausa/retomada pode descarregar modelos do Ollama, parar câmera e chamar hooks plugáveis. A instalação não iniciou Ollama, câmera, microfone, servidor de voz, processos ou autostart.

## Estado

`STATUS=installed-separated-not-activated`, `PC_OPERATOR_V1=untouched`, `VOICE_SERVER=untouched`, `AUTOSTART=false` e `EXECUTION_STARTED=false`.

## Validação

O módulo passou em compilação Python e no smoke test separado com sandbox temporário, confirmação de mutação, allowlist de programa pesado, pausa simulada e recusa de caminho externo.

## Reversão

Remova apenas a pasta do addon e restaure o arquivo do backup indicado no `INSTALL_D_MANIFEST.txt`. Nenhuma instalação anterior precisa ser revertida.
