'use strict';
const ENGINE='http://127.0.0.1:8765';
let lastCall=0,lastFixture=null,lastState=null,lastAnalysis=null;
const chatHistoryByFixture=Object.create(null);
let lastSpokenReply='';
function currentHistoryKey(){return lastFixture?('fx:'+String(lastFixture)):'nofixture'}
function historyFor(key){if(!chatHistoryByFixture[key])chatHistoryByFixture[key]=[];return chatHistoryByFixture[key]}
function detectVoiceRequest(text){
  const raw=String(text||'').trim();
  const re=/(?:responda|responde|responder|fale|falar|leia|ler|diga|dizer)\s+(?:isso\s+)?(?:com|por|em)\s+(?:voz|audio|áudio)|(?:agora\s+)?(?:com|por|em)\s+voz(?:\s+alta)?|\bouvir\s+(?:a\s+)?resposta|^\/(?:voz|speak|tts)\b|^(?:voz|speak)$/i;
  const speak=re.test(raw);
  const cleaned=speak?raw.replace(re,' ').replace(/\s+/g,' ').replace(/^[\s,.;:-]+|[\s,.;:-]+$/g,''):raw;
  return {speak,cleaned};
}
let auraAudioEl=null,auraAudioUnlocked=false;
function unlockAuraAudio(){
  if(auraAudioUnlocked) return;
  try{
    if(!auraAudioEl) auraAudioEl=new Audio();
    auraAudioEl.muted=true;
    auraAudioEl.src='data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=';
    const p=auraAudioEl.play();
    if(p&&p.then)p.then(()=>{auraAudioEl.pause();auraAudioEl.muted=false;auraAudioUnlocked=true}).catch(()=>{});
    else auraAudioUnlocked=true;
  }catch(_){}
  try{if(typeof window.voicePrimeAudio==='function')window.voicePrimeAudio()}catch(_){}
}
function playDataAudio(b64,mime){
  return new Promise((resolve,reject)=>{
    if(!auraAudioEl)auraAudioEl=new Audio();
    const el=auraAudioEl;
    el.muted=false;
    el.onended=()=>resolve(true);
    el.onerror=()=>reject(new Error('audio_element_error'));
    el.src='data:'+(mime||'audio/mpeg')+';base64,'+b64;
    const p=el.play();
    if(p&&p.catch)p.catch(reject);
  });
}
function speakBrowserFallback(){
  try{/* native TTS removed */}catch(_){}
  return Promise.resolve(false);
}
async function speakViaTtsRouter(text){
  const clean=String(text||'').replace(/\[[^\]]+\]/g,'').replace(/[*_`#]/g,'').replace(/\s+/g,' ').trim();
  if(!clean)return {ok:false,error:'texto vazio'};
  unlockAuraAudio();
  if(typeof window.auraSpeakText==='function'){
    const ok=await window.auraSpeakText(clean);
    if(ok) return {ok:true,via:'kanteiro_neural'};
  }
  try{
    const r=await fetch('http://127.0.0.1:8099/api/voice/neural',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:clean,voice:'pt-BR-AntonioNeural'}),signal:AbortSignal.timeout(20000)});
    const data=await r.json().catch(()=>({}));
    if(!r.ok||!data?.audio_base64)throw new Error(data?.error||'neural_tts_fail');
    if(data.gender && data.gender!=='male')throw new Error('tts_gender_not_male');
    if(data.fallback && data.fallback!=='disabled')throw new Error('tts_fallback_rejected');
    if(/(Francisca|gtts|google)/i.test(`${data.voice||''} ${data.engine||''}`))throw new Error('tts_legacy_voice_rejected');
    await playDataAudio(data.audio_base64, (data.format||data.audio_format)==='wav'?'audio/wav':'audio/mpeg');
    return {ok:true,via:'voice_8099'};
  }catch(e){
    const fb=await speakBrowserFallback(clean);
    return fb?{ok:true,via:'browser_fallback'}:{ok:false,error:String(e.message||e)};
  }
}
function localSpeakSummary(){
  if(!lastState?.fixtureId) return 'Hálem, ainda não há partida capturada. Quando o snapshot chegar, eu falo somente os dados observados.';
  const [sh,sa]=scoreObj(lastState);
  const corn=statPair(lastState,'corners');
  const xg=statPair(lastState,'xg');
  const nd=v=>v==null||v===''?'não há dado':String(v);
  const parts=[
    `Hálem, partida ${lastState.home||'casa'} contra ${lastState.away||'visitante'}, fixture ${lastState.fixtureId}.`,
    `Minuto ${nd(lastState.minute)}, placar ${nd(sh)} a ${nd(sa)}.`,
    `Escanteios observados: ${nd(corn?.[0])} a ${nd(corn?.[1])}.`,
    `xG observado: ${nd(xg?.[0])} e ${nd(xg?.[1])}.`
  ];
  const h2h=lastState.h2h;
  const h2hGames=h2h?.summary?.total||h2h?.parameters?.matches||(h2h?.tables||[]).length||null;
  if(h2h&&h2h.captured&&h2hGames){
    parts.push(`H2H capturado: ${h2hGames} jogos. Sem média inventada.`);
  }else{
    parts.push('Não há médias históricas neste contexto.');
  }
  if(lastAnalysis?.decision) parts.push(`Decisão do motor: ${lastAnalysis.decision}.`);
  return parts.join(' ');
}
const $=id=>document.getElementById(id);
const eventLog=$('eventLog'),statusEl=$('status');
function num(v){return Number.isFinite(Number(v))?Number(v):null}
function pct(v){const n=num(v);if(n===null)return '—';return `${Math.round(n<=1?n*100:n)}%`}
function setBar(id,v){const n=num(v);const x=n===null?0:Math.max(0,Math.min(100,n<=1?n*100:n));$(id).style.width=x+'%';return x}
function append(sender,text){if(!eventLog)return;const d=document.createElement('div');d.className='msg '+sender;d.textContent=text;eventLog.appendChild(d);eventLog.scrollTop=eventLog.scrollHeight;while(eventLog.children.length>100)eventLog.removeChild(eventLog.firstChild)}
function scoreObj(st){const s=st?.score||{};return [s.home??s.h,s.away??s.a]}
function statPair(st,key){const v=st?.stats?.[key]??st?.[key];if(Array.isArray(v))return v;return [v?.home,v?.away]}
function first(...xs){return xs.find(x=>x!==undefined&&x!==null&&x!=='')}
const SERVICE_COMMANDS={Engine:'RECUPERAR_AURA_SERVICOS.bat ou engine\\iniciar_engine.bat',Bridge:'RECUPERAR_AURA_SERVICOS.bat ou bridge\\iniciar_bridge.bat',Voice:'RECUPERAR_AURA_SERVICOS.bat ou bridge\\iniciar_voz.bat'};
function serviceError(error,service='Engine',url=ENGINE){
 const raw=String(error?.message||error||'erro desconhecido');
 const low=raw.toLowerCase();
 const endpoint=String(url||'').replace(/^https?:\/\//,'');
 const httpStatus=Number(error?.httpStatus||0);
 if(httpStatus && httpStatus < 500){
  return `[Engine] ${raw}`;
 }
 let cause=low.includes('abort')||low.includes('timeout')?'tempo limite excedido; o processo pode estar travado ou ainda carregando':(low.includes('failed to fetch')||low.includes('networkerror')||low.includes('econnrefused')||low.includes('connection refused')?'nenhum processo respondeu nessa porta; serviço parado, encerrado ou bloqueado pelo Windows':raw);
 return `[${service} OFFLINE] ${endpoint} · ${cause}. Comando: ${SERVICE_COMMANDS[service]||'RECUPERAR_AURA_SERVICOS.bat'}`;
}
const ACTION_ALIASES={
 '/analisar':'ANALYZE',analisar:'ANALYZE',analyze:'ANALYZE','/analyze':'ANALYZE',analise:'ANALYZE','/analise':'ANALYZE',
 '/risk':'SIMULATE_RISK',risk:'SIMULATE_RISK','/why':'EXPLAIN_PRESSURE',why:'EXPLAIN_PRESSURE',
 '/market':'SHOW_MARKET',market:'SHOW_MARKET','/data':'SHOW_DATA','/refresh':'REFRESH_GAME'
};
function normalizeActionCommand(cmd){
 const raw=String(cmd||'').trim();
 const key=raw.toLowerCase();
 if(ACTION_ALIASES[key]) return ACTION_ALIASES[key];
 return raw.replace(/^\//,'').toUpperCase().replace(/\s+/g,'_');
}
async function engine(path,body){
 const url=ENGINE+path;
 const ctrl=typeof AbortController!=='undefined'?new AbortController():null;
 const isChat=String(path||'').indexOf('/api/trader/chat')>=0;
 const timer=ctrl?setTimeout(()=>ctrl.abort(),body===undefined?5000:(isChat?45000:8000)):null;
 const opt=body===undefined?{method:'GET'}:{method:'POST',headers:{'Content-Type':'application/json','X-CornerAI':'quant-terminal'},body:JSON.stringify(body)};
 if(ctrl)opt.signal=ctrl.signal;
 try{
  const r=await fetch(url,opt);const data=await r.json().catch(()=>({}));
  if(!r.ok){const e=new Error(`${data.error||`HTTP ${r.status}`} · endpoint ${url}`);e.httpStatus=r.status;throw e}
  return data;
 }catch(e){
  if(e && e.httpStatus){
   const wrapped=new Error(serviceError(e,'Engine',url));
   wrapped.httpStatus=e.httpStatus;
   throw wrapped;
  }
  throw new Error(serviceError(e,'Engine',url));
 }finally{if(timer)clearTimeout(timer)}
}
async function getState(){try{const r=await chrome.runtime.sendMessage({type:'GET_DIAGNOSTICS'});return r?.state||null}catch(e){return null}}

/* ========================= PAINEL (estado / análise / risco) ========================= */
function normalizeAnalysis(a,st){const root=a?.analysis||a?.result||a||{};const market=first(root.market,root.market_name,root.best_market,root.signal?.market);const p=first(root.corner_prob,root.probability,root.model_prob,root.p_model);const pm=first(root.market_prob,root.implied_prob,root.p_market);const edge=first(root.edge,root.ev,root.value);const unc=first(root.uncertainty,root.risk?.uncertainty,root.confidence_interval);const decision=String(first(root.decision,root.action,root.signal,'AGUARDA')).toUpperCase();const pressure=first(root.pressure,root.pressure_score,root.metrics?.pressure,st?.pressure?.score);const momentum=first(root.momentum,root.momentum_score,root.metrics?.momentum);const regime=first(root.regime,root.regime_name,root.market_regime);const risk=root.risk||{};const integrity=root.data_integrity||{};const kills=Array.isArray(root.skill_kills)?root.skill_kills.join(', '):'';const integrityReason=Array.isArray(integrity.issues)&&integrity.issues.length?`integridade: ${integrity.issues.join(', ')}`:'';const reason=first(root.reason,root.explanation,root.why,risk.reason,root.risk_gate?.detail,integrityReason,kills,decision==='BLOCK'?'gate fail-closed ativo; nenhuma entrada autorizada.':'Sem justificativa retornada pelo motor.');return {market,p,pm,edge,unc,decision,pressure,momentum,regime,risk,reason}}
function renderState(st){
  const prevFx=lastFixture;
  lastState=st;
  if(st?.fixtureId){lastFixture=String(st.fixtureId);try{window.lastFixture=lastFixture}catch(_){}}
  if(prevFx && lastFixture && String(prevFx)!==String(lastFixture)){
    chatHistory=historyFor(currentHistoryKey());
    lastSpokenReply='';
    LIVE_EVENT_SEEN.clear();
    liveEventsPrimed=false;
  }
  if(!st){$('match').textContent='AGUARDANDO CAPTURA';$('fixture').textContent='fixture —';$('freshness').textContent='STALE';$('freshness').className='fresh stale';$('score').textContent='— × —';$('minute').textContent='—';updateChatContext();return}
 const [sh,sa]=scoreObj(st);$('match').textContent=`${st.home||'?'}  vs  ${st.away||'?'}`;$('fixture').textContent=`fixture ${st.fixtureId||'—'}`;$('score').textContent=`${sh??'—'} × ${sa??'—'}`;$('minute').textContent=st.minute!=null?`${st.minute}${st.extraMinute?`+${st.extraMinute}`:''}'`:'—';$('source').textContent=`Fonte ${st.lastSnapshotSource||'—'}`;
 const fresh=first(st.freshness?.score,st.quality?.freshness,st.capture?.freshness);const f= fresh===null||fresh===undefined?null:(Number(fresh)<=1?Number(fresh)*100:Number(fresh));$('freshVal').textContent=f===null?'—':Math.round(f);setBar('freshBar',f);const freshOk=st.liveStatus==='live'||(f!==null&&f>=70);$('freshness').textContent=freshOk?'FRESH':'STALE';$('freshness').className='fresh '+(freshOk?'fresh':'stale');
 const appm=statPair(st,'appm'),xg=statPair(st,'xg'),corn=statPair(st,'corners');$('appm').textContent=`${appm?.[0]??'—'} | ${appm?.[1]??'—'}`;$('xg').textContent=`${xg?.[0]??'—'} | ${xg?.[1]??'—'}`;$('corners').textContent=`${corn?.[0]??'—'} | ${corn?.[1]??'—'}`;const q=num(st.quality?.score??st.quality);$('quality').textContent=q===null?'0%':pct(q);$('eventCount').textContent=`${st.eventCount||st.cornerEventCount||0} eventos`;
 updateChatContext();
 announceLiveEvents(st);
}
function renderAnalysis(a){lastAnalysis=normalizeAnalysis(a,lastState);const n=lastAnalysis;$('marketName').textContent=n.market||'Nenhum mercado validado';$('modelProb').textContent=pct(n.p);$('marketProb').textContent=pct(n.pm);$('edge').textContent=pct(n.edge);$('uncertainty').textContent=pct(n.unc);$('reason').textContent=n.reason;setBar('pressureBar',n.pressure);setBar('momentumBar',n.momentum);$('pressureVal').textContent=n.pressure==null?'—':Math.round(n.pressure<=1?n.pressure*100:n.pressure);$('momentumVal').textContent=n.momentum==null?'—':Math.round(n.momentum<=1?n.momentum*100:n.momentum);$('regime').textContent=`REGIME ${n.regime||'—'}`;$('regime').className='badge '+(n.regime?'warn':'neutral');const d=$('decision');d.textContent=n.decision;d.className='decision '+(/BLOCK|NO|STOP|RED/.test(n.decision)?'block':/ENTRA|GO|VALID|EXEC/.test(n.decision)?'go':'wait');const risk=n.risk||{};$('riskState').textContent=first(risk.state,risk.status,n.decision.match(/BLOCK|AGUARDA|ENTRA/)?.[0],'BLOCK');$('riskState').className='badge '+(/BLOCK|STOP/.test($('riskState').textContent)?'danger':'neutral');$('exposure').textContent=pct(first(risk.exposure,risk.final_exposure,0));$('kelly').textContent=pct(first(risk.kelly,risk.raw_kelly));$('correlation').textContent=first(risk.correlation,risk.correlation_state,'—');$('riskReason').textContent=first(risk.reason,risk.explanation,'Fail-closed ativo até validação.');updateChatContext();announceOpportunity(n);}
function announceOpportunity(n){
  if(!n)return;
  const sig=[n.decision,n.edge,n.regime].join('|');
  if(sig===lastDecisionSig)return;
  const prev=lastDecisionSig;
  lastDecisionSig=sig;
  if(!prev)return;
  const go=/ENTRA|GO|VALID|EXEC|BUY/.test(String(n.decision||''));
  const edge=num(n.edge);
  if(!go && !(edge!=null && edge>0)) return;
  const text=`Hálem, oportunidade no radar. Decisão ${n.decision||'N/D'}. Edge ${edge==null?'N/D':Math.round(edge<=1?edge*100:edge)+'%'}. ${n.reason||'Sem narrativa extra.'}`;
  addBubble('ai',text);
  lastSpokenReply=text;
  speakNow(voiceSummary(text));
}
function renderActions(ui,targetId='quick'){const q=$(targetId);if(!q)return;q.innerHTML='';for(const a of (ui?.actions||[])){const b=document.createElement('button');b.textContent=a.label||a.id;b.onclick=()=>targetId==='chatChips'?sendChat(a.command):runAction(a.command,a.label||a.id);q.appendChild(b)}}
async function refresh(){const st=await getState();renderState(st);if(!st?.fixtureId){lastFixture=null;return st}lastFixture=String(st.fixtureId);try{const a=await engine('/api/analysis/'+encodeURIComponent(lastFixture));renderAnalysis(a)}catch(e){const msg=String(e.message||e);$('decision').textContent='ENGINE OFF';$('decision').className='decision block';$('marketName').textContent='Análise indisponível';$('reason').textContent=msg;const now=Date.now();if(!refresh._lastErrorAt||now-refresh._lastErrorAt>10000){append('err',msg);refresh._lastErrorAt=now}}return st}
async function runAction(command,label){try{await refresh();const r=await engine('/api/trader/action',{command:normalizeActionCommand(command),fixtureId:lastFixture});append('sys',`${label} → ${r.reply||JSON.stringify(r.analysis||r)}`);if(r.analysis)renderAnalysis(r.analysis)}catch(e){append('err',String(e.message||e))}}
$('btnSnapshot').onclick=async()=>{const st=await refresh();if(!st?.fixtureId){append('err','Sem partida capturada');return}append('sys',JSON.stringify({fixtureId:st.fixtureId,home:st.home,away:st.away,score:st.score,minute:st.minute,corners:st.stats?.corners,xg:st.stats?.xg},null,0))};
async function feedback(correct){await refresh();if(!lastFixture){append('err','Sem fixture');return}try{const r=await engine('/api/feedback',{fixtureId:lastFixture,correct,note:correct?'user_ok':'user_miss'});append('sys',(correct?'GREEN':'RED')+' registrado · '+JSON.stringify(r.weights||{}));}catch(e){append('err',String(e.message||e))}}
$('btnAcertou').onclick=()=>feedback(true);$('btnErrou').onclick=()=>feedback(false);
$('btnTG').onclick=async()=>{await refresh();try{const r=lastFixture?await engine('/api/telegram/alert',{fixtureId:lastFixture}):await engine('/api/telegram/test',{message:'AURA test '+new Date().toLocaleTimeString()});append('sys',r.ok?'Telegram enviado':'Telegram: '+(r.error||'falhou'))}catch(e){append('err',`Telegram indisponível: ${e.message}. Verifique Engine :8765 e a configuração do Telegram.`)}};
$('btnVisao').onclick=async()=>{append('user','[Visão]');try{const r=await chrome.runtime.sendMessage({type:'CAPTURE_VISIBLE_TAB'});append(r?.ok?'sys':'err',r?.ok?'Tela capturada; dados estruturados permanecem fonte principal.':String(r?.error||'captura falhou'))}catch(e){append('err',e.message)}};
$('engineState').onclick=()=>{};
async function health(){try{const s=await engine('/api/status');$('engineState').textContent='ENGINE LIVE';$('engineState').className='badge live';const gpu=s?.gpu||s?.device||{};const gpuName=gpu.gpu_name||gpu.name||gpu.device||'';statusEl.textContent='Engine OK'+(gpuName?` · ${gpuName}`:'');if(s?.skill)statusEl.textContent+=` · Skill ${s.skill.installed?'ATIVA':'OFF'}`;if(s?.gpu) window._auraGpu=s.gpu}catch(e){$('engineState').textContent='ENGINE OFF';$('engineState').className='badge danger';statusEl.textContent=serviceError(e,'Engine',ENGINE)}}
function tick(){const d=new Date();$('clock').textContent=d.toLocaleTimeString('pt-BR',{hour12:false});$('lastUpdate').textContent=lastState?'Atualizado '+d.toLocaleTimeString('pt-BR',{hour12:false}):'—'}

/* ========================= TABS ========================= */
const tabBtnPanel=$('tabBtnPanel'),tabBtnChat=$('tabBtnChat'),tabBtnAgents=$('tabBtnAgents'),viewPanel=$('viewPanel'),viewChat=$('viewChat'),viewAgents=$('viewAgents'),chatUnread=$('chatUnread');
let activeView='panel',unreadCount=0;
function setView(v){activeView=v;const isChat=v==='chat';const isAgents=v==='agents';viewPanel.hidden=isChat||isAgents;viewChat.hidden=!isChat;viewAgents.hidden=!isAgents;tabBtnPanel.classList.toggle('active',!isChat&&!isAgents);tabBtnChat.classList.toggle('active',isChat);tabBtnAgents.classList.toggle('active',isAgents);tabBtnPanel.setAttribute('aria-selected',String(!isChat&&!isAgents));tabBtnChat.setAttribute('aria-selected',String(isChat));tabBtnAgents.setAttribute('aria-selected',String(isAgents));if(isChat){unreadCount=0;chatUnread.hidden=true;chatUnread.textContent='0';scrollChatToBottom();$('chatInput').focus()}if(isAgents)loadAgents()}
tabBtnPanel.onclick=()=>setView('panel');tabBtnChat.onclick=()=>setView('chat');tabBtnAgents.onclick=()=>setView('agents');

/* ========================= CHAT IA ========================= */
const chatScroll=$('chatScroll'),chatMessages=$('chatMessages'),chatEmpty=$('chatEmpty'),chatTyping=$('chatTyping'),chatChips=$('chatChips'),chatForm=$('chatForm'),chatInput=$('chatInput'),btnChatSend=$('btnChatSend'),btnChatClear=$('btnChatClear');
let chatHistory=[]; // [{role:'user'|'assistant',content}]
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function mdLite(raw){
  const text=String(raw??'');
  const blocks=text.split(/\n{2,}/).map(block=>{
    const lines=block.split('\n');
    const isList=lines.every(l=>/^\s*[-•]\s+/.test(l))&&lines.length>0;
    if(isList){
      const items=lines.map(l=>`<li>${inline(l.replace(/^\s*[-•]\s+/,''))}</li>`).join('');
      return `<ul>${items}</ul>`;
    }
    return `<p>${lines.map(inline).join('<br>')}</p>`;
  });
  return blocks.join('');
  function inline(s){
    let h=escapeHtml(s);
    h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
    h=h.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    return h;
  }
}
function scrollChatToBottom(){requestAnimationFrame(()=>{chatScroll.scrollTop=chatScroll.scrollHeight})}
function addBubble(role,content,{markdown=true}={}){
  chatEmpty.style.display='none';
  const row=document.createElement('div');row.className=`bubble-row role-${role}`;
  const avatar=document.createElement('span');avatar.className=`chat-avatar ${role==='user'?'user':'ai'}`;avatar.textContent=role==='user'?'EU':role==='err'?'!':'IA';
  const col=document.createElement('div');col.className='bubble-col';
  const bubble=document.createElement('div');bubble.className='bubble';
  if(markdown&&(role==='ai'||role==='sys')) bubble.innerHTML=mdLite(content); else bubble.textContent=content;
  const meta=document.createElement('div');meta.className='bubble-meta';
  const time=document.createElement('span');time.textContent=new Date().toLocaleTimeString('pt-BR',{hour12:false});
  meta.appendChild(time);
  if(role==='ai'){
    const cp=document.createElement('button');cp.className='bubble-copy';cp.textContent='copiar';cp.onclick=()=>{navigator.clipboard?.writeText(content).catch(()=>{});cp.textContent='copiado ✓';setTimeout(()=>cp.textContent='copiar',1200)};meta.appendChild(cp);
    const sp=document.createElement('button');sp.className='bubble-copy';sp.textContent='voz';sp.title='Falar esta resposta com Kanteiro Neural';sp.onclick=async()=>{sp.textContent='falando…';const r=await speakViaTtsRouter(content);sp.textContent=r.ok?'ouviu ✓':'voz falhou';setTimeout(()=>sp.textContent='voz',1600)};meta.appendChild(sp);
  }
  col.appendChild(bubble);col.appendChild(meta);
  if(role==='user'){row.appendChild(col);row.appendChild(avatar)} else {row.appendChild(avatar);row.appendChild(col)}
  chatMessages.appendChild(row);
  scrollChatToBottom();
  if(role==='ai'&&activeView!=='chat'){unreadCount++;chatUnread.hidden=false;chatUnread.textContent=String(unreadCount)}
}
function setTyping(on){chatTyping.hidden=!on;if(on)scrollChatToBottom()}
function updateChatContext(){
  const ctxDot=$('ctxDot'),ctxMatch=$('ctxMatch'),ctxMeta=$('ctxMeta');
  if(!lastState?.fixtureId){ctxMatch.textContent='Nenhuma partida capturada';ctxMeta.textContent='sem dados';ctxDot.classList.remove('live');return}
  const [sh,sa]=scoreObj(lastState);
  ctxMatch.textContent=`${lastState.home||'?'} × ${lastState.away||'?'}`;
  const q=num(lastState.quality?.score??lastState.quality);
  ctxMeta.textContent=`${sh??'—'}×${sa??'—'} · ${lastState.minute!=null?lastState.minute+"'":'—'} · qualidade ${q===null?'—':Math.round(q<=1?q*100:q)+'%'}`;
  ctxDot.classList.toggle('live',lastState.liveStatus==='live');
}
const DASH_STAT_KEYS=["attacks","dangerous","shots","shotsOn","shotsOff","corners","xg","fouls","offsides","yellow","red","subs","crosses","saves","possession"];
function compactEvents(list){
  return (list||[]).slice(-12).map(e=>({
    type:e.type||e.eventType||null,
    minute:e.minute??null,
    extra:e.extraMinute||0,
    side:e.side||null,
    team:e.team||null
  }));
}
function buildContext(){
  if(!lastState?.fixtureId)return null;
  const [sh,sa]=scoreObj(lastState);
  const stats={};
  for(const k of DASH_STAT_KEYS) stats[k]=statPair(lastState,k);
  const h2h=lastState.h2h||{};
  return {
    fixtureId:lastState.fixtureId,home:lastState.home,away:lastState.away,
    score:{home:sh,away:sa},minute:lastState.minute,extraMinute:lastState.extraMinute,liveStatus:lastState.liveStatus,
    stats,
    events:compactEvents([...(lastState.matchEvents||[]),...(lastState.cornerEvents||[])]),
    odds:{
      markets:lastState.oddsMarkets||null,
      historyCount:Array.isArray(lastState.oddsHistory)?lastState.oddsHistory.length:0,
      wom:lastState.wom||null,
      opening:lastState.openingOdds||null
    },
    statStatus:lastState.statStatus||null,
    quality:num(lastState.quality?.score??lastState.quality),
    analysis:lastAnalysis?{market:lastAnalysis.market,modelProb:lastAnalysis.p,marketProb:lastAnalysis.pm,edge:lastAnalysis.edge,decision:lastAnalysis.decision,regime:lastAnalysis.regime,risk:lastAnalysis.risk,reason:lastAnalysis.reason}:null,
    intelligence:lastState.intelligence?{
      readiness:lastState.intelligence.readiness,
      confidence:lastState.intelligence.confidence,
      momentum:lastState.intelligence.momentum,
      features:lastState.intelligence.features||null
    }:null,
    charts:lastState.charts?{activeId:lastState.charts.activeId,tabs:lastState.charts.tabs,series:(lastState.charts.series||[]).length}:null,
    h2h:h2h.captured||h2h.tables||h2h.summary?{
      fixtureId:lastState.fixtureId,
      captured:!!h2h.captured,
      games:h2h.summary?.total||h2h.parameters?.matches||(h2h.tables||[]).length||null,
      summary:h2h.summary||null,
      parameters:h2h.parameters||null,
      averages:h2h.averages||null
    }:null
  };
}
function buildSystemContext(){
  const st=lastState||{};
  const d=st.diagnostics||{};
  return {
    extension:{version:st.version||'12.7.8',view:activeView||'panel'},
    capture:{health:st.captureHealth||null,quality:st.quality||null,dataMode:st.dataMode||null,dataCompleteness:st.dataCompleteness||null,lastUpdate:st.lastUpdate||0},
    diagnostics:{networkRequests:d.networkRequests||0,networkResponses:d.networkResponses||0,persistErrors:d.persistErrors||0,staleSnapshots:d.staleSnapshots||0,sourceConflicts:d.sourceConflicts||0,lastLocalAiOk:d.lastLocalAiOk??null,lastLocalAiError:d.lastLocalAiError||null},
    sources:st.sources||null,
    intelligence:st.intelligence||null,
    webhook:st.webhook?{bridgeOffline:!!st.webhook.bridgeOffline,lastOkAt:st.webhook.lastOkAt||0,lastError:st.webhook.lastError||null,pending:st.webhook.pending||0}:null,
    recentErrors:Array.isArray(st.errors)?st.errors.slice(-5):[],
    activeFixture:st.fixtureId?{fixtureId:st.fixtureId,home:st.home,away:st.away,minute:st.minute,liveStatus:st.liveStatus}:null
  };
}
const LIVE_EVENT_SEEN=new Set();
let liveEventsPrimed=false;
let lastScoreSig='';
let lastLiveStatus='';
let lastDecisionSig='';
let lastCornerSig='';
let speakAlways=true;
try{localStorage.setItem('aura_speak_always','1')}catch(_){}
function voiceSummary(text){
  const clean=String(text||'').replace(/\s+/g,' ').trim();
  if(!clean)return '';
  const parts=clean.split(/(?<=[\.\!\?])\s+/).filter(Boolean);
  let out=parts.slice(0,2).join(' ');
  if(out.length>240) out=out.slice(0,240).replace(/\s+\S*$/,'')+'.';
  return out;
}
function eventSig(e){return [e.eventId||'',e.type||e.eventType||'',e.minute??'',e.extraMinute||0,e.side||'',e.team||''].join('|')}
function jarvisEventLine(e,st){
  const t=String(e.type||e.eventType||'').toLowerCase();
  const who=e.team||(e.side==='home'?(st.home||'casa'):e.side==='away'?(st.away||'visitante'):'');
  const min=e.minute!=null?`${e.minute}'`:'este minuto';
  if(/corner|escanteio|^esc$/.test(t)) return `Escanteio para ${who||'um dos lados'}, aos ${min}.`;
  if(/goal|gol/.test(t)) return `Gol de ${who||'alguém'}, aos ${min}.`;
  if(/red|vermelho/.test(t)) return `Vermelho para ${who||'um jogador'}, aos ${min}. Isso muda o jogo.`;
  return null;
}
function announceLiveEvents(st){
  if(!st)return;
  const evs=[...(st.matchEvents||[]),...(st.cornerEvents||[])];
  if(!liveEventsPrimed){
    evs.forEach(e=>LIVE_EVENT_SEEN.add(eventSig(e)));
    lastScoreSig=[st.score?.home??st.score?.h,st.score?.away??st.score?.a].join('x');
    lastLiveStatus=st.liveStatus||'';
    liveEventsPrimed=true;
    return;
  }
  const lines=[];
  for(const e of evs){
    const id=eventSig(e);
    if(LIVE_EVENT_SEEN.has(id)) continue;
    LIVE_EVENT_SEEN.add(id);
    const line=jarvisEventLine(e,st);
    if(line) lines.push(line);
  }
  const scoreSig=[st.score?.home??st.score?.h,st.score?.away??st.score?.a].join('x');
  if(scoreSig!==lastScoreSig && lastScoreSig){
    const [sh,sa]=scoreObj(st);
    lines.push(`Placar atualizado: ${sh??'—'} a ${sa??'—'}.`);
  }
  lastScoreSig=scoreSig;
  if((st.liveStatus||'')!==lastLiveStatus){
    if(/ft|finished|ended/.test(String(st.liveStatus||''))) lines.push('Fim de jogo. Pode baixar a guarda — com estilo.');
    lastLiveStatus=st.liveStatus||'';
  }
  const corn=statPair(st,'corners');
  const cornSig=(corn?.[0]??'x')+'x'+(corn?.[1]??'x');
  if(liveEventsPrimed && lastCornerSig && cornSig!==lastCornerSig){
    lines.push(`Cantos agora ${corn?.[0]??'N/D'} a ${corn?.[1]??'N/D'}.`);
  }
  lastCornerSig=cornSig;
  if(!lines.length) return;
  const text='Hálem, '+lines.join(' ');
  addBubble('ai',text);
  lastSpokenReply=text;
  speakNow(voiceSummary(text));
}

async function speakNow(text){
  unlockAuraAudio();
  const spoken=await speakViaTtsRouter(voiceSummary(text)||text);
  if(!spoken.ok) addBubble('err','TTS não reproduziu: '+(spoken.error||'Voice :8099. Clique em ▶ Ouvir voz e tente de novo.'));
  else if(spoken.via==='browser_fallback') addBubble('sys','Neural falhou; usei voz do navegador só neste pedido.');
  return spoken;
}
async function sendChat(text){
  const raw=String(text||'').trim();
  if(!raw)return;
  unlockAuraAudio();
  if(/sempre\s+(responda|responde|fale|falar).{0,24}voz|voz\s+sempre/i.test(raw)){
    speakAlways=true;
    try{localStorage.setItem('aura_speak_always','1')}catch(_){}
  }
  const parsed=detectVoiceRequest(raw);
  const msg=parsed.cleaned||raw;
  chatInput.value='';autoGrow();
  addBubble('user',raw,{markdown:false});
  const hist=historyFor(currentHistoryKey());
  chatHistory=hist;
  if(parsed.speak && !parsed.cleaned){
    hist.push({role:'user',content:raw});
    const summary=localSpeakSummary();
    addBubble('ai',summary);
    lastSpokenReply=summary;
    await speakNow(summary);
    return;
  }
  hist.push({role:'user',content:msg});
  btnChatSend.disabled=true;
  setTyping(true);
  try{
    await refresh();
    try{window.lastFixture=lastFixture}catch(_){}
    const data=await engine('/api/trader/chat',{message:msg,fixtureId:lastFixture,context:buildContext(),systemContext:buildSystemContext(),history:hist.slice(-12),speak:parsed.speak});
    const reply=data.reply||data.message||JSON.stringify(data);
    setTyping(false);
    addBubble('ai',reply);
    hist.push({role:'assistant',content:reply});
    lastSpokenReply=reply;
    if(window.__auraSidepanel&&typeof window.__auraSidepanel.onMotorResponse==='function'){
      const regime=/BLOCK|STOP/.test(String(data.analysis?.decision||''))?'blocked_smd':'neutral';
      window.__auraSidepanel.onMotorResponse({ui:data.ui||null,regime:regime});
    }else if(data.ui) renderActions(data.ui,'chatChips'); else renderDynamicFollowups();
    if(data.analysis) renderAnalysis(data.analysis);
    speakNow(voiceSummary(reply));
  }catch(e){
    setTyping(false);
    addBubble('err','Não consegui falar com o engine ('+ENGINE+'). '+String(e.message||e));
  }finally{
    btnChatSend.disabled=false;
  }
}
function autoGrow(){chatInput.style.height='auto';chatInput.style.height=Math.min(110,chatInput.scrollHeight)+'px'}
chatInput.addEventListener('input',autoGrow);
chatInput.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chatForm.requestSubmit()}});
chatForm.addEventListener('submit',e=>{e.preventDefault();unlockAuraAudio();sendChat(chatInput.value)});
document.addEventListener('pointerdown',unlockAuraAudio,{passive:true});
document.addEventListener('keydown',unlockAuraAudio,{passive:true});
(function bindSpeakBtn(){
  const b=$('btnChatSpeak');
  if(!b)return;
  b.onclick=async()=>{unlockAuraAudio();const t=lastSpokenReply||localSpeakSummary();addBubble('sys','Falando o estado observado…');await speakNow(t)};
})();
btnChatClear.onclick=()=>{chatMessages.innerHTML='';chatChips.innerHTML='';chatHistoryByFixture[currentHistoryKey()]=[];chatHistory=historyFor(currentHistoryKey());lastSpokenReply='';chatEmpty.style.display='';};
$('btnCtxRefresh').onclick=async()=>{const b=$('btnCtxRefresh');b.classList.add('spin');await refresh();setTimeout(()=>b.classList.remove('spin'),350)};

