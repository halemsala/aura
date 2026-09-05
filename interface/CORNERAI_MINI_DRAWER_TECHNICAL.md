# CornerAI Mini Drawer System

## Objetivo

Esta implementação refatora a navegação lateral do CornerAI/AURA para um **Mini Drawer System** responsivo, preservando a sala de análise ao vivo e evitando deslocamentos bruscos dos gráficos. O estado expandido é o padrão; o estado recolhido mantém os ícones, LEDs dos agentes e o gatilho persistente de restauração.

## Menus canônicos

| Identificador | Rótulo | Função visual |
|---|---|---|
| `command` | Central de Comando | Entrada principal da sala de análise |
| `live` | Métricas ao Vivo | Monitoramento da partida e sinais ativos |
| `agents` | Status dos Agentes | Estado dos agentes locais |
| `macd` | MACD xG | Leitura de tendência de xG |
| `h2h` | H2H | Comparação histórica entre equipes |
| `odds` | Odds Matrix | Comparação entre modelo e mercado |

## Estado e comportamento

O estado `sidebarCollapsed` controla a classe `sidebar-collapsed`. O botão persistente do cabeçalho usa `title="Recolher menu"` ou `title="Expandir menu"`, alternando o ícone visual do gatilho. O CSS usa `width`, `opacity` e `transition` para realizar a contração em aproximadamente 300 ms, enquanto o conteúdo principal preserva o grid e recebe a margem correspondente.

No modo recolhido, os rótulos desaparecem sem ocupar espaço, os ícones continuam centralizados e os tooltips flutuantes recebem `data-tooltip`. Esses tooltips utilizam fundo translúcido, `backdrop-filter`, borda luminosa e sombra para manter o estilo glassmorphism.

## Telemetria local

A base da sidebar contém quatro linhas discretas: Scraper/Ingestão, Quant/Matemático, Momentum e Decision Maker. Cada linha possui um micro-LED pulsante, um status legível no modo expandido e um tooltip no modo recolhido. Os sinais são visuais e locais, sem iniciar integrações externas.

## Diretriz visual

A composição mantém o tema **Cyber Sports** sobre Graphite Matte/Future Dusk, com acentos em neon ciano, verde gramado, âmbar e violeta. O glassmorphism é aplicado com camadas translúcidas, blur, bordas internas e sombras profundas. Gráficos continuam usando contêineres responsivos para que o redimensionamento não quebre a sala de análise.

## Acessibilidade e segurança visual

O foco de teclado usa `:focus-visible` com contorno verde de alto contraste. Há suporte a `prefers-reduced-motion`, desativando transições e pulsos quando o usuário solicita redução de movimento. O estado colapsado não elimina a navegação: ícones, `title` nativo e tooltips continuam disponíveis.

## Validação de produção

A validação recomendada é executar `pnpm run typecheck` e `pnpm run build`. O pacote de interface não deve conter `server`, `engine`, `agents`, `bridge`, `desktop`, `scripts`, `addons`, `drizzle`, `node_modules` ou `dist`.

## Arquivos alterados

- `client/src/pages/Home.tsx`: menus canônicos, telemetria dos agentes e estado do drawer.
- `client/src/aura-command-redesign.css`: transições, tooltips, glassmorphism, LEDs, contraste e responsividade.

## Nota de integração

A implementação foi aplicada ao frontend React/Vite existente do AURA para preservar os gráficos, o radar tático, a simulação local e os painéis já aprovados. A estrutura gerada permanece somente visual e não executa agentes, scraping, apostas, chamadas externas ou ações operacionais.

> A interface é uma camada de visualização local. Os valores exibidos na sala de análise continuam sendo demonstrativos e não representam feed esportivo real.

## Alertas críticos e áudio local

A simulação exibe janelas críticas em ciclos locais: pressão aos 80 minutos e escanteio na janela seguinte. O sistema usa a função `showAlert` para abrir o alerta visual 3D, identificar o evento com ícone próprio e emitir um tom curto por Web Audio API. O controle de áudio fica no topo e alterna entre ativo e silenciado sem afetar os demais estados da sala.

A síntese sonora é gerada no navegador, sem arquivo externo, chamada de API ou serviço em background. As frequências e formas de onda variam por evento para diferenciar pressão, escanteio, cartão, pênalti, gol e alerta geral. O sistema mantém o fallback silencioso quando o navegador não disponibiliza `AudioContext` ou quando o operador desativa o som.

Os alertas visuais usam composição 3D em camadas, pulsação, cor semântica, brilho e botão de encerramento. A regra de `prefers-reduced-motion` remove pulsos e transições para preservar acessibilidade.
