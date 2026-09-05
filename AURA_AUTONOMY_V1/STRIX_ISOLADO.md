# Strix — Procedimento isolado de avaliação (NÃO é parte do runtime AURA)

**Classificação:** ferramenta autônoma de pentest / AI hacking (Apache-2.0).  
**Objetivo:** encontrar e validar vulnerabilidades com PoCs.  
**Proibido:** rodar no mesmo host de produção do AURA, contra terceiros, ou sem autorização escrita.

Fontes oficiais de referência:
- https://github.com/usestrix/strix
- https://docs.strix.ai / https://strix.ai

---

## 1. Pré-condições obrigatórias

- [ ] Autorização escrita do dono do alvo (escopo, datas, contatos)
- [ ] VM ou máquina dedicada (sem credenciais de produção AURA)
- [ ] Snapshot da VM antes de qualquer scan
- [ ] Docker disponível (se o modo self-hosted exigir)
- [ ] LLM key própria (somente na VM)
- [ ] Rede limitada ao necessário
- [ ] Timeout e orçamento de tokens definidos
- [ ] Política: **sem auto-fix**

---

## 2. O que Strix faz (resumo)

- Agentes que exploram código e/ou URLs
- Toolkit: browser, HTTP proxy, terminal, runtime Python
- Gera achados com PoCs (não apenas alertas estáticos)
- Pode sugerir correções — **nunca aplicar automaticamente no AURA**

---

## 3. Sequência recomendada (isolada)

### 3.1 Preparar VM
```text
1. Criar VM limpa (Windows ou Linux)
2. Snapshot "limpo"
3. Instalar Python 3.10/3.11 + Docker (se necessário)
4. Não montar discos de produção do AURA
```

### 3.2 Instalar Strix (seguir doc oficial do momento)
Consulte sempre o README oficial. Exemplos históricos (podem mudar):

```bash
# Exemplo — confirme na documentação atual antes de usar
pip install strix-agent
# ou instalador documentado em strix.ai
```

Skills auxiliares (se documentadas):
```bash
npx skills add usestrix/strix
```

**Não use `curl | bash` sem inspecionar o script antes.**

### 3.3 Configurar LLM
```bash
# Exemplo conceitual — use as variáveis oficiais do Strix
export STRIX_LLM="provedor/modelo"
export LLM_API_KEY="sua_chave_somente_na_vm"
```

### 3.4 Definir alvo autorizado
- Cópia do código do AURA **sem** secrets, **ou**
- Staging autorizado com dados fictícios

Nunca:
- Produção com usuários reais
- Domínios de terceiros
- Credenciais LIVE

### 3.5 Executar scan com limites
```bash
# Exemplo conceitual — ajuste aos flags oficiais atuais
strix --target /caminho/copia-autorizada
# Preferir modo headless/report-only quando disponível
```

Defina:
- Timeout máximo
- Limite de requisições
- Diretório de artefatos
- Sem flags de “auto-remediation”

### 3.6 Revisar resultados
- Ler todos os findings
- Validar PoCs manualmente
- Classificar falso positivo vs real
- **Não** aplicar patches automaticamente no AURA

### 3.7 Encerrar
- Exportar relatório
- Apagar artefatos sensíveis após retenção definida
- Reverter snapshot ou destruir a VM
- Revogar API keys usadas só para o teste

---

## 4. Integração com AURA (indireta)

Se um achado for real e relevante:
1. Abrir item de trabalho no processo de engenharia do AURA
2. Reproduzir em ambiente de desenvolvimento
3. Correção mínima + teste paper-only
4. Revisão + changelog + rollback plan
5. Nunca deixar o Strix alterar arquivos do AURA diretamente

---

## 5. Remoção completa na VM

```bash
pip uninstall strix-agent -y
# remover containers Docker relacionados
# apagar diretórios de artefatos e caches
# revogar chaves LLM
```

---

## 6. Checklist final Strix

- [ ] Autorização escrita arquivada
- [ ] VM isolada usada
- [ ] Sem auto-fix
- [ ] Relatório revisado por humano
- [ ] Nenhuma credencial de produção exposta
- [ ] VM limpa ou destruída
- [ ] Achados convertidos em tarefas de engenharia (se houver)

**Strix não aumenta a autonomia operacional do AURA. É ferramenta de segurança ofensiva controlada.**