/* Sugestões de continuação geradas a partir do estado real da partida —
   mantêm o chat dinâmico mesmo quando o engine não manda ui.actions. */
function renderDynamicFollowups(){
  const helper=window.__auraSidepanel;
  if(helper&&typeof helper.renderDynamicFollowups==='function'){
    const n=lastAnalysis||{};
    const decision=String(n.decision||n.signal||'').toUpperCase();
    const regime=/BLOCK|STOP/.test(decision)?'blocked_smd':(/BUY|GO|VALID/.test(decision)?'high_edge':'neutral');
    helper.renderDynamicFollowups(regime,n);
    return;
  }
  const n=lastAnalysis||{};const pool=[];
  if(/BLOCK|STOP/.test(String(n.decision||'')))pool.push({label:'Por que bloqueou?',cmd:'/why'});
  if(/GO|ENTRA|VALID/.test(String(n.decision||'')))pool.push({label:'Qual o risco dessa entrada?',cmd:'/risk'});
  if(n.edge!=null)pool.push({label:'Detalhar o edge',cmd:'Explique em detalhe de onde vem esse edge e quão estável ele é.'});
  if(n.regime)pool.push({label:'Explicar o regime',cmd:`O que significa o regime ${n.regime} agora?`});
  pool.push({label:'E se o ritmo mudar?',cmd:'Se o ritmo da partida mudar nos próximos 10 minutos, como isso afeta a análise?'});
  pool.push({label:'Comparar com H2H',cmd:'Compare o ritmo atual com o histórico H2H capturado.'});
  if(lastState?.fixtureId) pool.push({label:'Resumo rápido',cmd:'/state'});
  pool.push({label:'Status do sistema',cmd:'Faça um diagnóstico do Engine, Bridge, voz, Ollama, GPU e captura.'});
  pool.push({label:'Monitorar agora',cmd:'Quais componentes do sistema precisam de atenção neste momento?' });
  pool.push({label:'Assunto livre',cmd:'Quero conversar sobre um assunto externo ao trading.'});
  const picked=pool.sort(()=>Math.random()-0.5).slice(0,4);
  chatChips.innerHTML='';
  for(const s of picked){const b=document.createElement('button');b.textContent=s.label;b.onclick=()=>sendChat(s.cmd);chatChips.appendChild(b)}
}

