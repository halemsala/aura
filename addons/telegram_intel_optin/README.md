# Add-on: Telegram Intel (OPT-IN) — AURA

**Estado por defeito: DESLIGADO (inerte)**  
**Não faz parte do hot path** Bridge → Engine → decisão paper.

## O que é
Canal opcional para:
- publicar resumos/tips **paper/advisory** em grupos Telegram free;
- ingestão assistida de texto público (URLs allowlisted pelo operador).

## O que NÃO é
- Não ativa `execution_allowed`
- Não altera YAML de thresholds do Engine
- Não substitui o feed SokkerPro/Bridge como fonte de verdade de jogo ao vivo
- Não contorna PolicyGate / Paper Lock

## Ativação (manual)
1. Criar bot com @BotFather e obter token (você guarda o token; não commitar).
2. Copiar `config/telegram_intel.env.example` → `C:\aura\config\telegram_intel.env` e preencher.
3. Definir `AURA_TELEGRAM_INTEL_ENABLED=1` **apenas** nesse env (não no runtime de execução de ordens).
4. Correr `scripts\telegram_intel_dry_run.bat` (só valida config, não envia).
5. Só depois: processo worker separado (não dentro do Voice hot path).

## Compliance
Sites e Telegram têm Termos de Uso próprios. “Grátis” ≠ automaticamente permitido para scrape automatizado.
O operador é responsável por allowlist de URLs, ritmo de pedidos e conteúdo publicado.
Patentes não são o tema central; ToS, qualidade de dados e side-effects sim.
