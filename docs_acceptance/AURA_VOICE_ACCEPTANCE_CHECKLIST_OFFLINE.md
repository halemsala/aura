# Checklist de Testes de Aceite — Voice / VoiceProvider (AURA Hermes)

**Versão:** 1.0.0  
**Data:** 2026-08-30  
**Modo:** offline / paper-only / fail-closed  
**Escopo:** segurança · privacidade · fallback · proveniência  
**Autoridade:** InvariantGate + PolicyGate + AuditLedger  
**Pacote de referência:** AURA_QUANT_X_HERMES_INTEGRADO (AURA_VOZ_STACK_COMPLETO)

> **Regras absolutas**
> - Nenhuma instalação, rede, microfone, GPU pre-warm, MCP ou mutação de flags é permitida.
> - Todos os testes são estáticos ou com mocks locais.
> - Qualquer FAIL em teste bloqueante → status permanece `AGUARDA`.
> - Em caso de dúvida → rejeitar (fail-closed).

---

## Pré-condições obrigatórias (P0)

| ID     | Critério                                                                 | Como verificar offline                                      | Resultado esperado                                      | Bloqueante | Pass/Fail | Notas |
|--------|--------------------------------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------------|------------|-----------|-------|
| PRE-01 | `paper_trade=True` e `execution_allowed=False`                           | Ler env / config / invariant_gate                           | Ambos verdadeiros; qualquer True em execution → FAIL    | Sim        |           |       |
| PRE-02 | Nenhum processo Engine/Bridge/Voice/Ollama ativo                         | netstat / tasklist / portas 8765/8080/8099                  | Portas livres; nenhum processo AURA                     | Sim        |           |       |
| PRE-03 | Compilação estática dos módulos de voz                                   | `python -m compileall` em bridge/, engine/, scripts/        | Exit code 0, zero erros de sintaxe                      | Sim        |           |       |
| PRE-04 | Schema ToolManifest / contrato VoiceProvider presente e fechado          | Inspecionar definição (Pydantic/Zod/dataclass)              | Campos obrigatórios listados; sem **kwargs ou livres    | Sim        |           |       |
| PRE-05 | Ledger e sanitizer disponíveis (mesmo que mock)                          | Import + instanciação dry-run                               | Objetos criados sem side-effect                         | Sim        |           |       |

---

## 1. Segurança (Security)

| ID     | Critério de aceite                                                                 | Procedimento offline                                                                 | Pass/Fail | Notas |
|--------|------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|-----------|-------|
| SEC-01 | Chamada de voz **nunca** altera paper_trade, execution_allowed, approved, stake_pct, exposure | Injetar request válido + request malicioso; inspecionar estado após                 |           |       |
| SEC-02 | Campos desconhecidos, tipos inválidos ou caminhos arbitrários são rejeitados       | Payload com extra_field, path=../../etc/passwd, cmd=..., tipo errado                 |           |       |
| SEC-03 | Texto com tokens, secrets, comandos ou injeção é bloqueado pelo sanitizer          | Inputs: "Bearer xyz", "rm -rf /", "execute order", PII sintética                     |           |       |
| SEC-04 | Motor / adaptador **não** recebe texto cru                                         | Interceptar chamada ao provider (mock)                                               |           |       |
| SEC-05 | Side-effects limitados a write_local_audio_artifact (temporário)                   | Após render, listar arquivos criados                                                 |           |       |
| SEC-06 | Timeout e cancelamento funcionam                                                   | Request com max_duration_s=1 + cancel após 200 ms                                    |           |       |
| SEC-07 | Fila tem limite rígido (max_queue)                                                 | Enfileirar N+1 requests                                                              |           |       |
| SEC-08 | Nenhuma ferramenta de envio/publicação/execução é exposta                          | Inspecionar manifest da ferramenta aura_voice_render_local                           |           |       |
| SEC-09 | MCP / REST ampla desabilitados por padrão                                          | Verificar feature flags e allowlist                                                  |           |       |
| SEC-10 | Reload / auto-recovery não reinicia silenciosamente                                | Forçar falha de motor                                                                |           |       |

---

## 2. Privacidade (Privacy)

| ID     | Critério de aceite                                                                 | Procedimento offline                                                                 | Pass/Fail | Notas |
|--------|------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|-----------|-------|
| PRI-01 | Áudio bruto **nunca** entra no AuditLedger                                         | Gerar áudio + inspecionar entradas do ledger                                         |           |       |
| PRI-02 | Texto original / tokens / cookies / PII não aparecem em logs nem ledger            | Buscar strings sensíveis nos artefatos de log                                        |           |       |
| PRI-03 | Captura de áudio é opt-in e exige consent_ref                                      | Request sem consent_ref e com consent_ref inválido                                   |           |       |
| PRI-04 | Exclusão de captura é completa e verificável                                       | Criar captura → chamar delete → verificar filesystem + ledger                        |           |       |
| PRI-05 | Retenção configurável e respeitada                                                 | Definir TTL curto; esperar + verificar                                               |           |       |
| PRI-06 | Clonagem de voz exige consentimento explícito                                      | Request de clone sem consent_ref                                                     |           |       |
| PRI-07 | Nenhum upload automático de áudio ou referência                                    | Mock de rede + request de geração                                                    |           |       |
| PRI-08 | Microfone / ditado global desligados por padrão                                    | Verificar flags e permissões                                                         |           |       |

