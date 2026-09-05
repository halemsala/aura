# Manifesto do AURA AI Toolkit

**Pacote:** `aura-ai-toolkit`  
**Versão:** `1.0.0`  
**Propósito:** programação e verificação segura do AURA com agentes de IA.

## Conteúdo

O pacote contém quatro prompts de trabalho, uma skill de verificação baseada em evidência, modelos de plano e relatório, configurações exemplificativas para Playwright MCP e CLI, catálogo de ferramentas, guia de instalação manual, auditoria local e a análise do Reel de origem.

## Exclusões intencionais

Não contém credenciais, cookies, sessões, chaves de API, tokens, executáveis, modelos, dependências Node instaladas, código proprietário do AURA ou arquivos de produção. Não inicia servidores, não acessa contas e não altera configurações do usuário.

## Integridade

O ZIP deve ser auditado com `scripts/audit_package.sh`, testado com `unzip -t` e acompanhado de SHA-256 externo ao arquivo. O próprio arquivo de hash não deve ser incluído dentro do ZIP.

## Política de uso

Instalações externas são manuais. O responsável deve revisar cliente MCP, hosts autorizados, armazenamento de sessão, permissões, backup e rollback antes de conectar o pacote a um repositório ou conta.
