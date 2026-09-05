# Arquitetura — Telegram Intel Opt-in

## Separação de planos

```
[Plano A — Núcleo AURA paper]
  Feed oficial → Janitor → Agentes → RedTeam → ui/state
  execution_allowed=false sempre

[Plano B — Add-on Telegram Intel]  (processo/worker separado)
  allowlist URLs (opcional) → parse texto → DB local tips
  → reescrita advisory (LLM) → publish Telegram (se ENABLED e não DRY_RUN)
  Nunca chama ExecutionRouter com live
```

## Por que não no hot path
- Timeout/rede do Telegram não pode atrasar decisão de canto ao vivo.
- Falha do bot não pode derrubar Engine/Bridge.
- Publish é side-effect: AuditLedger + flag explícita.

## Scrape
- Só com `AURA_TELEGRAM_ALLOW_SCRAPE=1` e URL na allowlist.
- Rate limit obrigatório.
- Output = candidatos a tip; validação AURA continua paper/advisory.
- Fonte de verdade do jogo continua sendo Bridge/SokkerPro.

## Ativação futura “grupos free”
1. Bot + chat_id dos grupos
2. Templates de mensagem (sem prometer lucro)
3. Fila local + retry
4. Moderação humana na primeira fase
