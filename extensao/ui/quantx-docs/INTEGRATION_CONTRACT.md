# Contrato de integração — AURA QUANT-X UI

## Fontes de verdade

A nova interface não cria uma fonte de verdade adicional. Ela consome três fontes existentes:

| Responsabilidade | Fonte | Regra |
|---|---|---|
| Estado da partida | reconciliador/estado retornado por `GET_DIAGNOSTICS` | uma partida por vez, com `fixtureId` travado |
| Gráficos originais | `CHARTS_UNIFIED_GET` | conservar `readiness`, `source`, `updatedAt`, `status` e `N/D` |
| Decisão e risco | `GET /api/analysis/{fixtureId}` | a UI apenas narra e mostra; não recalcula autorização |

## Famílias de gráficos

O módulo standalone espera o pacote de gráficos unificados com estas famílias:

| Nome interno | Nome na interface | Campo esperado |
|---|---|---|
| `appm` | Pressão 3/5/10 min | `charts.appm` |
| `xg` | Gols esperados (xG) | `charts.xg` |
| `timeline` | Linha do tempo do jogo | `charts.timeline` |
| `oddsOscillation` | Oscilação das odds | `charts.oddsOscillation` |
| `macdXg` | Momento do xG | `charts.macdXg` |
| `pbar` | Pressão relativa | `charts.pbar` |
| `h2h` | Histórico entre equipes | `charts.h2h` |
| `radar` | Radar de estatísticas | `charts.radar` |

Cada família deve manter seu próprio `status`: `ready`, `pending`, `stale` ou equivalente. A UI traduz para `PRONTO`, `AGUARDANDO` e `DESATUALIZADO`.

## Campos da partida

A UI aceita `home`, `away`, `fixtureId`, `score.home`, `score.away`, `minute`, `liveStatus`, `stats.corners`, `stats.xg`, `matchEvents`, `quality`, `freshness`, `sources` e `diagnostics`. Se o projeto usar nomes diferentes, ajustar somente o adapter.

## Campos de decisão

A UI procura `decision`, `action`, `signal`, `corner_prob`, `calibrated_probability`, `market_prob`, `edge`, `uncertainty`, `risk.exposure`, `risk.final_exposure`, `risk.kelly`, `risk.raw_kelly`, `risk.reason`, `data_integrity.issues` e `model`.

A ausência de um campo é apresentada como `—` ou `N/D`. Não usar zero como substituto semântico.

## Chat

O chat envia:

```json
{
  "message": "Por que bloqueou?",
  "fixtureId": "fixture-atual",
  "context": {
    "score": {"home": 1, "away": 0},
    "minute": 35,
    "stats": {},
    "events": [],
    "charts": {},
    "quality": {},
    "analysis": {}
  },
  "systemContext": {
    "view": "kanteiro-fullscreen",
    "fixtureLock": true,
    "failClosed": true
  },
  "history": []
}
```

A resposta esperada pode usar `reply`, `message` e `analysis`. A UI não deve interpretar uma frase do LLM como autorização. A decisão mostrada deve continuar vindo de `analysis`/Risk Engine.

## Glossário apresentado ao usuário

| Termo técnico | Rótulo principal |
|---|---|
| `corner_prob` | Probabilidade de escanteio |
| `p_calibrated` | Probabilidade ajustada |
| `market_prob` | Probabilidade do mercado |
| `edge` | Vantagem calculável |
| `raw_kelly` | Cálculo teórico |
| `risk_cap` | Limite de risco |
| `data_integrity` | Qualidade dos dados |
| `source_conflict` | Fontes divergentes |
| `stale` | Desatualizado |
| `pending` | Aguardando dados |
| `fixture lock` | Partida travada |

O termo técnico pode aparecer em tooltip, no diagnóstico ou entre parênteses, mas o rótulo claro deve ser o principal.
