# Service Worker — debug notes (2026-08-19)

## Bugs encontrados e corrigidos

1. **`CHARTS_UNIFIED_GET` não existia no SW**
   - Content script e adapter pediam `CHARTS_UNIFIED_GET`
   - Background só tinha `CHARTS_UNIFIED` (ingestão de pack)
   - **Fix:** handler `CHARTS_UNIFIED_GET` devolve `state.charts`

2. **Abrir Central/Chat após `ensureStateLoaded`**
   - `await` no listener pode “quebrar” o gesto do usuário em alguns fluxos
   - **Fix:** `OPEN_CENTRAL` / `OPEN_KANTEIRO_CHAT` / `OPEN_LEGACY_DASHBOARD` tratados **antes** do `await ensureStateLoaded`, no mesmo padrão de `OPEN_SIDE_PANEL`

3. **Adapter engolia `chrome.runtime.lastError`**
   - SW dormindo / context invalidated → UI silenciosa
   - **Fix:** `chromeMessage` propaga `_swError`; `getState`/`getCharts` com fallbacks

4. **`SW_PING`**
   - Mensagem leve para validar se o SW responde: `{ type: "SW_PING" }` → `{ ok, version, alive }`

## Como validar no Chrome

1. `chrome://extensions` → Detalhes → **Service worker** → Inspecionar
2. Console do SW:
```js
chrome.runtime.sendMessage({type:"SW_PING"}, console.log)
chrome.runtime.sendMessage({type:"REQUEST_STATE"}, r => console.log(r?.fixtureId, r?.charts))
chrome.runtime.sendMessage({type:"CHARTS_UNIFIED_GET"}, console.log)
chrome.runtime.sendMessage({type:"OPEN_CENTRAL"}, console.log)
```
3. Se “Receiving end does not exist”: Recarregar extensão + recarregar aba SokkerPRO

## Erros comuns (não são bugs de sintaxe)

| Mensagem | Causa | Ação |
|---|---|---|
| Receiving end does not exist | SW morto / extensão recarregada | Reload extensão |
| Extension context invalidated | Página antiga após reload | F5 na aba |
| may only be called in response to user gesture | sidePanel sem gesto | Abrir pelo popup/clique |
| Cannot access chrome:// | tab restrita | Usar aba SokkerPRO |

## Sintaxe

`node --check extensao/background.js` → OK
