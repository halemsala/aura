# AURA QUANT-X — Pacote de instalação para o Grok

## Objetivo

Este pacote é um **overlay separado**. Ele não modifica o ZIP original. O Grok deve usar os arquivos para integrar uma nova central de inteligência de escanteios ao sistema atual, mantendo a dashboard antiga como fallback até a validação completa.

A instalação deve adicionar:

- `aura-quantx-central.html`: central premium com campo 3D, risco, gráficos e painéis ocultáveis;
- `aura-quantx-central.css`: design system da central;
- `aura-quantx-central.js`: renderização, replay, campos, layout e integração;
- `kanteiro-chat.html`: chat fullscreen contextual;
- `kanteiro-chat.css`: layout premium do chat;
- `kanteiro-chat.js`: histórico, atalhos, voz e contexto;
- `aura-quantx-adapter.js`: ponte para Engine, gráficos unificados e Voice;
- `aura-quantx-extension-hook.js`: botões opcionais de entrada na extensão;
- documentação de contratos e rollback.

## Regras obrigatórias

O Grok deve trabalhar sobre uma cópia ou branch. O ZIP original não pode ser sobrescrito, apagado ou migrado automaticamente. A dashboard antiga deve continuar disponível durante toda a instalação.

Nenhum campo ausente pode virar zero, string vazia ou valor inventado. A interface deve exibir `N/D`, `AGUARDANDO` ou `DESATUALIZADO`. O bundle não pode criar dados sintéticos em modo de produção.

O bundle nunca decide entrada. Ele apenas apresenta o contrato retornado pelo Engine. `BLOQUEADO`, `OBSERVAÇÃO`, exposição, Kelly e o Risk Engine devem ser exibidos como recebidos; a UI não pode transformar `WATCH` em `BUY` nem alterar stake, Kelly, risco ou exposição.

## Ordem de instalação

### Etapa 0 — backup e baseline

Criar uma cópia do projeto e registrar o hash do ZIP original. Iniciar a dashboard antiga e confirmar que captura, Engine, Bridge, Voice, chat e gráficos continuam funcionando. Salvar um screenshot do baseline.

### Etapa 1 — copiar arquivos standalone

Copiar todo o conteúdo de `src/` para um diretório servido pela extensão. Se a extensão usar outro diretório, ajustar os caminhos sem alterar a lógica dos arquivos.

Carregar `aura-quantx-adapter.js` antes de qualquer tela. Configurar, se necessário:

```js
window.AURA_QUANTX_CONFIG = {
  engineBase: 'http://127.0.0.1:8765',
  voiceBase: 'http://127.0.0.1:8099',
  requestTimeoutMs: 8000,
  chatTimeoutMs: 45000,
  allowDemoData: false
};
```

### Etapa 2 — expor as páginas

Adicionar as páginas à lista de recursos da extensão conforme o manifesto atual. Não remover páginas antigas. Para uma extensão Chrome, carregar as páginas por `chrome.runtime.getURL()` e abrir com `chrome.tabs.create` ou equivalente da arquitetura atual.

Adicionar o `aura-quantx-extension-hook.js` somente em uma superfície já controlada pela extensão. O hook fornece:

```js
window.AURA_QUANTX_UI_HOOK.openCentral();
window.AURA_QUANTX_UI_HOOK.openChat();
```

Se o projeto já tiver botões equivalentes, reutilizar os botões existentes e não criar duplicatas.

### Etapa 3 — ligar o estado real

Mapear `GET_DIAGNOSTICS` para `AURA_QUANTX_ADAPTER.getState()`. Mapear `CHARTS_UNIFIED_GET` para `getCharts()`. A captura de gráficos já deve continuar sendo feita pelo módulo existente, que publica APPM/pressão, xG, timeline, odds, MACD xG, PBar, H2H e radar.

Mapear `GET /api/analysis/{fixtureId}` para `getAnalysis()`. Mapear `POST /api/trader/chat` para `sendChat()`. Mapear o serviço de voz `POST /api/voice/neural` para `speak()`.

Se algum endpoint tiver outro caminho, alterar apenas `aura-quantx-adapter.js`. Não espalhar URLs pelo HTML ou pelos componentes.

### Etapa 4 — adicionar entrada para o chat

Criar um botão visível `ABRIR CHAT KANTEIRO` na central e um botão equivalente na dashboard antiga. O botão deve abrir `kanteiro-chat.html` em uma aba/janela. Antes de abrir, pode gravar uma pergunta inicial em `sessionStorage`:

```js
sessionStorage.setItem(
  'aura_kanteiro_prefill',
  'Resuma os escanteios e explique a decisão atual.'
);
```

O chat deve ler o `fixtureId` atual e jamais aceitar contexto de outra partida.

### Etapa 5 — validação

Testar primeiro com Engine/Bridge/Voice desligados. A tela deve carregar e exibir `N/D`, `AGUARDANDO` ou `DESATUALIZADO`, sem exceções JavaScript.

Depois testar com uma partida real capturada. Confirmar que placar, fixture, minuto, eventos, qualidade, gráficos e decisão aparecem na central. Testar também mercado ausente, divergência de escanteios, H2H ausente, gráficos pendentes, stale, fixture trocado, Engine offline e Voice offline.

Só depois comparar a cobertura de campos entre dashboard antiga e nova. Nenhuma função deve ser removida enquanto essa comparação não estiver aprovada.

## Critérios de aceite

A instalação só deve ser considerada concluída quando a nova central abrir em uma rota própria, o botão de chat funcionar, o contexto da partida estiver travado, os oito grupos de gráficos puderem ser consultados, painéis puderem ser ocultados e restaurados, a voz puder ser acionada sem quebrar a conversa, a dashboard antiga continuar acessível e todos os estados de risco permanecerem fail-closed.

O Grok deve entregar um relatório com arquivos copiados, arquivos alterados, endpoints mapeados, testes executados, screenshots antes/depois, falhas encontradas e instruções de rollback.

## Rollback

Para reverter, remover apenas os arquivos standalone, retirar o hook e restaurar os pontos de entrada adicionados. Não apagar banco, histórico, modelos, configurações, captura ou arquivos originais.
