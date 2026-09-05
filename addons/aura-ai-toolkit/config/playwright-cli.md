# Playwright CLI para coding agents

A CLI é uma alternativa mais econômica em contexto para agentes que trabalham dentro de repositórios grandes.

## Instalação manual

```bash
npm install -g @playwright/cli@latest playwright-cli
playwright-cli install --skills
```

## Comandos básicos

```bash
playwright-cli open http://localhost:3000 --headed
playwright-cli snapshot
playwright-cli screenshot --filename=evidence/home.png
playwright-cli console
playwright-cli requests
playwright-cli close
```

## Regra de segurança

Use somente URL local ou staging autorizado. Não reutilize cookies de produção, não salve `state` contendo credenciais e não use a CLI para publicar, comprar, enviar ordens ou operar contas reais.

## Documentação

<https://playwright.dev/docs/getting-started-cli>