---

## 3. Fallback e Resiliência

| ID     | Critério de aceite                                                                 | Procedimento offline                                                                 | Pass/Fail | Notas |
|--------|------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|-----------|-------|
| FAL-01 | Falha do motor primário (ex.: XTTS) retorna ao motor autorizado ou AGUARDA         | Mock de falha no provider primário                                                   |           |       |
| FAL-02 | Fallback FAST (SpeechSynthesis / navegador) permanece disponível                   | Desabilitar todos os motores locais                                                  |           |       |
| FAL-03 | Falha de Voicebox (se presente) **nunca** eleva privilégio nem executa código      | Simular exception no adaptador opcional                                              |           |       |
| FAL-04 | Texto inválido / vazio / excessivo é rejeitado antes do motor                      | Inputs: "", 100k chars, caracteres de controle                                       |           |       |
| FAL-05 | Concorrência não disputa GPU sem controle                                          | Dois requests simultâneos com limite=1                                               |           |       |
| FAL-06 | Circuit breaker / timeout global funciona                                          | Forçar latência artificial > limite                                                  |           |       |
| FAL-07 | Estado de UI / status é observável e consistente                                   | Após cada request, ler status                                                        |           |       |

---

## 4. Proveniência e Auditoria

| ID     | Critério de aceite                                                                 | Procedimento offline                                                                 | Pass/Fail | Notas |
|--------|------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|-----------|-------|
| PRO-01 | Cada artefato de áudio possui metadata completa                                    | Após render, inspecionar sidecar / registro                                          |           |       |
| PRO-02 | text_hash corresponde ao texto sanitizado                                          | Calcular hash localmente e comparar                                                  |           |       |
| PRO-03 | artifact_hash é verificável                                                        | Recalcular hash do arquivo de áudio                                                  |           |       |
| PRO-04 | Eventos de auditoria são emitidos na ordem correta                                 | Capturar sequência                                                                   |           |       |
| PRO-05 | Ledger é hash-chained e não permite alteração silenciosa                           | Gerar 3 eventos → verificar cadeia                                                   |           |       |
| PRO-06 | Decisão de política é registrada (allow / deny / fallback)                         | Requests permitidos e bloqueados                                                     |           |       |
| PRO-07 | Versão do motor / Skill / contrato é registrada                                    | Inspecionar metadata                                                                 |           |       |
| PRO-08 | Dry-run não produz artefato de áudio                                               | Request com dry_run=true                                                             |           |       |

**Campos mínimos exigidos em PRO-01:**  
`request_id`, `correlation_id`, `text_hash`, `engine_used`, `model_version`, `profile_id`, `duration_ms`, `artifact_hash`, `policy_decision`, `timestamp`, `fallback_used`

**Sequência mínima de eventos (PRO-04):**  
`voice.requested` → `voice.policy_checked` → `voice.rendered` | `voice.failed`

---

## 5. Matriz de execução rápida (Smoke Offline)

Execute **nesta ordem**. Todos devem passar antes de qualquer P1/P2:

1. PRE-01 → PRE-05  
2. SEC-01, SEC-02, SEC-03, SEC-05  
3. PRI-01, PRI-02  
4. FAL-01, FAL-02, FAL-04  
5. PRO-01, PRO-04, PRO-08  

**Critério de promoção:** 100 % dos testes bloqueantes (PRE + SEC-01/02/03 + PRI-01/02 + FAL-01/04 + PRO-01/04) em PASS.  
Qualquer FAIL → status permanece `AGUARDA`; não se ativa feature flag nem se promove adaptador.

---

## 6. Registo de execução

| Campo                    | Valor                          |
|--------------------------|--------------------------------|
| Data/hora execução       |                                |
| Operador                 |                                |
| Versão pacote AURA       |                                |
| Hash commit / build      |                                |
| Ambiente (OS / Python)   |                                |
| Resultado global         | PASS / FAIL / AGUARDA          |
| Testes bloqueantes FAIL  | (listar IDs)                   |
| Observações              |                                |

---

## 7. Observações de execução

- Todos os testes são **estáticos ou com mocks locais**.
- Nenhum teste deve abrir porta, carregar modelo grande, aceder microfone ou rede.
- Resultados devem ser registados com `request_id` / `correlation_id` e versão do pacote.
- Em caso de dúvida sobre um campo, o valor padrão seguro é **rejeitar** (fail-closed).
- Este checklist pode ser convertido em suite pytest com mocks sem alterar o núcleo do AURA.

---

**Fim do checklist.**  
Status recomendado após execução bem-sucedida dos bloqueantes: pronto para definir contrato `VoiceProvider` (P1) em modo advisory.
