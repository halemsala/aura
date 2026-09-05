---
name: aura-governance
version: 1.0.0
description: Aplica Paper Lock, allowlist, menor privilégio, correlação, TTL e aprovação separada para mutações no AURA.
---

# AURA Governance Skill

O `AuraController` é a autoridade. LLMs podem sugerir, resumir e classificar, mas não podem conceder permissões, alterar políticas, publicar, enviar mensagens, apostar, transferir valores ou executar ordens.

Toda capacidade externa deve ser explicitamente allowlisted. Conectores começam em modo read-only. Qualquer mutação exige uma etapa de aprovação humana fora do agente e um registro no ledger canônico. Falhas de schema, auditoria, identidade, frescor ou autorização resultam em `BLOCK`.

Invariantes obrigatórias: `paper_trade=true`, `execution_allowed=false`, `glm_advisory_only=true`, `approved=false`, `stake_pct=0.0` e `exposure=0.0`.
