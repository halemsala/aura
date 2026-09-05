'use strict';
const LOCAL_AI = {
  classicUrl: 'http://127.0.0.1:8765',
  gpuUrl: 'http://127.0.0.1:8000',
  enabled: true,
  lastOk: null,
  lastError: null,
  sent: 0,
  failed: 0
};
async function loadLocalAIConfig() {
  try {
    const r = await chrome.storage.local.get(['cornerai_local_ai_url','cornerai_gpu_url','cornerai_local_ai_enabled']);
    if (r.cornerai_local_ai_url) LOCAL_AI.classicUrl = String(r.cornerai_local_ai_url).replace(/\/$/, '');
    if (r.cornerai_gpu_url) LOCAL_AI.gpuUrl = String(r.cornerai_gpu_url).replace(/\/$/, '');
    if (r.cornerai_local_ai_enabled != null) LOCAL_AI.enabled = !!r.cornerai_local_ai_enabled;
  } catch (_) {}
}
async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs || 5000);
  try {
    return await fetch(url, Object.assign({}, options || {}, { signal: controller.signal }));
  } finally {
    clearTimeout(timer);
  }
}
async function postJson(url, body, timeoutMs) {
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CornerAI': 'unified' },
    body: JSON.stringify(body)
  }, timeoutMs || 5000);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}
const CornerAILocalClient = {
  async sendTelemetryToLocalAI(payload) {
    if (!LOCAL_AI.enabled) return { ok: false, reason: 'disabled' };
    await loadLocalAIConfig();
    const targets = [
      { url: LOCAL_AI.classicUrl + '/api/telemetry', via: '8765' },
      ...(LOCAL_AI.gpuUrl && LOCAL_AI.gpuUrl !== LOCAL_AI.classicUrl ? [{ url: LOCAL_AI.gpuUrl + '/api/telemetry', via: '8000' }] : [])
    ];
    let lastError = 'engine indisponível';
    for (const target of targets) {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const r = await postJson(target.url, payload, 3500);
          LOCAL_AI.sent++; LOCAL_AI.lastOk = Date.now(); LOCAL_AI.lastError = null;
          return { ok: true, via: target.via, result: r };
        } catch (e) {
          lastError = String(e.message || e);
          if (attempt === 0 && /Failed to fetch|NetworkError|ECONNREFUSED|fetch failed|timeout/i.test(lastError)) {
            await new Promise(r => setTimeout(r, 150));
            continue;
          }
          break;
        }
      }
    }
    LOCAL_AI.failed++; LOCAL_AI.lastError = lastError;
    return { ok: false, error: LOCAL_AI.lastError, optional: true };
  },
  async sendHistoricalToLocalAI(rows) {
    if (!LOCAL_AI.enabled) return { ok: false };
    await loadLocalAIConfig();
    try {
      const matches = Array.isArray(rows) ? rows : [];
      return { ok: true, result: await postJson(LOCAL_AI.classicUrl + '/api/historical', { matches }, 8000) };
    } catch (e) { return { ok: false, error: String(e.message || e) }; }
  },
  async status() {
    await loadLocalAIConfig();
    const urls = [
      { url: LOCAL_AI.classicUrl + '/api/status', via: '8765' },
      ...(LOCAL_AI.gpuUrl && LOCAL_AI.gpuUrl !== LOCAL_AI.classicUrl ? [{ url: LOCAL_AI.gpuUrl + '/api/status', via: '8000' }] : [])
    ];
    let last = 'engine indisponível';
    for (const target of urls) {
      try {
        const res = await fetchWithTimeout(target.url, {}, 1800);
        const data = await res.json().catch(() => ({}));
        if (res.ok) return { ok: true, via: target.via, data };
        last = data?.error || ('HTTP ' + res.status);
      } catch (e) { last = String(e.message || e); }
    }
    return { ok: false, error: last, optional: true };
  }
};
try { self.CornerAILocalClient = CornerAILocalClient; self.LOCAL_AI = LOCAL_AI; } catch (_) {}
