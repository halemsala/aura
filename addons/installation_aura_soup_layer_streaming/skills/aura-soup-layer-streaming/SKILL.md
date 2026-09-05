---
name: aura-soup-layer-streaming
description: Avalia planos de fine-tuning local com layer streaming, memória limitada e quantização, sem executar modelos ou treinamento.
---

# AURA Soup Layer Streaming

Use esta Skill quando o usuário quiser avaliar fine-tuning local de LLMs em GPU limitada ou transformar uma configuração Soup em um plano seguro para o AURA.

## Regras

1. Trate `Soup` como dependência externa opcional; não instale `soup-cli`, PyTorch, CUDA, modelos ou drivers automaticamente.
2. Exija uma configuração explícita com `base`, `task`, `data` e `training`.
3. Aceite `stream_layers` apenas como hipótese beta; não prometa desempenho, VRAM ou tokens/segundo sem benchmark no hardware real.
4. Diferencie memória de pesos, ativações, logits, batch e comprimento de sequência.
5. Gere apenas um plano advisory com fingerprint; `execution_allowed` permanece falso.
6. Para ativação futura, exigir cópia do projeto, ambiente isolado, benchmark, teste de equivalência, limite de VRAM, timeout, logs e rollback.
7. Nunca baixar modelos, acessar contas, enviar dados para a rede ou publicar resultados durante a análise.

## Saída obrigatória

A resposta deve separar: configuração recebida; suposições; riscos; evidências; warnings; pré-requisitos; plano de benchmark; decisão `ADVISORY`, `AGUARDA` ou `BLOCK`; fingerprint; e confirmação de que nenhuma execução ocorreu.
