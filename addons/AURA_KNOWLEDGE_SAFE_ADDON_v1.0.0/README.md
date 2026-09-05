# AURA Maximizer — Safe Addon

Addon isolado para aumentar a inteligência e a produtividade do AURA com **Skills**, conectores read-only, rotinas plan-only, agentes advisory, firewall LLM e observabilidade local.

## Garantias

O addon não inicia rede, não cria clientes externos, não instala dependências, não agenda jobs, não executa ferramentas, não publica, não envia mensagens e não habilita execução financeira. Todas as decisões mantêm `paper_trade=true`, `execution_allowed=false` e `glm_advisory_only=true`.

## Módulos

| Módulo | Função |
|---|---|
| `contracts.py` | Tipos e invariantes Paper-Only |
| `firewall.py` | Parsing estrito e fallback `BLOCK` |
| `connectors.py` | Allowlist de planos read-only |
| `routines.py` | Definição de rotinas desativadas |
| `agents.py` | Pipeline AURA One → Hermes advisory |
| `observability.py` | Eventos locais redigidos e hash |
| `skills/` | Método operacional versionado |
| `tests/` | Testes offline sem rede |

## Integração

A instalação recomendada é namespaced, por exemplo `addons/aura_maximizer/`. O `AuraController` existente continua sendo a autoridade. Qualquer integração com `engine/`, `bridge/`, MCP, APIs, n8n, Airflow, Temporal, voz ou publicação é uma etapa posterior e opt-in.

Leia `INSTALLAR_NO_OUTRO_CHAT.md` para o prompt completo de instalação em outro chat do Manus.
