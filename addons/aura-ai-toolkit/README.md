# AURA AI Toolkit

Pacote seguro e rastreável para programar, testar e revisar o AURA com Grok, Claude, Cursor, VS Code, Copilot, Codex ou outro agente compatível com MCP.

## Objetivo

Este pacote implementa o princípio **construir e provar são etapas diferentes**. Um agente pode planejar e alterar o código; outro processo deve executar os testes no navegador, verificar o comportamento real e anexar evidências antes da aprovação.

## Conteúdo

| Diretório | Conteúdo |
|---|---|
| `prompts/` | Prompts para planejamento, implementação, verificação independente e revisão final. |
| `skills/` | Instruções reutilizáveis para teste baseado em evidência e operação segura do AURA. |
| `templates/` | Matriz de testes, relatório de verificação, checklist de PR e arquivo de casos-limite. |
| `config/` | Exemplos de configuração do Playwright MCP e do Playwright CLI. |
| `docs/` | Guia de instalação, fluxo recomendado e catálogo de ferramentas. |
| `scripts/` | Auditoria local do pacote e verificações simples de integridade. |
| `checksums/` | Hashes dos artefatos gerados. |

## O que não está incluído

O ZIP não contém Node.js, Grok, modelos de IA, credenciais, cookies, sessões de navegador, dependências pesadas, executáveis ou código operacional do AURA. A instalação de ferramentas externas é deliberadamente manual e deve ser feita somente depois da revisão do ambiente.

## Fluxo recomendado

1. Copie este pacote para o repositório do AURA, fora do código de produção.
2. Preencha `templates/test_plan.md` antes de pedir qualquer alteração ao agente.
3. Use `prompts/01_planner.md` para gerar critérios de aceite e riscos.
4. Use `prompts/02_implementer.md` para orientar a alteração mínima e segura.
5. Execute a validação offline do próprio AURA.
6. Use `prompts/03_independent_verifier.md` com Playwright MCP ou `playwright-cli`.
7. Preencha `templates/verification_report.md` com screenshots e resultados observados.
8. Use `prompts/04_pr_gate_reviewer.md` somente após a evidência existir.

## Guardrails do AURA

Durante instalação e testes, mantenha serviços, integrações externas, userbot, Telegram poller, TTS, microfone, câmera, scheduler, autostart, publicação e execução financeira desligados. Use dados falsos, fixtures e ambiente local/staging. Não coloque tokens em prompts, arquivos de configuração ou screenshots.

Quando existirem no projeto, preserve `PAPER_TRADE=true`, `EXECUTION_ALLOWED=false` e `GLM_ADVISORY_ONLY=true`. Uma integração conectada não equivale a uma autorização para executar ações externas.

## Referências

A configuração do Playwright MCP segue a documentação oficial: <https://playwright.dev/docs/getting-started-mcp>. Para agentes de código, compare também o `playwright-cli` e as skills oficiais: <https://playwright.dev/docs/getting-started-cli>. O repositório oficial do MCP é <https://github.com/microsoft/playwright-mcp>.
