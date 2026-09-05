/* AURA QUANT-X — Adapter de integração para instalação pelo Grok.
 * Este arquivo não altera o sistema existente. Ele define a ponte entre a UI nova
 * e os contratos já existentes do Engine/Bridge/extensão.
 *
 * Configure window.AURA_QUANTX_CONFIG antes de carregar este arquivo, se necessário:
 * { engineBase: 'http://127.0.0.1:8765', voiceBase: 'http://127.0.0.1:8099' }
 */
(function (global) {
  'use strict';

  const config = Object.assign({
    engineBase: 'http://127.0.0.1:8765',
    voiceBase: 'http://127.0.0.1:8099',
    requestTimeoutMs: 8000,
    chatTimeoutMs: 45000,
    allowDemoData: false
  }, global.AURA_QUANTX_CONFIG || {});

  const isFiniteNumber = value => Number.isFinite(Number(value));
  const text = value => String(value ?? '').trim();
  const encode = value => encodeURIComponent(String(value ?? ''));

  async function request(path, options = {}) {
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timeout = setTimeout(() => controller?.abort(), options.timeoutMs || config.requestTimeoutMs);
    try {
      const response = await fetch(`${config.engineBase}${path}`, {
        method: options.method || 'GET',
        headers: Object.assign({ 'Content-Type': 'application/json', 'X-AURA-UI': 'quantx-central-v1' }, options.headers || {}),
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller?.signal,
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || `HTTP ${response.status}`);
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function chromeMessage(message) {
    if (!global.chrome?.runtime?.sendMessage) return null;
    return new Promise(resolve => {
      try {
        global.chrome.runtime.sendMessage(message, response => {
          const err = global.chrome.runtime.lastError;
          if (err) {
            // Common: SW asleep / context invalidated — resolve null, UI shows N/D
            resolve({ ok: false, error: err.message || String(err), _swError: true });
            return;
          }
          resolve(response || null);
        });
      } catch (e) { resolve({ ok: false, error: e?.message || String(e), _swError: true }); }
    });
  }

  function getExtensionUrl(path) {
    try {
      if (global.chrome?.runtime?.getURL) return global.chrome.runtime.getURL(path);
    } catch (_) {}
    return path;
  }

  async function getState() {
    let response = await chromeMessage({ type: 'GET_DIAGNOSTICS' });
    if (response && !response._swError && response.state) return response.state;
    if (response && !response._swError && response.snapshot) return response.snapshot;
    response = await chromeMessage({ type: 'REQUEST_STATE' });
    if (response && !response._swError && (response.fixtureId || response.state)) {
      return response.state || response;
    }
    // Engine fallback: status only (no fixture mix)
    try {
      const status = await request('/api/status');
      if (status) return { engineStatus: status, sources: { network: 'engine' }, _source: 'engine_status' };
    } catch (_) {}
    return null;
  }

  async function getCharts() {
    // Prefer SW state.charts (content script pushes CHARTS_UNIFIED packs into SW)
    let response = await chromeMessage({ type: 'CHARTS_UNIFIED_GET' });
    if (response?.pack || response?.charts) return response.pack || response.charts;
    // Fallback: diagnostics/state often already embeds charts
    const diag = await chromeMessage({ type: 'GET_DIAGNOSTICS' });
    if (diag?.state?.charts) return diag.state.charts;
    const st = await chromeMessage({ type: 'REQUEST_STATE' });
    if (st?.charts) return st.charts;
    return null;
  }

  async function getAnalysis(fixtureId) {
    if (!fixtureId) return null;
    try { return await request(`/api/analysis/${encode(fixtureId)}`); }
    catch (_) { return null; }
  }

  async function getCornerAnalysis(fixtureId, payload) {
    try {
      return await request('/api/corners/analysis', {
        method: 'POST',
        body: { fixtureId: fixtureId || null, payload: payload || null },
        timeoutMs: config.requestTimeoutMs
      });
    } catch (e) {
      return { ok: false, error: e?.message || String(e) };
    }
  }

  async function getStatus() {
    try { return await request('/api/status'); }
    catch (_) { return null; }
  }

  async function sendChat(payload) {
    const body = Object.assign({ fixtureId: null, context: null, systemContext: null, history: [] }, payload || {});
    try {
      return await request('/api/trader/chat', { method: 'POST', body, timeoutMs: config.chatTimeoutMs });
    } catch (error) {
      return { ok: false, error: error?.message || String(error) };
    }
  }

  async function speak(textToSpeak) {
    // Limpa markdown/asteriscos e normaliza espaços antes de enviar ao TTS
    const clean = text(textToSpeak)
      .replace(/[*_`#~|>\\]/g, '')
      .replace(/\[[^\]]+\]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!clean) return { ok: false, error: 'texto vazio' };
    try {
      if (typeof global.auraSpeakText === 'function') {
        const ok = await global.auraSpeakText(clean);
        if (ok) return { ok: true, via: 'extension' };
      }
      const response = await fetch(`${config.voiceBase}/api/voice/neural`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean, voice: 'pt-BR-AntonioNeural' }),
        signal: AbortSignal.timeout(config.requestTimeoutMs)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data?.audio_base64) throw new Error(data?.error || 'voz indisponível');
      if (data.gender && data.gender !== 'male') throw new Error('tts_gender_not_male');
      if (data.fallback && data.fallback !== 'disabled') throw new Error('tts_fallback_rejected');
      if (/(Francisca|gtts|google)/i.test(`${data.voice || ''} ${data.engine || ''}`)) throw new Error('tts_legacy_voice_rejected');
      const audio = new Audio(`data:${(data.format || data.audio_format) === 'wav' ? 'audio/wav' : 'audio/mpeg'};base64,${data.audio_base64}`);
      await audio.play();
      return { ok: true, via: 'voice-8099' };
    } catch (error) {
      return { ok: false, error: error?.message || String(error) };
    }
  }

  async function openCentral() {
    const viaBg = await chromeMessage({ type: 'OPEN_CENTRAL' });
    if (viaBg?.ok) return viaBg;
    global.open(getExtensionUrl('src/aura-quantx-central.html'), '_blank', 'noopener');
    return { ok: true, mode: 'window.open' };
  }
  async function openChat() {
    const viaBg = await chromeMessage({ type: 'OPEN_KANTEIRO_CHAT' });
    if (viaBg?.ok) return viaBg;
    global.open(getExtensionUrl('src/kanteiro-chat.html'), '_blank', 'noopener');
    return { ok: true, mode: 'window.open' };
  }
  async function openLegacyDashboard() {
    const viaBg = await chromeMessage({ type: 'OPEN_LEGACY_DASHBOARD' });
    if (viaBg?.ok) return viaBg;
    global.open(getExtensionUrl('ui/dashboard.html'), '_blank', 'noopener');
    return { ok: true, mode: 'window.open' };
  }

  global.AURA_QUANTX_ADAPTER = {
    config,
    request,
    getState,
    getCharts,
    getAnalysis,
    getCornerAnalysis,
    getStatus,
    sendChat,
    speak,
    openCentral,
    openChat,
    openLegacyDashboard,
    getExtensionUrl,
    isFiniteNumber
  };
})(window);
