/* Integração mínima na extensão atual.
 * Carregar depois de aura-quantx-adapter.js.
 * Não altera decisão, captura, Risk Engine ou contratos existentes.
 */
'use strict';
(() => {
  const A = window.AURA_QUANTX_ADAPTER;
  if (!A) return;

  const openCentral = () => {
    if (typeof A.openCentral === 'function') return A.openCentral();
    try {
      if (window.chrome?.runtime?.getURL) {
        chrome.tabs.create({ url: chrome.runtime.getURL('src/aura-quantx-central.html'), active: true });
        return;
      }
    } catch (_) {}
    window.open('src/aura-quantx-central.html', '_blank', 'noopener');
  };

  const openChat = () => {
    if (typeof A.openChat === 'function') return A.openChat();
    try {
      if (window.chrome?.runtime?.getURL) {
        chrome.tabs.create({ url: chrome.runtime.getURL('src/kanteiro-chat.html'), active: true });
        return;
      }
    } catch (_) {}
    window.open('src/kanteiro-chat.html', '_blank', 'noopener');
  };

  const openLegacy = () => {
    if (typeof A.openLegacyDashboard === 'function') return A.openLegacyDashboard();
    try {
      if (window.chrome?.runtime?.getURL) {
        chrome.tabs.create({ url: chrome.runtime.getURL('ui/dashboard.html'), active: true });
      }
    } catch (_) {}
  };

  const install = () => {
    if (document.getElementById('auraOpenCentral')) return;
    const host = document.createElement('div');
    host.id = 'auraInstallableActions';
    host.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;padding:8px;z-index:99999';
    host.innerHTML = '<button id="auraOpenCentral" type="button">CENTRAL AURA</button>' +
      '<button id="auraOpenKanteiro" type="button">CHAT KANTEIRO</button>' +
      '<button id="auraOpenLegacy" type="button">DASHBOARD ANTIGA</button>';
    document.body.appendChild(host);
    document.getElementById('auraOpenCentral').onclick = () => openCentral();
    document.getElementById('auraOpenKanteiro').onclick = () => openChat();
    document.getElementById('auraOpenLegacy').onclick = () => openLegacy();
  };

  window.AURA_QUANTX_UI_HOOK = { openCentral, openChat, openLegacy, install };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
