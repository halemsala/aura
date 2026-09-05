# Hermes V10 Ultra — Sistema Autônomo de Diagnóstico e Operação

## 🎯 Visão Geral

O **Hermes V10 Ultra** é um sistema multi-agente autônomo para diagnóstico, correção,
segurança e operação do ecossistema AURA QUANT-X. Construído sobre uma arquitetura
de micro-agentes LLM-powered, com segurança "defense in depth" e observabilidade
de classe mundial.

## 🏛️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES V10 ULTRA                          │
├─────────────────────────────────────────────────────────────┤
│  API Layer        │  FastAPI + WebSocket + JWT Auth         │
│  Dashboard        │  Command Center HTML5 embutido          │
├─────────────────────────────────────────────────────────────┤
│  Agent Layer      │  Diagnostic · Correction · Red Team     │
│                   │  Blue Team · Meta-Agent                 │
├─────────────────────────────────────────────────────────────┤
│  Core Engine      │  LLM Engine (Ollama + OpenAI fallback)  │
│                   │  Constitution Guard · Memory (RAG)      │
│                   │  Digital Twin · Anomaly Detection       │
│                   │  Self-Healing · Alert Manager · MCP     │
├─────────────────────────────────────────────────────────────┤
│  Orchestrator     │  Job queue · Circuit breaker · Retry    │
│                   │  Checkpointing · Human-in-the-loop      │
├─────────────────────────────────────────────────────────────┤
│  Security         │  Hash verification · Permission scan    │
│                   │  Secrets detection · Audit trail        │
├─────────────────────────────────────────────────────────────┤
│  Observability    │  Prometheus metrics · Structured logs   │
│                   │  Health checks · Distributed tracing    │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Clone e Setup
```bash
git clone https://github.com/lunacontrole-del/hermesv10.git
cd hermesv10
pip install -r requirements.txt
```

### 2. Validação
```bash
python scripts/hermes_setup_validator.py --root .
```

### 3. Iniciar
```bash
# Windows
hermes_v10_ultra.bat ultra

# Linux/Mac/Docker
docker-compose up --build -d
```

### 4. Acessar
- **Chat API**: http://localhost:8777/chat
- **Dashboard**: http://localhost:8778/
- **Metrics**: http://localhost:8777/metrics
- **Prometheus**: http://localhost:9090 (se ativado)

## 🔒 Invariantes de Segurança (NUNCA ALTERAR)

| Variável | Valor Obrigatório | Descrição |
|----------|-------------------|-----------|
| `PAPER_TRADE` | `true` | Sempre paper-trade |
| `EXECUTION_ALLOWED` | `false` | Execução real bloqueada |
| `AURA_EXECUTION_ALLOWED` | `0` | Flag interna de execução |
| `AURA_UNLOCK_LIVE` | `0` | Desbloqueio live desativado |

## 🧠 Agentes

### Diagnostic Agent
Diagnóstico completo do sistema com análise LLM + métricas reais.
```bash
python agents/hermes_diagnostic_agent_llm.py --root . --context "API lenta"
```

### Correction Agent
Aplica correções allowlisted com backup automático e rollback.
```bash
python agents/hermes_correction_agent_llm.py --root . --fix domain_lock --confidence 0.95
```

### Red Team Agent
Ataque controlado para encontrar vulnerabilidades.
```bash
python agents/hermes_red_team_agent_llm.py --root .
```

### Blue Team Agent
Defesa ativa e hardening do sistema.
```bash
python agents/hermes_blue_team_agent_llm.py --root . --harden
```

### Meta Agent
Orquestração inteligente e meta-aprendizado.
```bash
python agents/hermes_meta_agent_llm.py --root . --objective "otimizar saúde"
```

## 🧪 Testes

```bash
pytest tests/test_integration.py -v --tb=short
```

## 📊 Observabilidade

- **Prometheus**: Métricas de requests, latência, memória
- **Logs estruturados**: `structlog` em todos os módulos
- **Audit trail**: Imutável em `logs_supervisor/security_audit.log`
- **Anomaly DB**: SQLite com histórico de anomalias
- **Alertas**: Webhook, Discord, arquivo (configurável via env vars)

## 🐳 Docker

```bash
docker-compose up --build -d
```

Serviços:
- `hermes-api`: API principal (porta 8777)
- `redis`: Cache e filas (porta 6379)
- `ollama`: LLM local (porta 11434)
- `prometheus`: Métricas (porta 9090)

## 🔧 Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AURA_ROOT` | `.` | Diretório raiz do sistema |
| `HERMES_API_PORT` | `8777` | Porta da API |
| `HERMES_DASHBOARD_PORT` | `8778` | Porta do dashboard |
| `OLLAMA_HOST` | `http://localhost:11434` | Endpoint Ollama |
| `OLLAMA_MODEL` | `llama3.2:3b` | Modelo padrão |
| `OPENAI_API_KEY` | — | Chave OpenAI (fallback) |
| `HERMES_JWT_SECRET` | `auto` | Segredo para auth |
| `HERMES_ALERT_WEBHOOK` | — | URL para alertas |
| `HERMES_DISCORD_WEBHOOK` | — | URL Discord |

## 🛡️ Segurança

- **Constitution Engine**: Regex + semantic analysis para bloquear comandos perigosos
- **Digital Twin**: Simula mudanças antes de aplicar
- **Self-Healing**: Auto-correção com cooldown, limites e rollback
- **Circuit Breaker**: Evita cascata de falhas
- **Rate Limiting**: 60 req/min por IP
- **Path Traversal**: Bloqueado em todas as operações de filesystem
- **Secret Scanning**: Detecção de keys hardcoded
- **Hash Verification**: SHA256 de arquivos críticos

## 📈 Roadmap

- [ ] Integração com LangGraph para workflows complexos
- [ ] Suporte a múltiplos modelos simultâneos (ensemble)
- [ ] Fine-tuning contínuo com feedback humano (RLHF)
- [ ] Integração com exchanges via MCP (read-only)
- [ ] Dashboard em React com gráficos em tempo real

## 📄 Licença

Proprietário — AURA QUANT-X Systems

---

**Hermes V10 Ultra** — *Autonomous Diagnostic OS*
```