const STARTERS=[
  {label:'Resumo da partida',cmd:'Resuma o estado atual da partida com base em todos os dados capturados.'},
  {label:'Maior risco agora',cmd:'/risk'},
  {label:'Por que essa decisão?',cmd:'/why'},
  {label:'Melhor mercado',cmd:'/market'},
  {label:'Comparar com H2H',cmd:'Compare o ritmo atual da partida com o histórico H2H capturado.'},
  {label:'Status do sistema',cmd:'Faça um diagnóstico do Engine, Bridge, voz, Ollama, GPU e captura.'},
  {label:'Assunto livre',cmd:'Quero conversar sobre um assunto externo ao trading.'},
  {label:'/analisar',cmd:'/analisar'},
  {label:'Responda com voz',cmd:'responda com voz'}
];
(function renderStarters(){
  const box=$('chatStarters');box.innerHTML='';
  for(const s of STARTERS){const b=document.createElement('button');b.textContent=s.label;b.onclick=()=>sendChat(s.cmd);box.appendChild(b)}
})();

/* ========================= LEGACY COMMAND BAR (painel) ========================= */
$('btnTrader').onclick=()=>{const m=$('prompt').value.trim()||'/analisar';$('prompt').value='';append('user',m);runAction(m,'Comando')};
$('prompt').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('btnTrader').click()}});

