# MORA DAILY REPORT — YYYY-MM-DD

**Gerado em:** YYYY-MM-DD HH:MM:SS UTC
**Pipeline:** AURA QUANT-X V25 — MORA Master Agent
**Invariantes:** paper_trade=true | execution_allowed=false | GLM_ADVISORY_ONLY=true

---

## 1. RESUMO DE SAÚDE DO SISTEMA

**Síntese do GLM:**
[Resumo executivo gerado pelo GLM analisando os resultados do omnipotent_health_profiler e quality_audit. Inclui score de saúde 0-10, problemas críticos e gargalos.]

**Issues Detectados:**

### Memória
- [WARNING/OK] [Fragmentação de memória detectada ou sistema estável]
- [WARNING/OK] [VRAM fragmentada ou dentro do normal]

### Drift
- [WARNING/OK] [Schema drift detectado ou ausente]

### Latência
- [WARNING/OK] [Previsão de falha em Xh ou sem previsão de falha]

<details><summary>Detalhes do Health Profiler</summary>

```json
[Output completo do omnipotent_health_profiler.run_full_diagnostic() — limitado a 3000 chars]
```

</details>

---

## 2. PESQUISA DE MERCADO (Novidades)

### Reddit (Top Posts do Dia)
- **r/SoccerBetting**: [Título do Post](URL) (score N)
  > [Snippet do conteúdo...]
- **r/algobetting**: [Título do Post](URL) (score N)
- **r/sportsbetting**: [Título do Post](URL) (score N)

### GitHub (Repositórios Relevantes)
- **[user/repo](URL)** (N★): [Descrição do repo]
- **[user/repo](URL)** (N★): [Descrição do repo]

### arXiv (Papers Acadêmicos)
- **[Título do Paper](URL)**
  > [Resumo do paper...]
- **[Título do Paper](URL)**
  > [Resumo do paper...]

**Insights do GLM:**
[Síntese do GLM sobre o que vale adaptar, padrões que corroboram/contradizem o sistema, e técnicas aplicáveis encontradas.]

---

## 3. OPORTUNIDADES DE OTIMIZAÇÃO DE CÓDIGO

### `bridge/server.py`
- **Gargalo:** [Descrição do gargalo identificado ou "Nenhum gargalo crítico"]
- **Issue:** [Descrição específica do problema]
- **Severidade:** [high/medium/low]
- **Patch proposto:**
```python
[Trecho de código corrigido proposto pelo GLM]
```

### `engine/server.py`
- **Gargalo:** [...]
- **Issue:** [...]
- **Severidade:** [...]
- **Patch proposto:**
```python
[...]
```

### Erros Recentes Detectados
- `live_feed.jsonl`: [Descrição do erro]
- `data/glm_decisions.jsonl`: [Descrição do erro]

---

## 4. AÇÕES RECOMENDADAS

[Síntese final do GLM com prioridades de ação, risco de inação e esforço estimado]

1. **Prioridade Imediata:** [O que fazer primeiro]
2. **Risco de Inação:** [O que acontece se não fizer]
3. **Esforço:** [baixo/médio/alto]

---

*Sistema de agentes retomado com sucesso após ciclo MORA.*
*Todos os invariantes preservados: paper_trade=true | execution_allowed=false*
*AURA QUANT-X V25 — YYYY-MM-DD HH:MM:SS UTC*