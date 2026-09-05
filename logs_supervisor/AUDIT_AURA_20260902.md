# Auditoria AURA — 2026-09-02

Âmbito: stack local `C:\aura`. Sem apostas reais (`execution_allowed=false`). Sem matar Ollama. Sem fallback silencioso 1B/3B.

## Checklist operacional

| Item | Estado | Nota |
|---|---|---|
| Ollama :11434 | PASS | qwen3:8b Q4_K_M residente ~5.3 GiB VRAM |
| Alfred :8791 | PASS | modelo qwen3:8b, ctx 3072, keep_alive -1 |
| Hermes chat :8777 | PASS | think=false, ctx 3072, keep_alive -1 |
| Voz :8099 Whisper CPU | PASS | Python 3.11, não o venv do engine |
| Engine :8765 | PASS | 38 agentes declarados, 31 runnable |
| Matriz :8766 | PASS | UI matriz_v22 |
| Bridge :8080 | PASS | |
| qwen3:8b exclusive | PASS | 3b/1b/coder NÃO carregados em paralelo |
| Ferramentas Alfred | PASS | 80+ tools registadas (core) |
| Apagar sem AUTORIZO | PASS | dry-run + backup |
| Windows/System32 bloqueado | PASS | validators |
| Teclado/rato | PASS | AUTORIZO |
| Arranque Windows | PASS | Startup + HKCU Run AURA_Alfred |
| paper_trade flags | PASS | false no runtime Alfred (não bloqueia desktop) |
| execution_allowed | PASS | sempre false |
| Resposta «1 de 1 tarefas» | PASS (corrigido) | resumo humano do estado |
| Watchdog voz | PASS (corrigido) | health `/api/voice/health`; voz sobe em Python311 |

## Bugs corrigidos nesta auditoria

1. Chat «Alfred, estado» devolveva «1 de 1 tarefas» — resumo a partir dos factos das tools.
2. Watchdog pingava `/health` e reiniciava voz com o **venv do engine** (sem faster-whisper).
3. qwen3:8b não ficava residente — keep_alive -1 + warmup.
4. ctx 2048 / cooldown 60s / timeout 30s — subia latência e cortava jobs. Agora ctx 3072, cooldown 8s, timeout 90/120s.
5. Hermes sem `think:false`/`keep_alive` — alinhado ao Alfred.
6. `jarvis/config.yaml` apontava qwen2.5:3b + fallbacks 1B/3B — agora qwen3:8b, fallbacks vazios.
7. Plugin `echo_note.pyc` órfão removido.

## LLMs instaladas (papéis)

Ficheiro: `C:\aura\config\llm_roles.json`

| Modelo | Papel | Carregar |
|---|---|---|
| **qwen3:8b** | cérebro Hermes+Alfred | sempre, GPU, ctx 3072 |
| qwen2.5-coder:7b | código sob AUTORIZO | nunca em paralelo (6 GB) |
| qwen2.5:3b / llama 3.2 3b/1b | proibidos como fallback | nunca auto |

Não se carregam todas ao mesmo tempo: a 4050 tem 6 GB; o 8B já ocupa ~5.3 GiB. «Inteligência no máximo» aqui = **qwen3:8b a 100% da placa**, não um cocktail de modelos.

DeepSeek Harness em `C:\aura\deepseek-harness` é toolkit de código (skills/docs), não um segundo runtime nesta VRAM.

## Agentes

- Manifest `12.7.0-V25O-ALL-ACTIVATED+activated`
- 38 declarados / 31 runnable / 5 inspect_only (assets/UI, não código executável)
- 78 marcadores `agents/ENABLED`
- Análise paper-only reactivada nesta auditoria
- Matriz `activate-all` pode 404 se o proxy não mapear — não é apostas reais

## Como usar

Chat: http://127.0.0.1:8777/chat  
Falar = microfone Windows Realtek. Ficheiro = inbox. Mutável = AUTORIZO.

## O que NÃO foi ligado de propósito

- `execution_allowed` (apostas reais)
- LAN / bind 0.0.0.0
- Segundo LLM na GPU
- Apagar ou mexer em `C:\Windows`
