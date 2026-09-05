# CornerAI AURA Quant-X Terminal 12.5.8

## Alterações
- Side Panel nativo do Chrome via `side_panel` + permissão `sidePanel`.
- Terminal premium em CSS nativo, sem Tailwind/CDN.
- HUD compacto de partida, APPM, xG, cantos e qualidade.
- Painéis separados para Live Engine, Market Engine e Risk Engine.
- Estado `FRESH/STALE` e modo fail-closed visual.
- Kelly bruto separado do limite de exposição; UI exibe Risk Cap de 2%.
- Command line com `/analisar`, `/risk`, `/why`, `/state`, `/market`.
- Feedback GREEN/RED conectado ao endpoint existente.
- Mantidas captura, Snapshot, Telegram, Visão e ações do Trader.
- Renderização defensiva para diferentes formatos de resposta do engine.

## Observação
A UI não usa Tailwind. As classes Tailwind do conceito original foram traduzidas para CSS local para respeitar a CSP MV3 (`script-src 'self'`) e reduzir dependências.

## Instalação no Chrome
1. Extraia o ZIP.
2. Abra `chrome://extensions`.
3. Ative **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação**.
5. Selecione a pasta `AURA_QUANT_X_Complete/extensao`.
6. Ligue o engine local em `127.0.0.1:8765` antes de analisar.
