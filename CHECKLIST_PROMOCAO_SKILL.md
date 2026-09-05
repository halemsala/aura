# Checklist operacional — instalar e promover skill no AURA Harness

Política fixa: **paper trade ativo · execução real bloqueada · nada é instalado pelo modelo**.  
Toda mutação exige o texto exato `CONFIRMAR …`.

Use o harness consolidado: `AURA_HARNESS_UNICO_CONSOLIDADO.py` (ou o audited).

---

## Pré-requisitos

- [ ] Python 3.10+ com o arquivo do harness
- [ ] `AURA_ROOT` aponta para a raiz real do projeto (padrão `C:\aura` no Windows)
- [ ] Opcional: Ollama em `127.0.0.1:11434` (só para chat/sugestões; instalação de skill **não** depende dele)
- [ ] Self-test verde:

```bat
python AURA_HARNESS_UNICO_CONSOLIDADO.py --self-test
```

Esperado: `Harness self-test: OK; modo seguro ativo; nenhuma alteração executada.`

---

## Fluxo completo (ponta a ponta)

### 1) Subir o supervisor

```bat
python AURA_HARNESS_UNICO_CONSOLIDADO.py
```

- [ ] Banner mostra paper trade ativo e execução real bloqueada
- [ ] (Opcional) Descoberta de 1 skill no boot — somente leitura, não instala

### 2) Conferir estado

No chat:

```
status
```

- [ ] Tabela/resumo dos serviços (ollama / engine / bridge / voice)
- [ ] Nenhuma alteração de arquivo

### 3) Escolher a skill (somente leitura)

Opção A — descoberta assistida:

```
descobrir skills
```

- [ ] Lista skills locais em `AURA_ROOT/skills`
- [ ] Pode listar 1 candidato real do GitHub (se rede liberada)
- [ ] **Nada é baixado** neste passo

Opção B — você já tem a URL HTTPS:

- Só GitHub, GitLab ou Codeberg
- Exemplo: `https://github.com/org/nome-da-skill`

### 4) Pedir instalação → plano (ainda sem download)

```
instalar skill https://github.com/org/nome-da-skill
```

Variante com branch:

```
instalar skill https://github.com/org/nome-da-skill@main
```

- [ ] Resposta: `⚠️ PLANO PENDENTE p-…`
- [ ] Payload com `url`, `label`, `execute_installers: false`
- [ ] Instrução: digitar exatamente `CONFIRMAR PLANO p-…`
- [ ] **Nenhum arquivo criado ainda**

### 5) Confirmar o download para staging

```
CONFIRMAR PLANO p-<id-exibido>
```

- [ ] Download **só arquivo estático** (tarball), sem `git clone`
- [ ] Extração em `AURA_ROOT/halem_control/staging/<label>-<timestamp>/`
- [ ] Manifesto `_staging_origin.json` com `sha256`, `source_url`, `promoted: false`
- [ ] Varredura estática de riscos (alerta, não bloqueia sozinha)
- [ ] Mensagem: nada de `setup.py` / Makefile foi executado

Se falhar (rede, branch inexistente, arquivo > limite): plano marca `STAGING_FALHOU`; **nenhum instalador rodou**.

### 6) Revisar o que caiu em staging

```
listar staging
```

- [ ] Aparece o item com origem e status `⏳ aguardando revisão`

No disco, revise manualmente:

- [ ] Licença e dependências
- [ ] Ausência de scripts `curl | bash`, chaves privadas, PowerShell `-enc`
- [ ] Conteúdo faz sentido para o AURA (skill/agent tool, não malware)

### 7) Promover para a área ativa (segunda aprovação)

```
promover <label-ou-nome-mostrado>
```

- [ ] Novo plano pendente (com alertas da varredura, se houver)
- [ ] Digitar exatamente:

```
CONFIRMAR PLANO p-<novo-id>
```

Efeitos esperados:

- [ ] Cópia para `AURA_ROOT/skills/<label>/` (kind `install_skill`)
- [ ] Se já existia destino: backup em `AURA_ROOT/halem_control/backups/`
- [ ] Manifesto com `promoted: true` e `promoted_at`
- [ ] **Ainda nenhum instalador executado** — setup próprio continua manual e fora do harness

### 8) Verificar inventário

```
descobrir skills
```

ou inspecionar pasta:

- [ ] Skill aparece em `AURA_ROOT/skills/`
- [ ] Auditoria em `AURA_ROOT/halem_control/audit.jsonl` registra download e promoção

### 9) Cancelar a qualquer momento (antes do CONFIRMAR)

```
cancelar
```

- [ ] `pending_action` limpo
- [ ] Nada alterado

---

## O que o harness **nunca** faz neste fluxo

| Ação | Bloqueado? |
|---|---|
| `git clone` | Sim — só tarball HTTPS |
| Rodar `setup.py` / `Makefile` / instaladores do pacote | Sim |
| Desbloquear live / `EXECUTION_ALLOWED` | Sim |
| Instalar porque o modelo “achou bom” | Sim — só comando + CONFIRMAR |
| Promover sem segunda confirmação | Sim |
| Aceitar host fora de github/gitlab/codeberg | Sim |
| Aceitar `http://` (sem TLS) | Sim |

---

## Falhas comuns e o que fazer

| Sintoma | Causa provável | Ação |
|---|---|---|
| `Origem rejeitada` | URL sem HTTPS ou host não allowlist | Usar URL HTTPS válida |
| `download para staging falhou` | Rede, branch errada, rate limit, arquivo grande | Conferir URL/branch; tentar de novo |
| `Não encontrei um único item em staging` | Nome ambíguo ou errado | `listar staging` e usar o nome exato |
| `Confirmação não corresponde` | Texto diferente do pedido | Copiar o `CONFIRMAR PLANO p-…` exibido |
| Varredura aponta `pipe curl -> shell` | Script suspeito no repo | **Não promover**; revisar ou descartar |
| Ollama offline no chat | Serviço local parado | Não impede instalar skill; só afeta conversa/sugestão |

---

## Critérios de aceite (PASS)

1. Self-test OK sem alterar disco de produção.  
2. `instalar skill <url>` só cria plano até o CONFIRMAR.  
3. Após CONFIRMAR do install: árvore só em `halem_control/staging/`, com manifesto e sha256.  
4. Após CONFIRMAR do promover: cópia em `skills/<label>/`, backup se havia destino, sem execução de instaladores.  
5. `audit.jsonl` contém eventos de plano, download e promoção.  
6. `PAPER_TRADE=true` e `EXECUTION_ALLOWED=false` permanecem verdadeiros o tempo todo.

**Sem os passos 4→5 e 7 com CONFIRMAR explícito, não há skill ativa. Sem prova no disco + audit, não há PASS.**
