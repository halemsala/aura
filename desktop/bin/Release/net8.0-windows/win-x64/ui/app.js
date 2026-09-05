const API = {
  bridge: 'http://127.0.0.1:8080',
  engine: 'http://127.0.0.1:8765',
  voice: 'http://127.0.0.1:8099',
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

async function getJson(url, timeout = 2500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: error.message || 'offline' } };
  } finally {
    clearTimeout(timer);
  }
}

function serviceRow(name, url, result) {
  const state = result.ok ? 'online' : 'offline';
  return `<div class="service-row"><div><span class="dot ${state}"></span><strong>${escapeHtml(name)}</strong></div><span class="service-url">${escapeHtml(url.replace('http://', ''))}</span><span class="pill ${state}">${result.ok ? 'OK' : 'offline'}</span></div>`;
}

async function refreshStatus() {
  const checks = await Promise.all([
    ['Bridge', `${API.bridge}/health`],
    ['Engine', `${API.engine}/api/status`],
    ['Voice', `${API.voice}/api/voice/health`],
  ].map(async ([name, url]) => [name, url, await getJson(url)]));
  $('#services').innerHTML = checks.map(([name, url, result]) => serviceRow(name, url, result)).join('');
  const healthy = checks.every(([, , result]) => result.ok);
  $('#overallDot').className = `dot ${healthy ? 'online' : 'offline'}`;
  $('#overallLabel').textContent = healthy ? 'Sistema local disponível' : 'Serviços aguardando';
  $('#overallDetail').textContent = healthy ? 'Bridge, Engine e Voice responderam' : 'Consulte o log desktop_host.log e o BAT mestre';
  $('#paperBadge').textContent = 'PAPER TRADE ONLY';
  return checks;
}

