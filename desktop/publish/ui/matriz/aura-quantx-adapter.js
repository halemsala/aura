/* AURA QUANT-X — adaptador da Matriz para o WebView2 desktop.
 * Usa somente serviços locais e os contratos do Engine/Voice existentes.
 * Não contém dados de demonstração e não concede autoridade operacional.
 */
(function (global) {
  'use strict';

  const config = Object.assign({
    engineBase: 'http://127.0.0.1:8765',
    voiceBase: 'http://127.0.0.1:8099',
    requestTimeoutMs: 8000,
    chatTimeoutMs: 120000,
    allowDemoData: false
  }, global.AURA_QUANTX_CONFIG || {});

  const text = value => String(value ?? '').trim();

  async function request(path, options = {}) {
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timeout = setTimeout(() => controller?.abort(), options.timeoutMs || config.requestTimeoutMs);
    try {
      const response = await fetch(`${config.engineBase}${path}`, {
        method: options.method || 'GET',
        headers: Object.assign({ 'Content-Type': 'application/json', 'X-AURA-UI': 'quantx-matriz-v1' }, options.headers || {}),
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller?.signal,
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || data?.detail || `HTTP ${response.status}`);
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function getState() {
    try {
      const data = await request('/api/ui/state');
      return data?.snapshot || data || null;
    } catch (_) {
      try {
        const status = await request('/api/status');
        return { engineStatus: status, sources: { network: 'engine' }, _source: 'engine_status' };
      } catch (__) {
        return null;
      }
    }
  }

  async function getCharts() {
    try {
      const data = await request('/api/ui/state');
      return data?.charts || data?.snapshot?.charts || null;
    } catch (_) {
      return null;
    }
  }

  async function getAnalysis(fixtureId) {
    if (!fixtureId) {
      try {
        const data = await request('/api/ui/state');
        return data?.analysis || null;
      } catch (_) {
        return null;
      }
    }
    try {
      return await request(`/api/analysis/${encodeURIComponent(String(fixtureId))}`);
    } catch (_) {
      return null;
    }
  }

  async function getAgents() {
    try {
      return await request('/api/agents', { timeoutMs: 12000 });
    } catch (error) {
      return { ok: false, error: error?.message || String(error), agents: [], count: 0 };
    }
  }

  async function getActivation() {
    try { return await request('/api/activation', { timeoutMs: 12000 }); }
    catch (error) { return { ok: false, error: error?.message || String(error), tools: [], agents: {} }; }
  }

  async function sendChat(payload) {
    const body = Object.assign({ fixtureId: null, context: null, systemContext: null, history: [] }, payload || {});
    try {
      return await request('/api/glm_chat', { method: 'POST', body, timeoutMs: config.chatTimeoutMs });
    } catch (error) {
      return { ok: false, error: error?.message || String(error), policy: 'GLM_ADVISORY_ONLY', execution_allowed: false };
    }
  }

  async function speak(value) {
    const clean = text(value)
      .replace(/[*_`#~|>\\]/g, '')
      .replace(/\[[^\]]+\]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!clean) return { ok: false, error: 'texto vazio' };
    try {
      const response = await fetch(`${config.voiceBase}/api/voice/neural`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-AURA-UI': 'quantx-matriz-v1' },
        body: JSON.stringify({ text: clean, voice: 'pt-BR-AntonioNeural' }),
        signal: typeof AbortSignal?.timeout === 'function' ? AbortSignal.timeout(config.requestTimeoutMs) : undefined
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data?.audio_base64) throw new Error(data?.error || 'voz indisponível');
      if (data.gender && data.gender !== 'male') throw new Error('tts_gender_not_male');
      if (data.fallback && data.fallback !== 'disabled') throw new Error('tts_fallback_rejected');
      if (/(Francisca|gtts|google)/i.test(`${data.voice || ''} ${data.engine || ''}`)) throw new Error('tts_legacy_voice_rejected');
      const format = data.format || data.audio_format || 'mp3';
      const audio = new Audio(`data:${format === 'wav' ? 'audio/wav' : 'audio/mpeg'};base64,${data.audio_base64}`);
      await audio.play();
      return { ok: true, via: 'voice-8099' };
    } catch (error) {
      return { ok: false, error: error?.message || String(error) };
    }
  }

  function openChat() {
    const panel = global.document?.getElementById('glmChatPanel');
    if (panel) { panel.scrollIntoView({ behavior: 'smooth', block: 'start' }); global.location.hash = 'glmChatPanel'; }
    else global.location.href = 'https://aura.local/matriz/aura-quantx-central.html#glmChatPanel';
    return Promise.resolve({ ok: true, mode: 'matrix' });
  }

  global.AURA_QUANTX_ADAPTER = {
    config,
    request,
    getState,
    getCharts,
    getAnalysis,
    getAgents,
    getActivation,
    sendChat,
    speak,
    openChat
  };
})(window);
