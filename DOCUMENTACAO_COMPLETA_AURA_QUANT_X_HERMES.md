# DOCUMENTAÇÃO COMPLETA — AURA QUANT-X HERMES

**Produto:** AURA QUANT-X  
**Versão do pacote:** 12.7.62 — V37.3.29 VOZ XTTS / TORCHCODEC-STUB  
**Modo:** paper-trade only · fail-closed · GLM advisory-only  
**Data desta documentação:** 2026-08-30  

---

## 1. Visão geral

O **AURA QUANT-X** é um sistema autónomo de análise quantitativa de **escanteios** (corners) em futebol. Opera exclusivamente em modo **paper-trade**: nunca envia ordens reais, nunca altera exposição real e nunca desbloqueia execução sem intervenção humana explícita e fora do agente.

### Propósito

- Ingerir feed de eventos de escanteio (SokkerPro / CornerAI via Bridge).
- Analisar contexto, pressão, odds, fase de jogo e padrões.
- Produzir decisões **advisory** (ENTRA / AGUARDA / BLOQUEADO) com evidências.
- Expor estado via API, Matriz UI, Hermes Chat e Voice (Jarvis).
- Manter auditoria, políticas e invariantes de segurança.

### Princípios de desenho

| Princípio | Significado |
|-----------|-------------|
| Paper Lock | `paper_trade=true` e `execution_allowed=false` são imutáveis no runtime normal |
| Fail-closed | Qualquer dúvida, falta de dados ou violação de schema → bloqueio / AGUARDA |
| Menor privilégio | Ferramentas e conectores começam read-only; mutações exigem aprovação humana |
| Advisory LLM | GLM / Ollama sugerem; nunca concedem permissão nem executam |
| Proveniência | Tudo que entra e sai deve ter origem, hash e decisão de política registada |
| Local-first | Preferência por execução local; rede e microfone são opt-in |

---

## 2. Invariantes de segurança (nunca alterar)

```text
paper_trade          = true
execution_allowed    = false
approved             = false
stake_pct            = 0.0
exposure             = 0.0
glm_advisory_only    = true
AURA_UNLOCK_LIVE     = 0
AURA_PAPER_ONLY      = 1
```

- O `ExecutionRouter` e o `InvariantGate` rejeitam qualquer pedido que tente contornar estas flags.
- O Bridge exige token para rotas sensíveis.
- Módulos de Telegram, WebSocket amplo, STT real contínuo, captura browser stealth, GPU pre-warm e APIs externas permanecem **inertes por defeito**.

---

## 3. Arquitetura de serviços

| Serviço | Porta | Função principal | Health |
|---------|-------|------------------|--------|
| **Bridge** | `127.0.0.1:8080` | Ingestão de feed CornerAI / SokkerPro, skill-feed, status | `GET /health` |
| **Engine** | `127.0.0.1:8765` | Análise, agentes, risk gates, council, UI state, diagnostics | `GET /api/health` |
| **Voice / Jarvis** | `127.0.0.1:8099` | STT (Whisper), TTS (XTTS / Edge / Piper), streaming por frase | `GET /api/voice/health` |
| **Matriz UI** | `127.0.0.1:8766` | Interface oficial (desktop/ui/matriz_v22) | `http://127.0.0.1:8766/index.html` |
| **Hermes Chat** | `127.0.0.1:8777` | Chat supervisory / Hermes V10 | `http://127.0.0.1:8777/chat` |
| **Hermes Dash** | `127.0.0.1:8778` | Dashboard Hermes (opcional) | — |
| **Ollama** | `127.0.0.1:11434` | LLM local (ex.: glm4:9b-chat-q4_0) — **nunca morto pelo instalador** | `GET /api/tags` |

### Fluxo de dados (voz)

```
Microfone (opt-in) → VAD → WAV → /api/voice/talk
  → Whisper/STT → LLM local (advisory)
  → resposta por frase → XTTS/TTS (ou Edge/Piper/fallback)
  → reprodução + metadata no ledger (redigido)
```

### Fluxo de dados (análise)

```
SokkerPro / feed → Bridge :8080 → Engine :8765
  → risk gates + council + agentes
  → decisão advisory + evidências
  → Matriz / Hermes / Voice (somente renderização)
```

---

## 4. Estrutura de pastas (raiz do pacote)

