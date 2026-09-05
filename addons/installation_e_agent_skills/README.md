# Instalação E — Agent Skill Engine e fontes externas opcionais

## Escopo

Esta instalação adiciona o `engine/agents/agent_skill_engine.py`, um registro persistente de skills operacionais com advisor opcional via Ollama, e o `engine/agents/external_sources_e.py`, que contém adaptadores sob demanda para Microlink, Crossref, Open Library e Frankfurter.

O módulo foi instalado **separadamente** das instalações A, B, C e D. Ele não substitui `pc_operator.py`, `jarvis_command_center.py` ou `jarvis_voice_server.py`.

## Estado padrão seguro

A Instalação E permanece inerte no import. Ela não inicia servidor, thread, polling, Ollama, n8n, Docker, microfone, navegador ou chamadas externas automaticamente. O registro no `CommandCenter` não é realizado no startup.

A execução de skills que poderiam controlar o desktop está bloqueada por padrão por:

```text
AURA_E_ENABLE_SKILL_EXECUTION=0
```

O bloqueio também está incorporado no `AgentSkillEngine`: sem habilitação explícita, `execute_skill` retorna uma resposta de desativação e não chama o `DesktopController`.

## Componentes

| Componente | Localização | Estado |
|---|---|---|
| Agent Skill Engine | `engine/agents/agent_skill_engine.py` | Instalado, não conectado ao startup |
| Adaptadores de fontes externas | `engine/agents/external_sources_e.py` | Instalado, sem chamadas no import |
| Estado persistente de skills | `engine/data/agent_skills.json` | Criado somente quando o módulo for usado |
| Manifesto | `addons/installation_e_agent_skills/INSTALL_E_MANIFEST.txt` | Instalado |
| Configuração de referência | `addons/installation_e_agent_skills/.env.example` | Execução desativada |

## Advisor local

O módulo aceita `qwen3:4b` via Ollama, mas a instalação não executa `ollama pull`, não inicia Ollama e não baixa `nomic-embed-text`. Se o modelo não estiver disponível em uma ativação futura, o módulo degrada para passos manuais/fixos.

## Integração não aplicada

Os hunks que alterariam `bridge/jarvis_voice_server.py`, adicionariam `parse_agent_skills` ao roteamento global ou modificariam `scripts/run_selftests.py` não foram aplicados. Essa decisão mantém a instalação E reversível e evita ampliar o perímetro de execução do sistema durante a instalação.

Uma futura ativação deve ser feita em etapa separada, com revisão do catálogo de ferramentas, confirmação de cada operação de desktop e teste de rollback. O registro das fontes E usa prefixo `e_` para evitar colisões quando `build_external_intel_tools_v2` for chamado explicitamente.

## Fontes externas

As fontes públicas só são consultadas quando um método é invocado por código autorizado. Microlink aceita apenas URLs HTTP(S) públicas; caminhos locais e `file://` são rejeitados. Crossref, Open Library e Frankfurter têm limites de resultados, timeouts e validação de entrada. O conteúdo retornado não deve ser tratado como instrução de execução sem revisão.

## Reversão

Para reverter somente esta instalação, copie de volta o conteúdo do diretório `.install-backups/installation-e-*/` correspondente e remova os arquivos E instalados. Não remova backups das instalações A, B, C ou D.
