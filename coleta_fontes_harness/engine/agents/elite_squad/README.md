# Elite Squad Advisory (paper-only)

Incorporado em `engine/agents/elite_squad/`.

## Import

```python
from engine.agents.elite_squad import RED_TEAM, DATA_JANITOR, FORENSICS, ROI_AUDITOR
from engine.agents.elite_squad.integration_hooks import audit_proposal, sanitize_feed
```

## Regras

- `paper_trade=True` / `execution_allowed=False` sempre nas saídas de audit
- Tuner grava só `engine/data/threshold_suggestions.json` (`applied: false`)
- Sem Telegram, scrape de tips, GitHub no hot path, auto-write de YAML de produção
- **Não** está em `agents/ENABLED` por defeito — activação = import explícito no código do Engine após revisão

## Spec / schemas

- `docs/elite_squad/SPEC_ELITE_SQUAD_ADVISORY_PAPER.md`
- `schemas/elite_squad/*.json`