```
AURA_QUANT_X_HERMES_INTEGRADO/
├── INSTALAR_TUDO.bat              ← instalação limpa completa (admin)
├── AURA_START_ALL.bat             ← arranque diário
├── LIMPEZA_COMPLETA.bat           ← liberta portas AURA (não mata Ollama)
├── CHECK.bat                      ← verificação de ficheiros + health
├── LEIA-ME_PRIMEIRO.txt           ← ponto de entrada rápido
├── LEIA-ME_VOZ_ACCEPTANCE_E_INSTALACAO.txt
├── AURA_VOICE_ACCEPTANCE_CHECKLIST_OFFLINE.md
├── MANUAL_SISTEMA_AURA.txt
├── PACKAGE_MANIFEST_AUTHORIZED.md
├── VERSION
├── allowlist.json
├── pyproject.toml
├── requirements.txt
│
├── engine/                        ← núcleo de análise e risk
├── bridge/                        ← ingestão + Jarvis Voice
├── agents/                        ← agentes + ENABLED/
├── hermes_v10/                    ← supervisor / chat Hermes
├── desktop/                       ← UI Desktop (C#) + matriz
├── scripts/                       ← BATs, PS1, Python de ops
├── config/                        ← env, schemas, allowlist
├── core/                          ← risk + voice core
├── skills/                        ← Skills AURA (governance, ingestion, …)
├── voice_profiles/                ← perfis de voz / prompts
├── docs/ · docs_fonte/ · docs_acceptance/
├── patches/ · legacy_bats/ · _interno/
├── tests/ · tools/ · templates/ · knowledge/
└── addons/ · extensao/ · interface/ · ops/
```

---

## 5. Instalação limpa (Windows)

### Pré-requisitos

- Windows 10/11
- Python 3.11 (recomendado) — `py -3.11 --version`
- Extração do ZIP completo (pasta com `engine\server.py` e `bridge\server.py`)
- Executar BATs como **Administrador** quando indicado

### Sequência oficial (um comando)

1. Extrair o ZIP.
2. Clique direito em **`INSTALAR_TUDO.bat`** → **Executar como administrador**.

O instalador:

1. Copia o pacote para `C:\aura` (preserva `engine\venv` se existir).
2. Corre **LIMPEZA COMPLETA** (liberta portas AURA; **não** mata Ollama :11434).
3. Instala dependências e prepara venv.
4. Corre **CHECK**.
5. Sobe serviços (Bridge, Engine, Voice, Hermes, Matriz).
6. Corre CHECK final + Desktop/Matriz.

**Alternativas one-shot**

| BAT | Uso |
|-----|-----|
| `AURA_TUDO_EM_UM.bat` | Instalação + serviços num fluxo |
| `AURA_LIMPEZA_E_INSTALACAO_COMPLETA.bat` | Limpeza + instalação |
| `AURA_LIMPA_E_INSTALA.bat` | Variante curta |

**Forçar recriação de venv:**  
`INSTALAR_TUDO.bat /FORCE`

### Destino padrão

```
C:\aura
```

Após a primeira instalação, o dia a dia usa `C:\aura\AURA_START_ALL.bat`.

---

## 6. Operação diária

| Ação | Comando |
|------|---------|
| Arranque completo | `AURA_START_ALL.bat` ou `START.bat` |
| Só Engine | `START_ENGINE.bat` |
| Só Bridge | `START_BRIDGE.bat` |
| Só UI / Matriz | `START_UI.bat` / `AURA_ABRIR_DESKTOP.bat` |
| Verificação | `CHECK.bat` |
| Limpeza de portas | `LIMPEZA_COMPLETA.bat` |
| Auditoria | `AURA_AUDITORIA_COMPLETA.bat` |

### Health checks (browser ou curl)

```
http://127.0.0.1:8080/health
http://127.0.0.1:8765/api/health
http://127.0.0.1:8765/api/status
http://127.0.0.1:8765/api/ui/state
http://127.0.0.1:8765/api/diagnostics/deep
http://127.0.0.1:8099/api/voice/health
http://127.0.0.1:8766/index.html
http://127.0.0.1:8777/chat
```

Ordem de debug recomendada:

1. Portas em LISTEN?
2. `ui/state` tem `view.home` e `corner_events`?
3. `paper_trade: true` e `execution_allowed: false`?
4. Voice build esperado (AURA-VOICE / XTTS)?
5. Só então mexer em código.

---

## 7. Camada de voz (Jarvis / Voice 8099)

### Capacidades atuais

- **STT:** Whisper / faster-whisper (pipeline local).
- **TTS:** XTTS (voz de referência), Edge-TTS (AntonioNeural etc.), Piper (opcional).
- **Fallback:** SpeechSynthesis do navegador (modo FAST).
- **Streaming por frase**, sanitização de texto, sessões isoladas, diagnóstico e reload controlado.
- **VAD** no caminho de entrada.

