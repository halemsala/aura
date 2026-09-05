# AURA Local AIOps

Loop de **Operações Autônomas 100% local**:

```
Você → Agente Ollama → Orchestrator (Harness local) → Neo4j local → Callback
```

Nenhum serviço cloud. Tudo roda na sua máquina.

## Pré-requisitos

- Windows 10/11
- Docker Desktop (rodando)
- Python 3.10+
- Ollama instalado e rodando (`ollama serve`)
- Modelo puxado: `ollama pull llama3.2:3b` (ou outro)

## Ativação com 1 comando

```powershell
cd C:\aura\aura_local_aiops
.\scripts\ATIVAR_TUDO.bat
```

ou

```powershell
.\scripts\ATIVAR_TUDO.ps1
```

O script:
1. Sobe o Neo4j via Docker Compose
2. Instala dependências Python (`neo4j`, `requests`)
3. Inicia o Callback (porta 8090)
4. Inicia o Orchestrator / Harness local (porta 8095)
5. Faz health-check

## Usar o Agente (Ollama)

Em outro terminal:

```powershell
cd C:\aura\aura_local_aiops
python agent\ollama_agent.py
```

Exemplos de perguntas:

```
Crie um nó de teste chamado Demo
Liste quantos nós existem
Apague o nó Demo (com rollback)
```

## Teste manual do Orchestrator

```powershell
python agent\local_tool.py "RETURN 1 AS ok"
python agent\local_tool.py "CREATE (n:Test {name:'local'}) RETURN n"
```

## Portas

| Serviço            | Porta |
|--------------------|-------|
| Neo4j Browser      | 7474  |
| Neo4j Bolt         | 7687  |
| Orchestrator       | 8095  |
| Callback           | 8090  |
| Ollama             | 11434 |

## Parar tudo

```powershell
.\scripts\PARAR_TUDO.ps1
```

## Estrutura

```
aura_local_aiops/
├── docker-compose.yml
├── orchestrator/
│   └── local_orchestrator.py    ← substitui Harness CI/CD
├── agent/
│   ├── ollama_agent.py          ← agente com tool-calling via Ollama
│   ├── local_tool.py            ← chamada direta ao orchestrator
│   └── callback_server.py       ← recebe feedback
├── scripts/
│   ├── ATIVAR_TUDO.bat / .ps1   ← comando único
│   └── PARAR_TUDO.ps1
└── docs/
    └── README.md
```

## Integração com AURA QUANT-X

Se você já usa o AURA QUANT-X (portas 8080/8765/8099), este pacote é independente.
O Orchestrator pode ser chamado por qualquer agente (incluindo o Jarvis do QUANT-X)
via `POST http://127.0.0.1:8095/trigger`.
