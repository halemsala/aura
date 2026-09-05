---
name: aura-ingestion
version: 1.0.0
description: Normaliza snapshots do AURA, preserva ausências como N/D e exige proveniência e frescor antes de qualquer análise.
---

# AURA Ingestion Skill

Aceite somente snapshots estruturados do host. Não invente placar, odds, eventos, times, fontes ou horários. Campos ausentes permanecem ausentes. Rejeite dados com tipos inválidos, timestamps impossíveis, fontes vazias ou payload acima do limite definido pelo host.

A Skill não acessa rede, não lê credenciais e não chama ferramentas. Sua saída é um snapshot validado para o `AuraController`.