### BATs de voz

| BAT | Função |
|-----|--------|
| `AURA_INSTALAR_VOZ.bat` | Instala dependências de voz |
| `AURA_INSTALAR_TESTAR_VOZ_COMPLETO.bat` | Instala + testa + sobe stack |
| `AURA_INSTALAR_VOZ_NATURAL_AGORA.bat` | Perfil natural |
| `AURA_REPARAR_XTTS_TORCHCODEC.bat` | Repara incompatibilidade torchcodec / transformers |
| `AURA_ATIVAR_XTTS_REFERENCIA.bat` | Ativa voz de referência (WAV) |
| `AURA_TESTAR_PIPER.bat` | Teste Piper PT-BR |

### Notas técnicas (V37.3.28+)

- Compat shim: `scripts/aura_xtts_compat.py` (isin_mps_friendly + torchaudio via soundfile).
- Pin recomendado: coqui-tts 0.27.x + transformers ≥4.57.1,<5 + tokenizers 0.22–0.23.
- Edge disponível: AntonioNeural, FranciscaNeural, ThalitaMultilingualNeural (região dependente).
- Clonagem de voz = apenas via XTTS + ficheiro de referência; exige consentimento.
- 1.ª síntese XTTS pode demorar (download de pesos + carga GPU/CPU).

### Voicebox (jamiepine/voicebox)

**Status: ADVISORY apenas.**  
Não instalar no núcleo. Usar só como referência de contrato `VoiceProvider` (multi-engine, fila, capturas, efeitos). Qualquer integração futura deve passar por `ToolManifest` + `PolicyGate` + `AuditLedger` e permanecer opt-in / sandbox.

Checklist offline: `AURA_VOICE_ACCEPTANCE_CHECKLIST_OFFLINE.md`.

---

## 8. Control plane e governança

### Componentes-chave

| Componente | Papel |
|------------|--------|
| `ToolManifest` | Schema fechado de ferramentas (nome, versão, input/output, side-effects, timeout, aprovação) |
| `PolicyGate` | Rejeita campos fora do schema, agentes não autorizados, modos incompatíveis, live-order |
| `InvariantGate` | Autoridade do Paper Lock; bloqueia violações de invariantes |
| `AuditLedger` | Hash-chained; metadados redigidos (sem áudio bruto nem tokens) |
| `ExecutionRouter` | Hard gate adicional; força PAPER_BLOCKED quando paper ou !execution_allowed |
| `AuraController` | Autoridade central; LLMs só sugerem |

### Skills (pasta `skills/`)

Incluem (entre outras):

- `aura-governance` — Paper Lock, allowlist, menor privilégio, TTL, aprovação separada  
- `aura-ingestion` — Normalização de snapshots; ausências = N/D; exige proveniência  
- `aura-hermes-review` — Revisão de propostas (ADVISORY / AGUARDA / BLOCK)  
- `aura-explanation` — Explicações PT-BR com evidências, limitações e confiança  
- `aura-quant-x` — Operação, instalação, diagnóstico e correção do sistema  
- `aura-policy-guard`, `aura-ops-supervisor`, `aura-evidence`, etc.

### Allowlist

`allowlist.json` / `config/allowlist.json` restringe o que pode ser patchado in-place. Qualquer mutação fora da allowlist é rejeitada.

---

## 9. Engine — módulos principais

- `engine/server.py` — API FastAPI (health, status, ui/state, diagnostics, telemetry, council…)
- `engine/execution_router.py` — Hard gate de execução (paper only)
- `engine/aura_controller.py` — Controlador central
- `engine/drift_monitor.py` — Drift / variância
- `engine/data_veracity.py` — Veracidade de dados
- `engine/digital_twin_monte_carlo.py` — Simulação
- `engine/corner_intelligence.py` — Inteligência de escanteios
- `engine/agents/hermes_supervisor_agent.py` — Supervisor Hermes
- `engine/agents/war_council.py` — Conselho de Guerra (Crew local + Elo + Red Team)
- `engine/core/` — hardware_governor, policy_runtime, state_snapshot, alert_rate_limiter, …
- `engine/voice_planner.py` — Planeamento de voz

Agentes habilitados: lista em `agents/ENABLED/*.enabled`.

---

## 10. Bridge — módulos principais

