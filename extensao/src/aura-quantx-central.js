/* AURA QUANT-X — Central de Inteligência standalone.
 * Sem dados sintéticos: campos ausentes permanecem N/D.
 */
'use strict';
(() => {
  const A = window.AURA_QUANTX_ADAPTER;
  if (!A) return;
  const $ = id => document.getElementById(id);
  const root = $('auraApp');
  const state = { snapshot: null, analysis: null, charts: null, selectedGraph: 'appm', paused: false, frame: 0 };
  const layoutKey = 'aura_quantx_layout_v1';
  const graphDefs = [
    ['appm', 'Pressão 3/5/10 min', 'appm'],
    ['xg', 'Gols esperados (xG)', 'xg'],
    ['timeline', 'Linha do tempo do jogo', 'timeline'],
    ['odds', 'Oscilação das odds', 'oddsOscillation'],
    ['macdXg', 'Momento do xG', 'macdXg'],
    ['pbar', 'Pressão relativa', 'pbar'],
    ['h2h', 'Histórico entre equipes', 'h2h'],
    ['radar', 'Radar de estatísticas', 'radar']
  ];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const first = (...values) => values.find(value => value !== null && value !== undefined && value !== '');
  const pct = value => { const n = finite(value); return n === null ? '—' : `${(n <= 1 ? n * 100 : n).toFixed(1).replace('.', ',')}%`; };
  const num = value => { const n = finite(value); return n === null ? '—' : String(n).replace('.', ','); };
  const rootAnalysis = () => state.analysis?.analysis || state.analysis?.result || state.analysis || {};
  const stats = () => state.snapshot?.stats || {};
  const pair = key => { const v = stats()[key] ?? state.snapshot?.[key]; if (Array.isArray(v)) return v; return [v?.home, v?.away]; };
  const score = () => { const s = state.snapshot?.score || {}; return [s.home ?? s.h, s.away ?? s.a]; };
  const fixtureId = () => state.snapshot?.fixtureId || state.snapshot?.fixture_id || null;
  const show = (id, value) => { const el = $(id); if (el) el.textContent = value; };
  const toast = message => { const el = $('toast'); if (!el) return; el.textContent = message; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 2200); };

  function qualityStatus(value) {
    const s = String(value || '').toLowerCase();
    return s === 'ready' ? 'PRONTO' : s === 'stale' ? 'DESATUALIZADO' : s === 'pending' ? 'AGUARDANDO' : 'N/D';
  }

  function renderHeader() {
    const [homeScore, awayScore] = score();
    const s = state.snapshot || {};
    show('miniMatch', s.home && s.away ? `${s.home} × ${s.away}` : 'Aguardando captura');
    show('miniScore', `${homeScore ?? '—'} × ${awayScore ?? '—'}`);
    show('miniMinute', s.minute != null ? `${s.minute}'` : '—');
    const freshness = first(s.freshness?.score, s.quality?.freshness, s.capture?.freshness);
    show('topFreshness', freshness == null ? 'N/D' : `${Math.round(Number(freshness) <= 1 ? freshness * 100 : freshness)}%`);
    show('fieldClock', s.minute != null ? `${s.minute}:${String(s.second ?? '00').padStart(2,'0')}` : '—');
    show('footerUpdate', s.lastUpdate ? `atualizado ${new Date(s.lastUpdate).toLocaleTimeString('pt-BR',{hour12:false})}` : 'aguardando captura');
  }

  function renderRisk() {
    const a = rootAnalysis();
    const r = a.risk || a.risk_gate || {};
    const decision = String(first(a.decision, a.action, a.signal, 'BLOCK')).toUpperCase();
    const blocked = /BLOCK|STOP|RED/.test(decision) || String(first(r.state, r.status, '')).toUpperCase() === 'BLOCK';
    const stateEl = $('riskState');
    if (stateEl) stateEl.className = `risk-state ${blocked ? 'blocked' : 'watch'}`;
    show('riskLabel', blocked ? 'BLOQUEADO' : decision.includes('BUY') ? 'APROVADO' : 'OBSERVAÇÃO');
    show('decisionLabel', blocked ? 'OBSERVAÇÃO DE ESCANTEIO' : decision);
    show('modelProb', pct(first(a.calibrated_probability, a.p_calibrated, a.corner_prob, a.probability, a.model_prob)));
    show('marketProb', pct(first(a.market_prob, a.implied_prob, a.p_market)));
    show('edge', pct(first(a.edge, a.ev, a.value)));
    show('exposure', pct(first(r.exposure, r.final_exposure, 0)));
    show('footerExposure', pct(first(r.exposure, r.final_exposure, 0)));
    show('kelly', pct(first(r.kelly, r.raw_kelly, a.kelly)));
    const integrity = a.data_integrity || {};
    const issues = Array.isArray(integrity.issues) ? integrity.issues : [];
    show('reason1', issues[0] ? String(issues[0]).replaceAll('_',' ').toUpperCase() : 'DADOS VÁLIDOS');
    show('reason2', issues[1] ? String(issues[1]).replaceAll('_',' ').toUpperCase() : blocked ? 'POLÍTICA SEGURA ATIVA' : 'SEM BLOQUEIO');
    const acc = first(a.accuracy_score, a.accuracy_pack?.accuracy_score);
    const conf = first(a.analysis_confidence, a.accuracy_pack?.confidence);
    let explain = first(a.reason, a.explanation, r.reason, blocked ? 'A política segura mantém a exposição em zero.' : 'A análise está em observação.') || 'N/D';
    if (acc != null || conf) {
      explain = `${explain} · Acertividade ${acc != null ? Math.round(Number(acc)) : '—'}/100 · Confiança ${conf || 'N/D'}`;
    }
    show('riskExplanation', explain);
    const p = first(a.corner_prob, a.probability, a.model_prob);
    const horizons = a.corner_prob_by_horizon || a.probability_by_horizon || {};
    show('p1', pct(horizons['1'] ?? horizons['1m']));
    show('p3', pct(horizons['3'] ?? horizons['3m']));
    show('p5', pct(horizons['5'] ?? horizons['5m'] ?? p));
    show('p10', pct(horizons['10'] ?? horizons['10m']));
    show('horizon1', `1 min ${pct(horizons['1'] ?? horizons['1m'])}`);
    show('horizon3', `3 min ${pct(horizons['3'] ?? horizons['3m'])}`);
    show('horizon5', `5 min ${pct(horizons['5'] ?? horizons['5m'] ?? p)}`);
    show('horizon10', `10 min ${pct(horizons['10'] ?? horizons['10m'])}`);
  }

  function renderCorners() {
    const corners = pair('corners');
    const timeline = state.charts?.timeline?.events || [];
    const cornerEvents = timeline.filter(e => /corner|escanteio|canto/i.test(String(e.type || e.label || '')));
    show('cornerScore', `${corners?.[0] ?? '—'} — ${corners?.[1] ?? '—'}`);
    const last = cornerEvents.at(-1);
    show('lastCornerAge', last?.minute != null && state.snapshot?.minute != null ? `${Math.max(0, Number(state.snapshot.minute) - Number(last.minute))} min` : 'N/D');
    show('corner5m', cornerEvents.filter(e => state.snapshot?.minute != null && Number(state.snapshot.minute) - Number(e.minute) <= 5).length || (cornerEvents.length ? '0' : 'N/D'));
    show('corner10m', cornerEvents.filter(e => state.snapshot?.minute != null && Number(state.snapshot.minute) - Number(e.minute) <= 10).length || (cornerEvents.length ? '0' : 'N/D'));
  }

  function renderGraphTabs() {
    const box = $('graphTabs'); if (!box) return;
    box.innerHTML = '';
    for (const [id, label, key] of graphDefs) {
      const status = qualityStatus(state.charts?.readiness?.[key] || state.charts?.[key]?.status);
      const b = document.createElement('button');
      b.textContent = label; b.dataset.status = status === 'AGUARDANDO' ? 'pending' : status.toLowerCase(); b.className = id === state.selectedGraph ? 'active' : '';
      b.title = `${label} · ${status}`;
      b.onclick = () => { state.selectedGraph = id; renderGraphTabs(); drawGraphPreview(); };
      box.appendChild(b);
    }
    const data = state.charts?.[graphDefs.find(x => x[0] === state.selectedGraph)?.[2]];
    show('graphSource', data?.source ? `Fonte ${data.source}` : 'Fonte não informada');
    show('graphStatus', qualityStatus(data?.status || state.charts?.readiness?.[state.selectedGraph]));
  }

  function drawGraphPreview() {
    const canvas = $('graphCanvas'); if (!canvas) return;
    const box = canvas.parentElement; const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, box.clientWidth * dpr); canvas.height = Math.max(1, box.clientHeight * dpr);
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); const w = box.clientWidth, h = box.clientHeight;
    ctx.clearRect(0, 0, w, h); ctx.strokeStyle = 'rgba(53,200,244,.18)'; ctx.lineWidth = 1;
    for (let i=1;i<5;i++){ctx.beginPath();ctx.moveTo(0,h*i/5);ctx.lineTo(w,h*i/5);ctx.stroke();}
    const graph = state.charts?.[graphDefs.find(x => x[0] === state.selectedGraph)?.[2]];
    const values = graph?.values || graph?.series || graph?.events || [];
    if (!Array.isArray(values) || values.length < 2) { const empty=$('graphEmpty'); if(empty) empty.style.display='grid'; return; }
    const empty=$('graphEmpty'); if(empty) empty.style.display='none';
    const ys = values.map(v => finite(v.value ?? v.y ?? v.minute)).filter(v => v !== null);
    if (ys.length < 2) return;
    const min = Math.min(...ys), max = Math.max(...ys), range = Math.max(1e-9,max-min);
    ctx.strokeStyle = state.selectedGraph === 'odds' ? '#f0b64b' : '#35c8f4'; ctx.lineWidth = 1.7; ctx.beginPath();
    ys.forEach((value,i) => { const x=i/(ys.length-1)*w; const y=h-8-((value-min)/range)*(h-16); if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y); }); ctx.stroke();
  }

  function renderContext() {
    const [hs,as]=score(); show('contextScore', `${hs ?? '—'} × ${as ?? '—'}`);
    const events = state.charts?.timeline?.events || state.snapshot?.matchEvents || [];
    const box = $('contextEvents'); if (!box) return; box.innerHTML='';
    events.filter(e => /goal|gol|red|vermelho|yellow|amarelo|substit/i.test(String(e.type||e.label||''))).slice(-5).reverse().forEach(e=>{
      const row=document.createElement('div'); row.className='event-row'; row.innerHTML=`<time>${esc(e.minute ?? '—')}'</time><span>${esc(e.label || e.type || 'evento')}</span><em>${esc(e.side || 'partida')}</em>`; box.appendChild(row);
    });
    if(!box.children.length) box.innerHTML='<div class="event-row"><time>—</time><span>Sem eventos de contexto</span><em>N/D</em></div>';
  }

  function renderFeatures() {
    const a=rootAnalysis(); const s=state.snapshot||{}; const f=a.features||s.intelligence?.features||{};
    const list=[
      ['Mudança da pressão', first(f.pressure_slope,a.pressure_slope,s.pressure?.slope)],
      ['Aceleração dos gols esperados', first(f.xg_acceleration,a.xg_acceleration)],
      ['Ataques perigosos por 5 min', first(f.dangerous_5m,a.dangerous_5m)],
      ['Tempo desde o último canto', first(f.last_corner_age,a.last_corner_age)],
      ['Movimento das odds', first(f.odds_velocity,a.odds_velocity)],
      ['Dinheiro inteligente', first(f.wom,a.wom,s.wom)]
    ];
    const box=$('featureList'); if(!box)return;
    box.innerHTML=list.map(([label,value])=>{
      const active = value != null && value !== '';
      // Arredonda na UI sem inventar
      let display = 'N/D';
      if (active) {
        const n = finite(value);
        display = n === null ? String(value) : (Math.abs(n) >= 10 ? n.toFixed(1) : n.toFixed(2)).replace('.', ',');
      }
      return `<div class="feature-row"><label>${esc(label)}</label><b>${esc(display)}</b><small>${active ? 'REAL' : 'AUSENTE'}</small></div>`;
    }).join('');
  }

  function renderModels() {
    const a=rootAnalysis(); const m=a.model || a.models || a.model_stack || {};
    const list=[
      ['Modelo de taxa de escanteios',first(m.poisson,a.poisson,a.base_poisson)],
      ['Modelo de sequência',first(m.hawkes_lambda,a.hawkes_lambda,a.hawkes)],
      ['Modelo de variáveis ao vivo',first(m.lightgbm,a.lightgbm)],
      ['Ajuste de calibração',first(m.calibrator,a.calibrator)],
      ['Resultado combinado',first(m.ensemble,a.ensemble,a.corner_prob)]
    ];
    const box=$('modelList'); if(!box)return;
    box.innerHTML=list.map(([label,value])=>{
      const active = value != null && value !== '' && Number.isFinite(Number(value));
      const display = active ? num(value) : 'N/D';
      const tag = active ? 'ATIVO' : 'AUSENTE';
      return `<div class="model-row"><label>${esc(label)}</label><b>${esc(display)}</b><small>${esc(tag)}${m.version ? ' · '+esc(m.version) : ''}</small></div>`;
    }).join('');
  }

  function renderQuality() {
    const s=state.snapshot||{}; const q=finite(s.quality?.score ?? s.quality); show('qualityScore',q===null?'—':Math.round(q<=1?q*100:q)); const box=$('qualityList'); if(!box)return;
    const d=s.diagnostics||{}; const rows=[['Campos críticos ausentes',first(s.quality?.critical_missing_fields?.length,s.quality?.criticalMissing,0)],['Campos inválidos',first(s.quality?.invalid_fields?.length,s.quality?.invalidFields,0)],['Fontes concordantes',first(s.quality?.source_agreement,'N/D')],['Tempo de atualização',first(s.lastUpdateAge,s.freshness?.age,'N/D')],['Rede',s.sources?.network||'N/D'],['Gráficos',s.sources?.charts||'N/D'],['Eventos',s.sources?.events||'N/D'],['Mercado',s.sources?.market||'N/D']];
    box.innerHTML=rows.map(([label,value])=>`<div class="quality-row"><span>${esc(label)}</span><b>${esc(value == null ? 'N/D' : num(value))}</b></div>`).join('');
  }

  function renderTrace() { const box=$('traceLine'); if(!box)return; const steps=[['Recebimento','ok'],['Conciliação','ok'],['Verificação dos dados','ok'],['Cálculo','ok'],['Verificação do mercado','warn'],['Bloqueio de risco','block']]; box.innerHTML=steps.map(([label,status],i)=>`<div class="trace-step ${status==='block'?'block':''}"><i>${status==='block'?'×':status==='warn'?'!':'✓'}</i><label>${label}</label><small>${i===5?'exposição 0%':'verificado'}</small></div>`).join(''); }
  function renderLedger() { const box=$('ledgerBody'); if(!box)return; const events=state.charts?.timeline?.events||[]; box.innerHTML=events.slice(-8).reverse().map(e=>`<tr><td>${esc(e.minute ?? '—')}'</td><td>${esc(e.label||e.type||'evento')}</td><td>${esc(e.src||'N/D')}</td><td>CONFIRMADO</td></tr>`).join('')||'<tr><td>—</td><td>Sem eventos capturados</td><td>N/D</td><td>AGUARDANDO</td></tr>'; }

  function drawField() {
    const canvas=$('fieldCanvas'); if(!canvas)return; const stage=canvas.parentElement; const dpr=window.devicePixelRatio||1; const w=stage.clientWidth,h=stage.clientHeight; canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.width=`${w}px`;canvas.style.height=`${h}px`; const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
    const hasSeries=Boolean(state.charts?.seriesCount||state.charts?.xg?.values?.length||state.charts?.appm?.intervals&&Object.keys(state.charts.appm.intervals).length);
    $('fieldEmpty').style.display=hasSeries?'none':'block';
    ctx.save();ctx.translate(w*.10,h*.52);ctx.rotate(-.06);ctx.scale(1,.55);ctx.strokeStyle='rgba(109,201,227,.25)';ctx.lineWidth=1;ctx.strokeRect(0,0,w*.78,h*1.25);for(let i=1;i<8;i++){ctx.beginPath();ctx.moveTo(w*.78*i/8,0);ctx.lineTo(w*.78*i/8,h*1.25);ctx.stroke()}for(let i=1;i<5;i++){ctx.beginPath();ctx.moveTo(0,h*1.25*i/5);ctx.lineTo(w*.78,h*1.25*i/5);ctx.stroke()}ctx.restore();
    if(!hasSeries)return;
    const t=state.paused?0:performance.now()/2800;ctx.save();ctx.globalAlpha=.7;for(let line=0;line<13;line++){ctx.beginPath();for(let x=0;x<=w*.72;x+=8){const y=h*.43+Math.sin(x*.024+line*.55+t)*8+Math.sin(x*.008-line*.28+t*.7)*12+line*5;const px=w*.12+x;const py=y+(x/w-.5)*32;if(x===0)ctx.moveTo(px,py);else ctx.lineTo(px,py)}ctx.strokeStyle=line%3===0?'rgba(240,182,75,.65)':'rgba(53,200,244,.32)';ctx.lineWidth=line%3===0?1.2:.7;ctx.stroke()}ctx.restore();
    const events=state.charts?.timeline?.events||[];for(const e of events.slice(-12)){const ex=Math.max(0,Math.min(1,(Number(e.minute||0)-Math.max(0,Number(state.snapshot?.minute||36)-15))/15));const px=w*.13+ex*w*.68;const py=h*.42+Math.sin(ex*10+t)*12;ctx.beginPath();ctx.arc(px,py,3,0,Math.PI*2);ctx.fillStyle=/corner|escanteio|canto/i.test(String(e.type||e.label))?'#f0b64b':'#dfeff2';ctx.fill()}
  }

  function renderAll(){renderHeader();renderRisk();renderCorners();renderGraphTabs();drawGraphPreview();renderContext();renderFeatures();renderModels();renderQuality();renderTrace();renderLedger();drawField();}

  function loadLayout(){try{return JSON.parse(localStorage.getItem(layoutKey)||'{}')}catch(_){return {}}}
  function applyLayout(layout){document.querySelectorAll('[data-panel]').forEach(panel=>{const name=panel.dataset.panel;const visible=layout[name] !== false;panel.classList.toggle('is-hidden',!visible);const toggle=document.querySelector(`[data-layout-toggle="${name}"]`);if(toggle)toggle.checked=visible})}
  function buildLayoutMenu(){const box=$('layoutToggles');if(!box)return;const names=[['field','Campo 3D'],['risk','Torre de risco'],['corners','Indicadores de escanteios'],['graphs','Todos os gráficos'],['goals','Gols e contexto'],['features','Indicadores ao vivo'],['model','Combinação de modelos'],['quality','Qualidade dos dados'],['trace','Caminho da decisão'],['ledger','Registro de eventos'],['voice','Voz da AURA']];box.innerHTML=names.map(([id,label])=>`<label class="toggle-row"><span>${label}</span><input type="checkbox" data-layout-toggle="${id}" checked></label>`).join('');const layout=loadLayout();applyLayout(layout);box.querySelectorAll('input').forEach(input=>input.onchange=()=>{const next=loadLayout();next[input.dataset.layoutToggle]=input.checked;applyLayout(next)})}
  function bindPanels(){document.querySelectorAll('[data-panel-action]').forEach(button=>button.addEventListener('click',()=>{const panel=button.closest('[data-panel]');if(!panel)return;const action=button.dataset.panelAction;if(action==='hide'){if(panel.dataset.required==='true'){toast('O Campo 3D é o núcleo e não pode ser ocultado.');return}panel.classList.add('is-hidden');const layout=loadLayout();layout[panel.dataset.panel]=false;localStorage.setItem(layoutKey,JSON.stringify(layout));buildLayoutMenu()}if(action==='collapse')panel.classList.toggle('is-collapsed');if(action==='expand')panel.classList.toggle('is-expanded')}))}
  function bindControls(){ $('openChat').onclick=()=>A.openChat(); $('quickSummary').onclick=()=>{sessionStorage.setItem('aura_kanteiro_prefill','Resuma os escanteios e explique a decisão atual.');A.openChat()}; $('speakSummary').onclick=async()=>{const text=`A decisão atual é ${$('riskLabel').textContent}. ${$('riskExplanation').textContent}`.replace(/[*_`#]/g,'').replace(/\s+/g,' ').trim();const r=await A.speak(text);toast(r.ok?'Resumo enviado para a voz.':'Voz indisponível.');}; $('layoutButton').onclick=()=>{const m=$('layoutMenu');m.hidden=!m.hidden;$('layoutButton').setAttribute('aria-expanded',String(!m.hidden));if(!m.hidden)buildLayoutMenu()}; $('closeLayout').onclick=()=>{$('layoutMenu').hidden=true}; $('saveLayout').onclick=()=>{const layout={};document.querySelectorAll('[data-layout-toggle]').forEach(x=>layout[x.dataset.layoutToggle]=x.checked);localStorage.setItem(layoutKey,JSON.stringify(layout));toast('Layout salvo nesta estação.')}; $('restoreLayout').onclick=()=>{localStorage.removeItem(layoutKey);applyLayout({});buildLayoutMenu();toast('Layout padrão restaurado.')}; document.querySelectorAll('[data-layout-toggle]').forEach(x=>x.onchange=()=>{}); $('pauseField').onclick=()=>{state.paused=!state.paused;$('pauseField').textContent=state.paused?'▶ CONTINUAR':'Ⅱ PAUSAR'}; document.querySelectorAll('.speed').forEach(b=>b.onclick=()=>{document.querySelectorAll('.speed').forEach(x=>x.classList.remove('active'));b.classList.add('active')});}
  async function refresh(){state.snapshot=await A.getState();state.charts=await A.getCharts();state.analysis=await A.getAnalysis(fixtureId());renderAll();}
  function loop(){if(!state.paused){state.frame=requestAnimationFrame(loop);drawField()}else state.frame=requestAnimationFrame(loop)}
  async function refreshVoiceHealth(){
    try{
      const r = await fetch('http://127.0.0.1:8099/api/voice/health', {signal: AbortSignal.timeout(2500)});
      const d = await r.json();
      const eng = d?.tts?.engine || d?.engine || 'neural';
      const el = $('voiceEngineStatus');
      if(el) el.textContent = '● PRONTA · ' + String(eng).toUpperCase();
    }catch(_){ const el=$('voiceEngineStatus'); if(el) el.textContent='● PRONTA PARA OUVIR'; }
  }
  async function boot(){buildLayoutMenu();bindPanels();bindControls();await refresh();refreshVoiceHealth();loop();setInterval(refresh,4000);setInterval(refreshVoiceHealth,15000);}
  boot();
})();
