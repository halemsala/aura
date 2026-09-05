# Prompt operacional para enviar ao Grok

Você recebeu o pacote `AURA_QUANTX_GROK_BUNDLE`. Quero que o instale no sistema AURA QUANT-X atual, mas **não quero que você modifique, sobrescreva ou reempacote o ZIP original**.

Trabalhe sobre uma cópia/branch do sistema atual. O pacote é um overlay instalável, composto por páginas, estilos, JavaScript e documentação. O objetivo é adicionar uma central premium de inteligência de escanteios e um chat fullscreen com o Kanteiro, mantendo a dashboard antiga como fallback.

## Resultado obrigatório

Ao terminar, devem existir duas entradas funcionais:

```text
Central AURA → src/aura-quantx-central.html
Chat Kanteiro → src/kanteiro-chat.html
```

A central deve manter o campo 3D como núcleo, mostrar escanteios como foco principal, exibir gols/cartões/substituições apenas como contexto, expor todos os oito grupos de gráficos SokkerPro e permitir ocultar, recolher, ampliar, restaurar e salvar painéis.

Os oito grupos são:

```text
Pressão 3/5/10 min
Gols esperados (xG)
Linha do tempo do jogo
Oscilação das odds
Momento do xG
Pressão relativa
Histórico entre equipes
Radar de estatísticas
```

O chat deve abrir em tela inteira, usar o nome Kanteiro, manter o `fixtureId` travado, receber contexto real, disponibilizar perguntas rápidas e permitir ouvir, copiar e consultar fontes.

## Arquivos do pacote

Copie e integre:

```text
src/aura-quantx-adapter.js
src/aura-quantx-central.html
src/aura-quantx-central.css
src/aura-quantx-central.js
src/kanteiro-chat.html
src/kanteiro-chat.css
src/kanteiro-chat.js
src/aura-quantx-extension-hook.js
```

Leia também `INTEGRATION_CONTRACT.md` e `INSTALL_FOR_GROK.md` antes de editar qualquer arquivo.

## Regras de integração

Use os contratos existentes do sistema. O adapter deve ser o único lugar que conhece URLs do Engine e Voice. Preserve:

```text
GET_DIAGNOSTICS
CHARTS_UNIFIED_GET
GET /api/status
GET /api/analysis/{fixtureId}
POST /api/trader/chat
POST /api/voice/neural
```

Se os nomes ou rotas atuais forem diferentes, ajuste somente o adapter e documente o mapeamento. Não espalhe alterações pelo Engine, Risk Manager ou captura sem necessidade.

Não reimplemente a captura do SokkerPro. Use o módulo de gráficos unificados existente e preserve os oito grupos. Não apague `dashboard.html`, `dashboard.js`, `sidepanel.html`, `sidepanel.js`, `charts-unified.js`, `voice-assistant.js`, o banco, modelos, logs ou configurações.

## Segurança e fail-closed

A interface nunca pode autorizar uma entrada. Ela apenas apresenta a decisão do Engine. Se a resposta for `BLOCK`, `BLOCKED_BY_DATA`, `BLOCKED_BY_MARKET`, `STALE` ou tiver `exposição=0`, isso deve permanecer bloqueado na tela.

Não transformar `N/D`, `null`, `pending` ou `stale` em zero. Não inventar odds, médias H2H, séries de gráficos ou probabilidades. Dados ausentes devem aparecer como `N/D`, `AGUARDANDO` ou `DESATUALIZADO`.

O chat pode explicar, resumir e responder perguntas, mas não pode alterar Risk Engine, Kelly, stake, exposição, fixture lock, captura, modelos ou configuração crítica.

## Execução por etapas

### Etapa A — backup e inventário

Faça cópia/branch, registre o hash do estado inicial e liste as rotas da dashboard antiga. Não faça perguntas conceituais. Se houver incompatibilidade real, registre-a e continue com o adapter.

### Etapa B — instalar páginas sem remover a antiga

Copie os arquivos do pacote, exponha-os na extensão e adicione os botões `CENTRAL AURA`, `ABRIR CHAT KANTEIRO` e `VOLTAR À CENTRAL`. Não duplique botões que já existam.

### Etapa C — ligar dados reais

Conecte estado, gráficos, análise, chat e voz pelo adapter. Verifique que o novo dashboard recebe o mesmo fixture da dashboard antiga. Se o fixture mudar, limpar o contexto e impedir mistura de partidas.

### Etapa D — habilitar painéis e chat

Ative os controles de painel. O Campo 3D pode ser minimizado, mas deve permanecer sempre restaurável. Os demais módulos podem ser ocultados e reordenados. Salvar layout apenas no armazenamento da interface; não modificar o banco do Engine.

Habilite as perguntas rápidas:

```text
Resumir os escanteios
Por que bloqueou?
Mostrar todos os gráficos
Revisar os últimos 5 minutos
Comparar a pressão casa/fora
Explicar a probabilidade
Analisar o mercado
Ver fontes dos dados
O que mudou agora?
Falar o resumo
```

### Etapa E — testes

Execute validação estática de JavaScript, abra as duas páginas no navegador e teste Engine offline, Bridge offline, Voice offline, captura sem fixture, fixture trocado, odds ausentes, divergência de eventos/estatísticas, gráficos `pending`, gráficos `stale`, H2H ausente e decisão `BLOCK`.

Compare antes/depois: fixture, placar, minuto, estatísticas, oito gráficos, decisão, exposição, reason codes, eventos, voz e chat. A dashboard antiga deve continuar abrindo.

### Etapa F — relatório

Entregue:

```text
arquivos copiados
arquivos alterados
rotas/contratos mapeados
variáveis de configuração
comandos executados
testes aprovados e reprovados
screenshots antes/depois
riscos restantes
rollback exato
```

Não continue me fazendo perguntas conceituais. Só pare se existir um bloqueio técnico real. Caso contrário, instale, teste, corrija os problemas locais e finalize o relatório. Não altere o ZIP original.