- `bridge/server.py` — HTTP Bridge (feed, skill-feed, health, status) — **obrigatório `do_GET`**
- `bridge/jarvis_voice_server.py` — Servidor de voz :8099
- `bridge/jarvis/` — módulos TTS, config, memory, governor, security
- `bridge/cognitive/voice_command_router.py` — Classificação segura de comandos de voz
- `bridge/cognitive/streaming_voice_pipeline.py` — Pipeline de streaming
- `bridge/voice_preflight.py` — Preflight de voz
- `bridge/diagnostico_gpu_voice.py` — Diagnóstico GPU/voz
- Requirements de voz: `bridge/requirements_voice*.txt`

---

## 11. Desktop e Matriz UI

- Projeto C#: `desktop/Aura.Desktop.csproj`, `MainForm.cs`, `BrowserHost.cs`, …
- UI oficial: `desktop/ui/matriz_v22/` (servida em :8766)
- Se o EXE Desktop não existir, o arranque abre o browser na Matriz (não aborta).

---

## 12. Hermes V10

- Pasta `hermes_v10/` (agents, core, dashboard, docker-compose opcional)
- Chat: `http://127.0.0.1:8777/chat`
- BATs: `AURA_HERMES_V10_ULTRA.bat`, `hermes_v10/hermes_v10_ultra.bat`, …
- Supervisor: `engine.agents.hermes_supervisor_agent`

---

## 13. Catálogo de BATs (raiz)

### Instalação e limpeza

| Ficheiro | Função |
|----------|--------|
| `INSTALAR_TUDO.bat` | Instalação limpa completa (admin) |
| `AURA_LIMPEZA_E_INSTALACAO_COMPLETA.bat` | Limpeza + instalação |
| `AURA_TUDO_EM_UM.bat` | One-shot instalação + serviços |
| `AURA_LIMPA_E_INSTALA.bat` | Variante curta |
| `LIMPEZA_COMPLETA.bat` | Liberta portas AURA (não mata Ollama) |
| `LIMPEZA_CORE.bat` | Limpeza core |
| `AURA_LIMPEZA_AGRESSIVA.bat` | Limpeza agressiva |

### Arranque e UI

| Ficheiro | Função |
|----------|--------|
| `AURA_START_ALL.bat` | Arranque completo diário |
| `START.bat` | Arranque genérico |
| `START_ENGINE.bat` | Só Engine |
| `START_BRIDGE.bat` | Só Bridge |
| `START_UI.bat` | UI |
| `AURA_ABRIR_DESKTOP.bat` | Desktop / Matriz |
| `ABRIR.bat` / `ABRIR_MATRIZ.bat` / `ABRIR_INTERFACE_CORNERAI.bat` | Atalhos de UI |
| `COMPILAR_E_ABRIR_DESKTOP.bat` | Compilar + abrir Desktop |

### Voz

| Ficheiro | Função |
|----------|--------|
| `AURA_INSTALAR_VOZ.bat` | Deps de voz |
| `AURA_INSTALAR_TESTAR_VOZ_COMPLETO.bat` | Instalar + testar + subir |
| `AURA_INSTALAR_VOZ_NATURAL_AGORA.bat` | Perfil natural |
| `AURA_REPARAR_XTTS_TORCHCODEC.bat` | Reparo XTTS/torchcodec |
| `AURA_ATIVAR_XTTS_REFERENCIA.bat` | Voz de referência |
| `AURA_TESTAR_PIPER.bat` | Teste Piper |

### Check e auditoria

| Ficheiro | Função |
|----------|--------|
| `CHECK.bat` | Ficheiros + portas + health |
| `AURA_AUDITORIA_COMPLETA.bat` | Auditoria |
| `AURA_INSTALAR_TESTAR_RELATORIO_GERAL.bat` | Relatório geral |
| `AURA_ENGINE_FOREGROUND.bat` | Engine em foreground |

### Hermes / assistente

| Ficheiro | Função |
|----------|--------|
| `AURA_HERMES_V10_ULTRA.bat` | Hermes V10 ultra |
| `AURA_SOBE_HERMES_SO.bat` | Sobe Hermes |
| `AURA_ASSISTENTE_COMPLETO.bat` | Assistente completo |
| `AURA_ATIVAR_ASSISTENTE_WINDOWS.bat` | Assistente Windows |

Há BATs legados adicionais em `legacy_bats/` e scripts em `scripts/` (`.bat`, `.ps1`, `.py`).

---

## 14. Portas — resumo e limpeza

| Porta | Serviço | Limpeza pelo AURA? |
|-------|---------|--------------------|
| 8080 | Bridge | Sim |
| 8765 | Engine | Sim |
| 8766 | Matriz | Sim |
| 8099 | Voice | Sim |
| 8777 | Hermes Chat | **Não** (preservado em limpeza padrão) |
| 8778 | Hermes Dash | — |
| 11434 | Ollama | **Nunca** |

