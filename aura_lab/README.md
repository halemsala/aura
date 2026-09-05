# AURA LAB — Failure Mode Catalog + Agente de Resiliência

Ambiente **controlado** para descobrir, simular (só no lab), diagnosticar e registrar falhas do AURA QUANT-X.  
Não injeta falhas no sistema de uso diário. Não desliga paper_trade. Não executa mutação sem CONFIRMAR.

## Objetivo

1. Catálogo versionado de modos de falha reais do AURA.
2. Agente LAB em modo **advisory**: lê snapshot + catálogo → propõe diagnóstico e reparo.
3. Registro append-only (`lab_failures.jsonl`) que vira o "manual vivo" de quebra/reparo.
4. Injeção **opcional** só quando `LAB_MODE=1` e alvo for pasta/clone de lab.

## Invariantes (iguais ao AURA oficial)

- `paper_trade=true`
- `execution_allowed=false`
- `GLM_ADVISORY_ONLY`
- Mutação real → plano + **CONFIRMAR** (Harness)
- Lab nunca promove skill/repo sozinho

## Estrutura

```
aura_lab/
  README.md                 ← este arquivo
  schema/
    failure_mode.schema.json
    lab_record.schema.json
  catalog/
    failure_modes_v1.yaml   ← cenários iniciais (expandir)
  agent/
    lab_agent_spec.md       ← contrato do agente LAB
    prompts/
      diagnose_system.md
  records/
    lab_failures.jsonl      ← (vazio no repo; runtime)
  tools/
    catalog_loader.py       ← carrega e valida catálogo
    record_writer.py        ← append seguro no jsonl
    snapshot.py             ← health TCP/HTTP local (só leitura)
    lab_diagnose.py         ← CLI: sintoma + snapshot → diagnóstico + registro
```

## Fluxo mínimo

```
snapshot (status/health) 
  → match no catálogo (sintoma / serviço / código)
  → proposta ADVISORY (causa provável + passos de reparo)
  → [opcional] plano Harness + CONFIRMAR
  → verificação (health de novo)
  → registro em lab_failures.jsonl
```

## Uso da CLI

```bash
cd aura_lab

# Só sintoma
python3 tools/lab_diagnose.py "desktop abriu mas o painel nao carregou"

# Sintoma + snapshot real (portas 8080/8765/8099/11434)
python3 tools/lab_diagnose.py --snapshot "engine offline"

# Só snapshot (query montada a partir do que está OFF)
python3 tools/lab_diagnose.py --snapshot

# JSON para automação / Harness
python3 tools/lab_diagnose.py --snapshot --json "voz nao responde"

# Validar catálogo
python3 tools/catalog_loader.py
python3 tools/catalog_loader.py --match "bridge 501"
```

Cada diagnóstico (exceto `--no-record`) grava uma linha em `records/lab_failures.jsonl`.

## Release ZIP (obrigatório a cada atualização)

```bash
cd aura_lab
python3 tools/pack_release.py              # usa VERSION atual
python3 tools/pack_release.py --bump-patch # incrementa patch e gera ZIP
python3 tools/pack_release.py --version 0.2.0
```

Saída: `artifacts/AURA_LAB_v<versão>_<UTC>.zip`  
Inclui `BUILD_MANIFEST.txt` (arquivos + política paper-only).

## Como expandir

- Novo sintoma de campo → nova entrada em `failure_modes_v1.yaml` (nunca editar histórico do jsonl).
- Cada entrada precisa: `id`, `symptom`, `service`, `detect`, `repair_steps`, `verify`, `severity`.
- Preferir 1 falha por teste; não "1000 erros de uma vez".
- **Após qualquer mudança:** `python3 tools/pack_release.py --bump-patch`

## Próximos passos sugeridos

1. [x] Validar schema + catálogo v1 com `catalog_loader.py`
2. [x] CLI `lab_diagnose` + snapshot HTTP
3. [x] `pack_release.py` — ZIP a cada atualização
4. [x] Intent no Harness + visão ampliada (`harness/harness_lab_vision.py`)
5. Injetores LAB (503, timeout, payload inválido) atrás de `LAB_MODE=1`
6. Aprofundar vision: logs tail, `/api/diagnostics/deep`, paper summary

## Harness — comandos novos (após INSTALL_NO_HARNESS.txt)

```
visão
status
lab diagnostico engine offline
lab diagnostico desktop abriu mas painel nao
ajuda
```
