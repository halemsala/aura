# CornerAI Skill instalada

A skill fornecida pelo usuário foi instalada como camada operacional local do CornerAI.

- Fonte: `CornerAI_v10.2-ELITE-DUAL-SOURCE-WITH-EXPERIENCE-INTEGRATED.skill`
- Runtime: `engine/skill_runtime.py`
- Registro append-only: `engine/artifacts/CornerAI_Log_Analises_Entradas.md` e JSONL
- Memória: `SESSION-STATE.md` e `RECENT_CONTEXT.md`
- Chat: `/api/trader/chat` usa a skill instalada; não depende de Grok.
- Ações interativas: `/api/trader/action`
- Diagnóstico: `/api/skill/status`

A versão declarada dentro do arquivo é preservada exatamente como fornecida.
