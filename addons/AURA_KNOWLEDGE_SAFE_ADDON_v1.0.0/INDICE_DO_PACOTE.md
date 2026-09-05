# Pacote de conhecimento e código para AURA — sem o sistema AURA original

Este ZIP reúne o material produzido e pesquisado nesta conversa para uso pelo Grok ou outro agente de implementação. **O sistema AURA original não está incluído.**

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `code/` | Código próprio do addon, pipeline Hermes + AURA IA e testes offline |
| `skills/` | Skills próprias criadas para ingestão, governança, revisão Hermes e explicação |
| `configs/` | Configuração segura e catálogo de ferramentas externas |
| `installer/` | Instaladores POSIX, backup e rollback |
| `windows/` | Instalador PowerShell e wrapper CMD |
| `docs/research/` | Relatórios, notas, transcrições e análises das postagens/Reels |
| `docs/official/` | Documentação oficial consultada sobre Skills, Hooks, MCP, Agent SDK e observabilidade |
| `docs/installation/` | Prompts e instruções de instalação para Grok |
| `MANIFESTO_CONHECIMENTO.json` | Escopo, contagens, exclusões e política de segurança |

## Conteúdo coletado

O material cobre Skill, Conector, Rotina, Agente, Claude Code Setup, Task Observer, Find Skills, MCP, Ralph Loop, CCMA, pipeline planner–coder–tester–reviewer–security, Context Engineering, Verification Before Completion, Systematic Debugging, Webapp Testing, Web Quality Audit, observabilidade, memória, n8n, Airflow, Temporal, LangGraph, PydanticAI, CrewAI, AutoGen, Semantic Kernel, TradingView, Cloudflare, Higgsfield, Ollama e Telegram.

## Limite importante

Não foram embutidos códigos completos de repositórios de terceiros, modelos, credenciais, MCPs, frameworks externos ou ferramentas prometidas por DM. Esses itens aparecem como catálogo, referência ou recomendação porque não foram baixados, auditados e validados para Windows. O Grok deve tratar cada um como candidato opcional e bloqueado.

## Política de instalação

O código próprio é inerte por padrão. Ele não cria serviço, autostart, tarefa agendada, conexão de rede, login, publicação, envio de mensagem, execução financeira, download de dependência ou ativação de IA. A instalação no AURA deve ocorrer em cópia de trabalho, com `Plan` → `Stage` → confirmação → `Install` → `Verify`.
