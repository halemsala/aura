# Expansão de visão do Harness / AURA

## Problema

O snapshot original do Harness enxergava pouco:

- 4 serviços (TCP + health raso)
- `boot_state.json` e `diagnostico_latest.json` se existirem
- policy fixa paper-only

Isso parece “cego”: o operador pergunta e o modelo só vê ON/OFF de porta.

## O que a expansão adiciona (só leitura)

| Camada | Fonte | Para quê |
|--------|--------|----------|
| Serviços | 8080/8765/8099/11434 + latência | Disponibilidade |
| UI state | `GET /api/ui/state` (se engine up) | Painel / captura / home |
| Analysis sample | `GET /api/status` ou health rico | paper_trade, gates |
| Voice detail | `/api/voice/health` campos llm/device | Voz não é só porta |
| Starters oficiais | resolve_* no disco | Sabe se pode “iniciar X” |
| Staging / skills | pastas controladas | O que está pendente |
| LAB catalog | failure_modes + lab_diagnose | Diagnóstico com FM-id |
| Disco AURA_ROOT | existência de pastas-chave | Instalação incompleta |
| Logs oficiais | tail runtime_engine/bridge/voice, install, recovery | Últimos erros sem abrir arquivo |
| Diagnostics deep | `GET /api/diagnostics/deep` (+ fallbacks) | Resumo gates/erros do Engine |

Versão da visão no código: **1.1** (`vision_version`).

## O que continua proibido

- Mutação sem CONFIRMAR
- Stake real / execution_allowed
- “Fazer tudo sozinho” sem evidência e sem plano

## Honestidade vs propaganda

AURA **não** é um OS autônomo que opera 100% do Windows sozinho.  
É supervisor local: análise de jogos + gestão de serviços oficiais + planos com aprovação humana.

A expansão de visão aumenta a **observabilidade** (de ~20% para bem mais do *sistema AURA*), não inventa poderes fora do projeto.
