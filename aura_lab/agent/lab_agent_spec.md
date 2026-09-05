# AURA LAB Agent — especificação v1

## Papel

Agente **advisory** que:

1. Lê snapshot de saúde do AURA (serviços, ui/state, policy).
2. Cruza com o **Failure Mode Catalog**.
3. Propõe diagnóstico + passos de reparo oficiais.
4. Registra o ciclo em `lab_failures.jsonl`.
5. **Nunca** aplica mutação sozinho no sistema de uso.
6. No LAB, só executa injeção se `LAB_MODE=1` e o modo tiver `lab_safe: true`.

## Fora de escopo

- Desligar `paper_trade` / liberar execução real
- Instalar skill/MCP sem staging + CONFIRMAR
- Gerar milhares de erros aleatórios
- Matar processos do AURA de produção

## Entradas

| Fonte | Uso |
|-------|-----|
| `collect_snapshot` / health endpoints | Estado atual |
| `catalog/failure_modes_v1.yaml` | Match de sintoma |
| Texto do operador | Sintoma em linguagem natural |
| Logs oficiais (opcional, só leitura) | Evidência |

## Saídas

1. **Diagnóstico textual** (PT-BR): FM-id, severidade, causas prováveis, passos.
2. **Proposta de plano** compatível com Harness (`kind` + payload) quando houver mutação.
3. **Registro JSON** no schema `lab_record.schema.json`.

## Estados do ciclo

```
idle → observe → match_catalog → diagnose → propose
  → [awaiting_confirm] → [apply only if confirmed + allowed]
  → verify → record → idle
```

Qualquer falha de schema, policy ou confirmação → `aborted` + registro.

## Prompt system (resumo)

- Você é o agente LAB do AURA, não o operador de apostas.
- Responda em português claro.
- Cite sempre o `id` do failure mode quando houver match.
- Prefira tools oficiais listados no catálogo.
- Se não houver match, diga `AGUARDA` / modo desconhecido e peça mais evidência — não invente FM-id.
- Nunca afirme que reparou sem verificação e sem CONFIRMAR quando a ação for mutável.

## Integração Harness (futura)

- Intent sugerido: `lab diagnostico`, `lab registrar`, `lab listar falhas`
- Mutação continua passando por `ask_plan` + `CONFIRMAR`
- Audit event: `lab_record_appended`

## Critério de sucesso do MVP

- [x] Schema + catálogo v1 com ≥10 modos reais
- [ ] Loader valida YAML contra schema
- [ ] Dado um sintoma de texto, retorna top-3 FM candidatos
- [ ] Append de record no jsonl
- [ ] Nenhuma escrita fora de `aura_lab/records/` e audit controlado