async function boot(){await health();await refresh();tick();setInterval(tick,1000);setInterval(async()=>{await health();await refresh()},3000);append('sys','AURA 12.7.13 · Hálem, texto+voz, alerta de oportunidade. Recarregue a extensão.')}
boot();


/* === AURA OPS TOOLS === */
(function(){
  const ORCH = (typeof ORCH_BASE !== 'undefined' ? ORCH_BASE : 'http://127.0.0.1:8080');
  const ENG = (typeof ENGINE !== 'undefined' ? ENGINE : 'http://127.0.0.1:8765');
  async function jget(url){const r=await fetch(url); return r.json();}
  async function jpost(url){const r=await fetch(url,{method:'POST'}); return r.json();}
  const $id = (id)=>document.getElementById(id);
  const setBox=(id,val)=>{const el=$id(id); if(el) el.textContent=typeof val==='string'?val:JSON.stringify(val,null,2);};
  $id('btnHealth')?.addEventListener('click', async()=>{
    try{
      const [a,b]=await Promise.allSettled([jget(ORCH+'/api/health'), jget(ENG+'/api/health')]);
      setBox('latencyBox',{orch:a.status==='fulfilled'?a.value:String(a.reason), eng:b.status==='fulfilled'?b.value:String(b.reason)});
    }catch(e){setBox('latencyBox',String(e));}
  });
  $id('btnLatency')?.addEventListener('click', async()=>{
    try{ setBox('latencyBox', await jget(ENG+'/api/ops/latency')); }
    catch(e){ try{ setBox('latencyBox', await jget(ORCH+'/api/ops/latency')); }catch(e2){ setBox('latencyBox',String(e2)); } }
  });
  $id('btnSignature')?.addEventListener('click', async()=>{
    try{ setBox('signatureBox', await jget(ENG+'/api/ops/signatures')); }
    catch(e){ try{ setBox('signatureBox', await jget(ORCH+'/api/ops/signatures')); }catch(e2){ setBox('signatureBox',String(e2)); } }
  });
  $id('btnDirectorPending')?.addEventListener('click', async()=>{
    try{ setBox('directorBox', await jget(ENG+'/api/director/pending')); }
    catch(e){ setBox('directorBox',String(e)); }
  });
  $id('btnDirectorApprove')?.addEventListener('click', async()=>{
    try{ setBox('directorBox', await jpost(ENG+'/api/director/approve')); }
    catch(e){ setBox('directorBox',String(e)); }
  });
  $id('btnRefreshAll')?.addEventListener('click', async()=>{
    $id('btnHealth')?.click(); $id('btnLatency')?.click(); $id('btnSignature')?.click(); $id('btnDirectorPending')?.click();
  });
})();


