# Arquitetura de modelos AURA — Qwen + Llama (GLM só na nuvem)

## Diagrama

```
🏠 NOTEBOOK (AURA 24h) — RTX 4050 6GB
│
│   qwen2.5:3b-instruct  →  cérebro principal (chat, tool calls, PT-BR)
│   llama3.2:3b          →  especialista (docs gigantes, instruções longas)
│
│   ≈ 4 GB dos 6 GB  ✅
│
☁️ NUVEM (fora do AURA)
│
│   GLM  →  arquiteto: planos/projetos em chat externo
│           você traz o texto → audita → só então cola no AURA
│           NUNCA carrega no Ollama local
```

## Configuração aplicada

| Item | Valor |
|------|--------|
| `bridge/jarvis/config.yaml` → `llm.model` | `qwen2.5:3b-instruct` |
| `llm.longctx_model` | `llama3.2:3b` |
| `llm.fallback_models` | `llama3.2:3b,qwen2.5:3b,...` (**sem GLM**) |
| `bridge/jarvis/core/llm_router.py` | bloqueia nomes com `glm` |
| Env `AURA_JARVIS_MODEL` / `AURA_LLM_*` | qwen + llama |
| `OLLAMA_MAX_LOADED_MODELS` | `2` |
| `AURA_OLLAMA_KEEP_ALIVE_LONGCTX` | `0` (llama descarrega após uso) |

## Ativação

```bat
AURA_CONFIGURAR_QWEN_LLAMA.bat
:: depois reinicie AURA_START_ALL
```

O BAT:
1. Grava variáveis de ambiente (persistente + sessão)
2. Faz `ollama pull qwen2.5:3b-instruct` e `ollama pull llama3.2:3b`
3. **Não** puxa GLM

## Router — regras

1. Tokens estimados > 24k → `llama3.2:3b`
2. `needs_json` / tool call → `qwen2.5:3b-instruct`
3. Instrução composta (2+ passos) → `llama3.2:3b`
4. Padrão → `qwen2.5:3b-instruct`

Qualquer `force_model` contendo `glm` é rejeitado e cai no qwen.

## Fluxo com GLM (nuvem)

1. Abra o chat GLM **fora** do AURA  
2. Peça o plano/projeto  
3. Traga o texto para auditoria (aqui ou no Hermes)  
4. Só o que passar entra no código/config do AURA  

## O que NÃO fazer

- `ollama pull glm4:...` no notebook do AURA (compete VRAM com qwen+llama)
- Colocar GLM em `fallback_models` ou `AURA_JARVIS_MODEL`
- Rodar dois stacks pesados (trading + 9B) sem Governor

## Verificação rápida

```bat
ollama list
:: deve mostrar qwen2.5:3b-instruct e llama3.2:3b

echo %AURA_JARVIS_MODEL%
:: qwen2.5:3b-instruct
```

No Python (com AURA no path):

```python
from bridge.jarvis.core.llm_router import LLM_ROUTER
print(LLM_ROUTER.describe())
```