function renderAgents(catalog) {
  const agents = Array.isArray(catalog.agents) ? catalog.agents : [];
  $('#agentCount').textContent = `${agents.length} agentes`; 
  $('#agents').innerHTML = agents.map((agent) => {
    const functions = Array.isArray(agent.functions) ? agent.functions : [];
    const actions = Array.isArray(agent.actions) ? agent.actions : ['status', 'inspect'];
    const state = agent.implementationState || agent.implementation_state || 'unknown';
    const inspectOnly = Boolean(agent.inspectionOnly || state === 'inspect_only');
    return `
    <article class="agent-card">
      <div class="agent-head"><span class="agent-layer">${escapeHtml(agent.layer)}</span><span class="pill ${state === 'runnable' ? 'online' : 'pending'}">${escapeHtml(state)}</span></div>
      <h4>${escapeHtml(agent.name || agent.id)}</h4>
      <p>${escapeHtml(agent.path || agent.file || '')}</p>
      <details><summary>Menu individual · ${functions.length} função(ões)</summary>
        <div class="agent-menu"><b>Ações:</b> ${escapeHtml(actions.join(', '))}</div>
        <div class="agent-functions">${functions.length ? functions.map(escapeHtml).join(', ') : 'Somente inspeção ou nenhuma função allowlisted.'}</div>
      </details>
      <button class="agent-inspect" data-agent="${escapeHtml(agent.id)}">${inspectOnly ? 'Inspecionar funções' : 'Abrir menu seguro'}</button>
      ${actions.includes('glm_review') ? `<button class="agent-glm-review" data-agent="${escapeHtml(agent.id)}">Solicitar revisão GLM</button>` : ''}
    </article>`;
  }).join('');
  document.querySelectorAll('.agent-inspect').forEach((button) => {
    button.addEventListener('click', () => {
      const agent = agents.find((item) => item.id === button.dataset.agent);
      if (!agent) return;
      const functions = Array.isArray(agent.functions) ? agent.functions : [];
      const actions = Array.isArray(agent.actions) ? agent.actions : ['status', 'inspect'];
      const mode = agent.inspectionOnly ? 'somente inspeção' : 'runnable com Gatekeeper';
      $('#lastCapture').textContent = `${agent.name}: ${mode}. Funções allowlisted: ${functions.join(', ') || 'nenhuma'}. Ações: ${actions.join(', ')}. Paper trade permanece ativo.`;
    });
  });
  document.querySelectorAll('.agent-glm-review').forEach((button) => {
    button.addEventListener('click', async () => {
      const agent = agents.find((item) => item.id === button.dataset.agent);
      if (!agent) return;
      button.disabled = true;
      button.textContent = 'Enfileirando revisão...';
      const result = await fetch(`${API.engine}/api/agents/${encodeURIComponent(agent.id)}/glm-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reason: `Revisão advisory solicitada pelo usuário para ${agent.name || agent.id}.`,
          context: { agent_id: agent.id, implementation_state: agent.implementationState || agent.implementation_state || 'unknown' },
        }),
      }).then((response) => response.json()).catch((error) => ({ ok: false, error: error.message || 'offline' }));
      $('#lastCapture').textContent = result.ok ? `${agent.name || agent.id}: revisão GLM enfileirada (${result.status}). Nenhuma ação foi executada.` : `Revisão GLM não enfileirada: ${result.error || result.detail || 'erro'}`;
      button.disabled = false;
      button.textContent = 'Solicitar revisão GLM';
    });
  });
}

async function loadAgents() {
  const live = await getJson(`${API.engine}/api/agents`, 6000);
  if (live.ok && live.data?.ok && Array.isArray(live.data?.agents)) {
    renderAgents(live.data);
    return;
  }
  try {
    const response = await fetch('agents.json', { cache: 'no-store' });
    renderAgents(await response.json());
    $('#agentCount').textContent += ' · catálogo local';
  } catch (_) {
    $('#agentCount').textContent = 'catálogo indisponível';
    $('#agents').innerHTML = '<p class="muted">Não foi possível carregar o catálogo do Engine nem o catálogo local.</p>';
  }
}

async function refreshAdmin() {
  const [result, agentResult] = await Promise.all([
    getJson(`${API.engine}/api/admin/health`, 5000),
    getJson(`${API.engine}/api/agents/glm/status`, 5000),
  ]);
  const state = result.ok && result.data?.ok;
  $('#adminState').className = `pill ${state ? 'online' : 'offline'}`;
  $('#adminState').textContent = state ? 'online' : 'offline';
  if (!state) {
    $('#adminDetail').textContent = result.data?.error || 'Control plane indisponível; nenhuma modificação será executada.';
    $('#adminAudit').textContent = 'Não foi possível consultar o ledger.';
    return;
  }
  const ledger = result.data.ledger || {};
  const agentGlm = agentResult.ok && agentResult.data?.ok ? agentResult.data : {};
  $('#adminMode').textContent = result.data.mode || 'PLAN_ONLY';
  $('#adminDetail').textContent = result.data.architecture?.human_approval_required_for_mutation ? `GLM advisory ativo; fila ${agentGlm.queue_depth || 0}/${agentGlm.queue_limit || 0}; mutações exigem aprovação explícita.` : 'Verifique a política administrativa antes de continuar.';
  $('#adminAudit').textContent = JSON.stringify({ status: ledger.status, events: ledger.audit_events, hash_chain: ledger.hash_chain?.valid, tools: result.data.tools?.length || 0, agent_glm: agentGlm }, null, 2);
}

async function refreshOllama() {
  const result = await getJson('http://127.0.0.1:11434/api/tags', 3000);
  const models = Array.isArray(result.data?.models) ? result.data.models.map((model) => model.name) : [];
  const present = models.includes('glm4:9b-chat-q4_0');
  $('#ollamaState').className = `pill ${present ? 'online' : 'offline'}`;
  $('#ollamaState').textContent = present ? 'GLM-4 pronto' : (result.ok ? 'modelo ausente' : 'Ollama offline');
  $('#ollamaDetail').textContent = present ? 'Ollama respondeu e o modelo alvo está disponível.' : (result.data?.error || `Modelos disponíveis: ${models.join(', ') || 'nenhum'}`);
}

function appendChatMessage(text, sender) {
  const box = $('#glmChatBox');
  const message = document.createElement('div');
  message.className = `chat-message ${sender}`;
  message.textContent = String(text ?? '');
  box.appendChild(message);
  box.scrollTop = box.scrollHeight;
}

async function sendGlmChat(event) {
  event.preventDefault();
  const input = $('#glmChatInput');
  const button = $('#glmChatSend');
  const message = input.value.trim();
  if (!message || button.disabled) return;
  appendChatMessage(message, 'user');
  input.value = '';
  button.disabled = true;
  $('#glmChatState').className = 'pill pending';
  $('#glmChatState').textContent = 'GLM a responder';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 125000);
  let result;
  try {
    const response = await fetch(`${API.engine}/api/glm_chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      cache: 'no-store',
      signal: controller.signal,
    });
    result = { ok: response.ok, data: await response.json().catch(() => ({})) };
  } catch (error) {
    result = { ok: false, data: { error: error.name === 'AbortError' ? 'tempo limite excedido' : (error.message || 'offline') } };
  } finally {
    clearTimeout(timer);
  }
  if (result.ok && result.data?.reply) {
    appendChatMessage(result.data.reply, 'ai');
    $('#glmChatState').className = 'pill online';
    $('#glmChatState').textContent = result.data.model || 'advisor local';
  } else {
    const detail = result.data?.detail || result.data?.error || 'O Engine/GLM local não respondeu.';
    appendChatMessage(`Não foi possível obter resposta: ${typeof detail === 'string' ? detail : 'verifique o status do Engine e do Ollama.'}`, 'ai');
    $('#glmChatState').className = 'pill offline';
    $('#glmChatState').textContent = 'indisponível';
  }
  button.disabled = false;
  input.focus();
}

function bind() {
  $('#glmChatForm').addEventListener('submit', sendGlmChat);
  $('#openSokker').addEventListener('click', () => {
    if (window.chrome?.webview) window.chrome.webview.postMessage({ type: 'AURA_OPEN_SOKKERPRO' });
    else window.location.href = 'https://sokkerpro.com/';
  });
  $('#refreshStatus').addEventListener('click', async () => {
    await refreshStatus();
    await refreshOllama();
    await refreshAdmin();
    await loadAgents();
  });
}

bind();
loadAgents();
refreshStatus();
refreshOllama();
refreshAdmin();
setInterval(refreshStatus, 5000);
setInterval(refreshOllama, 10000);
setInterval(refreshAdmin, 10000);