/* ========================= AGENT HUB ========================= */
let agentCatalogCache = null;
const AGENT_ACTION_LABELS = {
  status: 'Status',
  inspect: 'Inspecionar',
  health: 'Saúde',
  pending: 'Pendências',
  voice_diagnostic: 'Diagnóstico de voz',
  paper_preview: 'Prévia paper trade',
  simulation_contract: 'Contrato de simulação',
  run_function: 'Executar função'
};
function agentText(value){return value===undefined||value===null?'—':String(value)}
async function requestAgentAction(agentId, actionName, payload={}){
  const url=ENGINE+'/api/agents/'+encodeURIComponent(agentId)+'/action';
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CornerAI':'agent-hub'},body:JSON.stringify({action:actionName,payload})});
  const data=await r.json().catch(()=>({error:'resposta invalida'}));
  if(!r.ok||data.ok===false)throw new Error(data.error||`HTTP ${r.status}`);
  return data;
}
function renderAgentCatalog(data){
  const root=$('agentMenus');if(!root)return;
  agentCatalogCache=data;
  const query=String($('agentSearch')?.value||'').trim().toLowerCase();
  const layer=String($('agentLayerFilter')?.value||'all');
  const source=(data?.agents||[]).filter(a=>{
    const hay=[a.id,a.name,a.file,a.layer].join(' ').toLowerCase();
    return (layer==='all'||a.layer===layer)&&(!query||hay.includes(query));
  });
  if(!source.length){root.innerHTML='<div class="card agent-empty">Nenhum agente corresponde ao filtro atual.</div>';return}
  const groups=new Map();
  for(const agent of source){if(!groups.has(agent.layer))groups.set(agent.layer,[]);groups.get(agent.layer).push(agent)}
  root.innerHTML='';
  for(const [layerName,agents] of groups){
    const section=document.createElement('section');section.className='agent-layer';
    const head=document.createElement('div');head.className='agent-layer-head';
    const title=document.createElement('strong');title.textContent=layerName;
    const count=document.createElement('span');count.textContent=`${agents.length} agente(s)`;
    head.append(title,count);section.appendChild(head);
    const grid=document.createElement('div');grid.className='agent-grid';
    for(const agent of agents)grid.appendChild(renderAgentCard(agent));
    section.appendChild(grid);root.appendChild(section);
  }
  const runnableCount=source.filter(a=>a.implementation_state==='runnable').length;
  const summary=$('agentSummary');if(summary)summary.textContent=`${source.length}/${data?.count||source.length} visíveis · ${runnableCount} com execução`;
}
function renderAgentCard(agent){
  const implState=agent.implementation_state||((agent.source?.exists)?'inspect_only':'source_missing');
  const card=document.createElement('article');card.className='agent-card agent-'+implState+(agent.source?.exists?'':' agent-missing');
  const head=document.createElement('div');head.className='agent-card-head';
  const name=document.createElement('h3');name.textContent=agent.name||agent.id;
  const state=document.createElement('span');state.className='agent-state '+(implState==='runnable'?'ready':implState==='source_missing'||implState==='syntax_error'?'missing':'');state.textContent=implState==='runnable'?'EXECUTÁVEL':implState==='asset'?'ASSET':implState==='syntax_error'?'SINTAXE':implState==='source_missing'?'AUSENTE':'INSPEÇÃO';
  head.append(name,state);card.appendChild(head);
  const file=document.createElement('span');file.className='agent-file';file.title=agent.file;file.textContent=agent.file;card.appendChild(file);
  const meta=document.createElement('div');meta.className='agent-meta';meta.textContent=`${(agent.functions||[]).length} função(ões) · ${(agent.runnable_functions||[]).length} executável(eis) · ${implState} · ${agent.source?.kind||'sem fonte'}`;card.appendChild(meta);
  const actions=document.createElement('div');actions.className='agent-actions';
  const result=document.createElement('pre');result.className='agent-result';
  for(const actionName of (agent.actions||['status','inspect'])){
    if(actionName==='run_function')continue;
    const button=document.createElement('button');button.type='button';button.textContent=AGENT_ACTION_LABELS[actionName]||actionName;button.dataset.agentAction=actionName;
    button.onclick=async()=>{
      result.classList.add('visible');result.textContent='Consultando '+(AGENT_ACTION_LABELS[actionName]||actionName)+'...';button.disabled=true;
      try{const data=await requestAgentAction(agent.id,actionName);result.textContent=JSON.stringify(data,null,2)}catch(error){result.textContent='Falha: '+agentText(error.message||error)}finally{button.disabled=false}
    };
    actions.appendChild(button);
  }
  const functionMenu=document.createElement('div');functionMenu.className='agent-function-menu';
  const functionTitle=document.createElement('div');functionTitle.className='agent-function-title';functionTitle.textContent='Funções deste agente';functionMenu.appendChild(functionTitle);
  const details=Array.isArray(agent.function_details)?agent.function_details:[];
  const runnable=new Set(agent.runnable_functions||[]);
  const select=document.createElement('select');select.className='agent-function-select';select.title='Selecione uma função allowlisted para executar';
  const runnableDetails=details.filter(d=>runnable.has(d.name));
  const runnableNames=runnableDetails.length?runnableDetails.map(d=>d.name):[...runnable];
  if(!runnableNames.length){
    const opt=document.createElement('option');opt.textContent='Nenhuma função com handler seguro';opt.disabled=true;select.appendChild(opt);
  }else{
    for(const fn of runnableNames){
      const d=runnableDetails.find(x=>x.name===fn);const opt=document.createElement('option');opt.value=fn;opt.textContent=d?.signature||fn;select.appendChild(opt);
    }
  }
  functionMenu.appendChild(select);
  const functionDefaults=agent.function_defaults||{};
  const defaultFor=(fn)=>functionDefaults[fn]&&typeof functionDefaults[fn]==='object'?functionDefaults[fn]:{};
  const args=document.createElement('textarea');args.className='agent-function-args';args.rows=5;args.spellcheck=false;args.placeholder='Argumentos JSON; defaults seguros preenchidos automaticamente';
  args.value=JSON.stringify(defaultFor(runnableNames[0]||''),null,2);functionMenu.appendChild(args);
  select.addEventListener('change',()=>{args.value=JSON.stringify(defaultFor(select.value),null,2)});
  const fnButton=document.createElement('button');fnButton.type='button';fnButton.className='agent-function-run';fnButton.textContent='Executar função';fnButton.disabled=!runnableNames.length;
  fnButton.onclick=async()=>{
    let call={};
    try{call=args.value.trim()?JSON.parse(args.value):{};if(!call||typeof call!=='object'||Array.isArray(call))throw new Error('o JSON deve ser um objeto')}catch(error){result.classList.add('visible');result.textContent='Argumentos inválidos: '+agentText(error.message||error);return}
    const fn=select.value;result.classList.add('visible');result.textContent=`Executando ${fn} em paper trade...`;fnButton.disabled=true;
    try{const data=await requestAgentAction(agent.id,'run_function',{function:fn,call});result.textContent=JSON.stringify(data,null,2)}catch(error){result.textContent='Falha: '+agentText(error.message||error)}finally{fnButton.disabled=!runnableNames.length}
  };
  functionMenu.appendChild(fnButton);
  const allFunctions=document.createElement('div');allFunctions.className='agent-function-list';
  for(const d of details){const chip=document.createElement('span');chip.className='agent-function-chip '+(runnable.has(d.name)?'runnable':'inspect-only');chip.title=d.signature||d.name;chip.textContent=runnable.has(d.name)?d.name:d.name+' (inspeção)';allFunctions.appendChild(chip)}
  if(details.length)functionMenu.appendChild(allFunctions);
  card.append(actions,functionMenu,result);return card;
}
async function loadAgents(){
  const root=$('agentMenus');if(!root)return;
  root.innerHTML='<div class="card agent-empty">Carregando agentes e verificando fontes...</div>';
  try{
    const r=await fetch(ENGINE+'/api/agents');
    const data=await r.json().catch(()=>({error:'resposta invalida'}));
    if(!r.ok||data.ok===false)throw new Error(data.error||`HTTP ${r.status}`);
    renderAgentCatalog(data);
  }catch(error){
    const summary=$('agentSummary');if(summary)summary.textContent='offline';
    root.innerHTML='';const box=document.createElement('div');box.className='card agent-empty';box.textContent='Não foi possível carregar o catálogo: '+agentText(error.message||error);root.appendChild(box);
  }
}
$('agentSearch')?.addEventListener('input',()=>{if(agentCatalogCache)renderAgentCatalog(agentCatalogCache)});
$('agentLayerFilter')?.addEventListener('change',()=>{if(agentCatalogCache)renderAgentCatalog(agentCatalogCache)});
$('btnAgentsRefresh')?.addEventListener('click',loadAgents);
loadAgents();


// Ponte do Pilar 7: os chips renderizados com DocumentFragment continuam
// executando comandos reais do controlador ativo, sem abrir um segundo fluxo.
window.__auraSendAction=async function(action,label){
  const aliases={
    analyze_now:'/analisar',
    system_status:'/status',
    last_signals:'/data',
    confirm_entry:'/risk',
    adjust_stake:'/risk',
    show_kelly:'/risk',
    wait_velocity:'/why',
    force_analysis:'/analisar',
    smd_history:'/why',
    cooldown_status:'/risk',
    next_window:'/risk',
    recalc_poisson:'/analisar',
    change_line:'/market'
  };
  const command=aliases[String(action||'')]||String(action||'/status');
  await runAction(command,label||command);
};
window.addEventListener('aura:sidepanel-action',function(event){
  const detail=event&&event.detail||{};
  void window.__auraSendAction(detail.action,detail.label);
});
