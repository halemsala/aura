# Instalações recuperadas — módulos G a M

Esta entrega recupera módulos completos dos anexos anteriores e instala o módulo de inteligência futebolística do anexo 14. Cada grupo tem backup comum com lista de caminhos, e nenhum hunk de integração que possa iniciar serviços ou ativar automações foi aplicado automaticamente.

## Grupos instalados

| Grupo | Fonte | Arquivos |
|---|---|---|
| G — People Memory | `pasted_content_2.txt` | `engine/agents/people_memory.py` |
| H — Research e Media | `pasted_content_6.txt` | `engine/agents/research_improver.py`, `engine/agents/media_editor.py` |
| I — Desktop e Telegram | `pasted_content_7.txt` | `engine/agents/desktop_controller.py`, `engine/agents/telegram_employee.py` |
| J — Voice Auth e Router | `pasted_content_9.txt` | `engine/agents/voice_auth.py`, `engine/agents/command_router_v2.py` |
| K — Boot, Voice Client e Vision | `pasted_content_10.txt` | `engine/boot.py`, `scripts/aura_voice_client.py`, `engine/agents/vision.py` |
| L — External Intelligence | `pasted_content_11.txt` | `engine/agents/external_intelligence.py` |
| M — Football Intelligence | `pasted_content_14.txt` | `engine/agents/football_intelligence.py` |

## Correções de compatibilidade

O parser de macros do `desktop_controller.py` tinha um dois-pontos indevido e uma guarda `if` ausente; ambos foram corrigidos localmente. O cliente de voz recebeu o import explícito de `sys`. O módulo de futebol recebeu o import explícito de `urllib.parse`, usado nas consultas Crossref. O `engine/boot.py` recebeu a raiz correta do projeto: como está diretamente dentro de `engine/`, usa `parents[1]`, não `parents[2]`.

O Final Check foi atualizado para reconhecer `engine/core/sensor_cache.py` e `engine/core/latency_sim.py`, que já existiam nesses caminhos corretos, e para incluir `engine/agents/football_intelligence.py`.

## Segurança e ativação

Os módulos foram copiados para a árvore principal, mas não foram conectados ao startup do servidor de voz, à cadeia global de parsers, ao Telegram poller, ao boot automático ou ao autostart. `desktop_controller.py`, `telegram_employee.py`, `vision.py`, `external_intelligence.py` e `football_intelligence.py` só fazem ações de hardware, rede ou dados quando suas funções são chamadas explicitamente.

O `boot.py` não foi executado com `--check`, `--self-test` ou modo contínuo durante a instalação. O `aura_voice_client.py` não abriu microfone nem enviou dados. O Telegram não foi iniciado. PeopleMemory não iniciou câmera e não gravou biometria. As fontes externas não foram consultadas.

As políticas financeiras permanecem `PAPER_TRADE=true`, `EXECUTION_ALLOWED=false` e `GLM_ADVISORY_ONLY=true`. O cálculo de Kelly do módulo de futebol é somente matemático e continua dentro de paper trade; não existe função de aposta, stake, carteira ou execução real.

## Compatibilidade para dependências históricas

Os anexos forneciam apenas hunks de integração para `persona_bridge.py` e `web_knowledge.py`, sem módulos completos. Para eliminar as lacunas de import sem inventar integrações perigosas, foram instalados dois shims locais, pequenos e documentados: `persona_bridge.py` com presença opt-in e `web_knowledge.py` com armazenamento JSONL local e ranking lexical sem rede. Eles não ativam câmera, biometria, scraping ou chamadas externas no import.

`sensor_cache.py` e `latency_sim.py` não são faltantes: existem em `engine/core/` e o Final Check foi corrigido para usar os caminhos reais.

## Reversão

O backup independente está no diretório informado no manifesto de backup gerado junto com esta instalação. Para reverter o lote, remova somente os 15 arquivos listados no `INSTALLED_PATHS.txt` e os diretórios de documentação dos grupos G–M. Não remova módulos anteriores A–F.
