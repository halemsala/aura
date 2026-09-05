# Instalação S — Intent Router

## Escopo

Esta instalação adiciona `engine/agents/intent_router.py`, extraído do `pasted_content_19.txt`. O módulo roteia linguagem natural para ferramentas do CommandCenter, injeta contexto dinâmico, aplica limite de confiança e usa parser determinístico como fallback.

A instalação é **separada e não integrada**. Os hunks H-IR1 e H-IR2 não foram aplicados: o `jarvis_voice_server.py` continua usando o fluxo existente, sem inversão global para LLM-first e sem chamadas novas a LLM durante o startup.

## Correções aplicadas

| Item | Correção |
|---|---|
| Cache semântico | O cache passou a armazenar tokens e sessão, em vez de tentar reconstruir tokens a partir do hash SHA-256 |
| JSON do LLM | A extração foi substituída por `JSONDecoder.raw_decode`, aceitando objetos aninhados em `args` |
| Ordem de roteamento | LLM é tentado primeiro e o parser determinístico só é usado como fallback, conforme a proposta do anexo |
| Confiança | Valores não numéricos, infinitos ou fora de 0–1 são normalizados antes do threshold |
| Isolamento | A chamada de LLM só ocorre quando um `ask_fn` é fornecido explicitamente; sem isso, o parser local é usado |
| Self-test | O fake LLM foi corrigido para ler a frase do usuário, sem confundir o contexto de grupos com a intenção atual |

## Estado seguro

Nenhum LLM foi chamado durante a instalação. Nenhum provider de contexto real foi conectado, nenhuma tool nova foi registrada no CommandCenter global e nenhum servidor, Telegram, userbot, rede ou autostart foi iniciado.

## Arquivos

| Arquivo | Função |
|---|---|
| `engine/agents/intent_router.py` | Implementação canônica |
| `addons/installation_s_intent_router/intent_router_from_pasted_content_19.py` | Cópia rastreável do anexo |
| `addons/installation_s_intent_router/INSTALL_S_MANIFEST.txt` | Hashes, backup e estado de integração |
| `addons/installation_s_intent_router/README.md` | Documentação da instalação |

## Validação

O self-test verifica intenção natural com argumentos, cache semântico, fallback determinístico, confirmação pendente, conversa casual, threshold de confiança, contexto e Jaccard. O resultado aprovado foi `ALL TESTS PASSED - intent_router.py`.

## Ativação futura

A ativação do roteador no voice server deve ser feita em instalação independente, com escolha explícita do modelo, limite de custo/latência, allowlist de tools, proteção de confirmações e testes de regressão. O CommandCenter deve continuar sendo a autoridade de execução e suas políticas fail-closed não devem ser bypassadas pelo LLM.

## Reversão

O backup da instalação R/S está em `.install-backups/installations-r-s-20260825_102059/`. Como os arquivos canônicos R e S não existiam antes, o backup contém marcadores de ausência. Para reverter somente S, remova o arquivo canônico e o diretório `addons/installation_s_intent_router`; preserve R e as instalações anteriores.