`LIMPEZA_COMPLETA.bat` usa `scripts/AURA_SAFE_FREE_PORTS.ps1` (ou fallback netstat) e **não** mata Ollama.

---

## 15. Testes de aceite de voz (offline)

Ver ficheiro: **`AURA_VOICE_ACCEPTANCE_CHECKLIST_OFFLINE.md`**

Cobertura:

- Pré-condições (Paper Lock, portas livres, compileall, schema)
- Segurança (não alterar flags, schema fechado, sanitizer, side-effects limitados)
- Privacidade (áudio bruto fora do ledger, consent_ref, exclusão)
- Fallback (motor primário → fallback → AGUARDA)
- Proveniência (hashes, eventos de auditoria, dry-run)

Critério de promoção: 100 % dos testes bloqueantes em PASS.

---

## 16. Troubleshooting rápido

| Sintoma | Ação |
|---------|------|
| Bridge GET = 501 | Garantir `do_GET` em `bridge/server.py` |
| Portas ocupadas | `LIMPEZA_COMPLETA.bat` |
| Voz / XTTS falha (torchcodec) | `AURA_REPARAR_XTTS_TORCHCODEC.bat` |
| venv corrompido | `INSTALAR_TUDO.bat /FORCE` |
| Ollama offline | Não é morto pelo AURA; verificar serviço Ollama e `ollama pull` do modelo |
| Capture stale | Aba SokkerPro inativa (>45 s) — não reinstalar |
| `BLOCKED_BY_DATA` / HOLD | Comportamento fail-closed esperado; não “sistema morto” |
| Python não no PATH | Usar `py -3.11`; instalador tenta descoberta automática |

Logs úteis:

- `logs_supervisor\INSTALAR_TUDO.log`
- `bridge\runtime_bridge.log` (quando presente)
- Output de `CHECK.bat` e `AURA_AUDITORIA_COMPLETA.bat`

---

## 17. O que NÃO fazer

- Não definir `execution_allowed=True` nem `AURA_UNLOCK_LIVE=1` em operação normal.
- Não instalar Voicebox (ou qualquer stack de voz externa) no núcleo.
- Não ligar MCP/REST ampla de voz sem ToolManifest + PolicyGate + aprovação.
- Não ativar ditado global / microfone contínuo sem opt-in explícito e consentimento.
- Não matar manualmente o processo Ollama (:11434) via scripts do AURA.
- Não colar dois comandos BAT na mesma linha (ex.: `AURA_ABRIR_DESKTOP.batcd C:\aura`).
- Não importar Skills externas com capacidade de mutação/execução por prompt livre.

---

## 18. Referências internas do pacote

| Documento | Conteúdo |
|-----------|----------|
| `LEIA-ME_PRIMEIRO.txt` | Instalação e portas em 1 página |
| `LEIA-ME_INSTALACAO_RAPIDA.md` | Fluxo rápido C:\aura |
| `LEIA-ME_VOZ_E_STACK.txt` | Voz XTTS / reparos |
| `LEIA-ME_VOZ_ACCEPTANCE_E_INSTALACAO.txt` | Guia voz + acceptance |
| `MANUAL_SISTEMA_AURA.txt` | Changelog local + invariantes |
| `PACKAGE_MANIFEST_AUTHORIZED.md` | Componentes autorizados e o que está inerte |
| `CHANGELOG_V37.3.27_VOZ_XTTS.txt` (e adjacentes) | Histórico de correções de voz |
| `AURA_VOICE_ACCEPTANCE_CHECKLIST_OFFLINE.md` | Checklist de aceite offline |
| `docs/` · `docs_fonte/` · `docs_acceptance/` | Documentação adicional |

---

## 19. Resumo executivo para o operador

1. **Extrair** o ZIP completo.  
2. **Instalar** com `INSTALAR_TUDO.bat` (admin) → destino `C:\aura`.  
3. **Dia a dia:** `AURA_START_ALL.bat`.  
4. **Verificar:** `CHECK.bat` + health URLs.  
5. **Voz:** reparar com `AURA_REPARAR_XTTS_TORCHCODEC.bat` se necessário; testar com os BATs de voz.  
6. **Nunca** desbloquear execução real nem instalar Voicebox no núcleo.  
7. Qualquer alteração de política ou ferramenta passa por allowlist, PolicyGate e aprovação humana.

---

**Fim da documentação completa.**  
Sistema paper-only · fail-closed · local-first · advisory LLM.
