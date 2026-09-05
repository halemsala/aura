const VERSION="12.6.5";

try{ const _v=document.querySelector(".version"); if(_v) _v.textContent="v"+VERSION; }catch{}

async function msg(type,extra={},timeoutMs=20000){return new Promise(r=>{
  let done=false; const finish=v=>{if(done)return;done=true;r(v)};
  const timer=setTimeout(()=>finish({ok:false,error:"timeout "+timeoutMs+"ms — recarregue a extensão"}),timeoutMs);
  try{
    chrome.runtime.sendMessage({type,...extra},res=>{
      clearTimeout(timer);
      const err=chrome.runtime.lastError;
      if(err) finish({ok:false,error:err.message});
      else finish(res||{ok:false,error:"sem resposta do service worker"});
    });
  }catch(e){clearTimeout(timer);finish({ok:false,error:e?.message||String(e)})}
})}
async function activeSokker(){
  try{
    const target=await msg("GET_CAPTURE_TARGET");
    if(target?.tabId){
      const t=await chrome.tabs.get(Number(target.tabId));
      if(t?.id&&/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(t.url||"")) return t;
    }
  }catch{}
  const tabs=await chrome.tabs.query({active:true,currentWindow:true});
  return tabs.find(t=>/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(t.url||""));
}
const liveMinute=document.getElementById('liveMinute'),liveEvents=document.getElementById('liveEvents'),liveSnapshots=document.getElementById('liveSnapshots'),menus=document.getElementById('menus'),status=document.getElementById('status'),statusTitle=document.getElementById('statusTitle'),dot=document.getElementById('dot'),match=document.getElementById('match'),fixture=document.getElementById('fixture'),source=document.getElementById('source'),readiness=document.getElementById('readiness'),quality=document.getElementById('quality'),coverage=document.getElementById('coverage');
document.getElementById("dashboard").onclick=async()=>{
  statusTitle.textContent="Abrindo dashboard…";
  status.textContent="Aguarde";
  const r=await msg("OPEN_DASHBOARD_WINDOW");
  statusTitle.textContent=r?.ok?"Dashboard aberto":"Dashboard indisponível";
  status.textContent=r?.ok?(r.mode==="tab"?"Aberto em nova aba.":"Aberto em janela separada."):String(r?.error||"Não foi possível abrir o Dashboard. Recarregue a extensão.");
};
document.getElementById("diagnostics").onclick=async()=>{
  statusTitle.textContent="Abrindo diagnóstico…";
  status.textContent="Aguarde";
  const r=await msg("OPEN_DIAGNOSTICS_WINDOW");
  statusTitle.textContent=r?.ok?"Diagnóstico aberto":"Diagnóstico indisponível";
  status.textContent=r?.ok?(r.mode==="tab"?"Aberto em nova aba.":"Aberto em janela separada."):String(r?.error||"Não foi possível abrir o diagnóstico. Recarregue a extensão.");
};
document.getElementById('sweep').onclick=async()=>{const r=await msg('MENU_SWEEP');statusTitle.textContent=r?.ok?'Varredura iniciada':'Varredura indisponível';status.textContent=r?.ok?`${r.count||0} menu(s) programado(s).`:String(r?.error||'Abra o SokkerPRO.')};
document.getElementById('capture').onclick=async()=>{const t=await activeSokker();if(!t){statusTitle.textContent='Abra o SokkerPRO';status.textContent='Nenhuma partida ativa nesta janela.';return}try{statusTitle.textContent='Armando captura…';status.textContent='Colheita DOM direta (9.2.3)…';const armed=await chrome.runtime.sendMessage({type:'ARM_ACTIVE_GAME',tabId:t.id});if(!armed?.ok && !armed?.harvest?.ok)throw new Error(armed?.error||armed?.harvest?.error||'Falha ao iniciar a captura');const snaps=armed?.acceptedSnapshots||armed?.harvest?.acceptedSnapshots||0;statusTitle.textContent=snaps>0?'Captura ativa':'Armado';status.textContent=(snaps>0?('Snapshots: '+snaps+' · '):'')+'fixture '+(armed.fixtureId||armed?.harvest?.fixtureId||'—');try{await chrome.runtime.sendMessage({type:'FORCE_DOM_HARVEST',tabId:t.id});}catch{}await refresh()}catch(e){statusTitle.textContent='Falha na captura';status.textContent=String(e?.message||e||'Recarregue a página do SokkerPRO.');}};
let __allToolsReport=null;
function renderAllToolsReport(report){
 const st=document.getElementById("allToolsStatus"),box=document.getElementById("allToolsSummary");
 if(!report){if(st)st.textContent="Nenhum relatório";return;}
 const sm=report.summary||{};
 if(st)st.textContent=`${sm.pass||0} PASS · ${sm.fail||0} FAIL · ${sm.pending||0} AGUARDANDO · ${report.durationMs||0}ms · fixture ${report.fixtureId||"—"}`;
 if(box){box.innerHTML=(report.results||[]).map(x=>{
   const icon=x.status==="PASS"?"🟢":x.status==="FAIL"?"🔴":"🟡";
   return `<div class="row"><b>${icon} ${escapeHtml(x.label)}</b> · ${escapeHtml(String(x.detail||""))}</div>`;
 }).join("")+`<div class="row"><b>Resumo:</b> ${sm.total||0} ferramentas verificadas</div>`;}
}
document.getElementById("allToolsTestBtn")?.addEventListener("click",async()=>{
 const st=document.getElementById("allToolsStatus");if(st)st.textContent="Executando teste maximizado…";
 const t=await activeSokker();
 if(!t){if(st)st.textContent="Abra uma partida do SokkerPRO.";return;}
 const r=await msg("RUN_ALL_TOOLS_TEST",{tabId:t.id});
 if(!r?.ok){if(st)st.textContent="Falha: "+(r?.error||"sem resposta");return;}
 __allToolsReport=r.report||null;renderAllToolsReport(__allToolsReport);
 try{await chrome.storage.local.set({cornerai_last_tool_test:__allToolsReport})}catch{}
});
document.getElementById("allToolsCopyBtn")?.addEventListener("click",async()=>{
 if(!__allToolsReport){const r=await msg("GET_LAST_TOOL_TEST");__allToolsReport=r?.report||null;}
 if(!__allToolsReport)return;
 try{await navigator.clipboard.writeText(JSON.stringify(__allToolsReport,null,2));const st=document.getElementById("allToolsStatus");if(st)st.textContent+=" · relatório copiado";}catch{}
});
document.getElementById("allToolsDownloadBtn")?.addEventListener("click",async()=>{
 if(!__allToolsReport){const r=await msg("GET_LAST_TOOL_TEST");__allToolsReport=r?.report||null;}
 if(!__allToolsReport)return;
 const blob=new Blob([JSON.stringify(__allToolsReport,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=`cornerai-all-tools-test-${__allToolsReport.fixtureId||"session"}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
async function loadLastAllToolsReport(){try{const r=await msg("GET_LAST_TOOL_TEST");if(r?.ok&&r.report){__allToolsReport=r.report;renderAllToolsReport(r.report)}}catch{}}
loadLastAllToolsReport();
document.getElementById('reset').onclick=async()=>{if(confirm('Limpar o estado da partida?')){await msg('RESET_STATE');await refresh()}};
async function refresh(){const r=await msg('REQUEST_STATE');const active=!!r?.fixtureId;dot.className='status-dot'+(active?' on':'');statusTitle.textContent=active?(r.liveStatus==='finished'?'Partida histórica':'Captura ativa'):'Aguardando partida';status.textContent=active?'Motor conectado e monitorando dados.':'Abra uma partida no SokkerPRO.';match.textContent=active?`${r.home||'?'}  ${r.score?.home??0} × ${r.score?.away??0}  ${r.away||'?'}`:'Nenhuma partida';fixture.textContent=active?`Fixture ${r.fixtureId} · ${r.dataMode||'unknown'}`:'Aguardando captura';if(liveMinute)liveMinute.textContent=active?(r.minute==null?'—':`${r.minute}${r.extraMinute?`+${r.extraMinute}`:''}'`):'—';if(liveEvents)liveEvents.textContent=`${r.eventCount||r.cornerEventCount||0} eventos`;if(liveSnapshots)liveSnapshots.textContent=`${r.snapshotCount||0} snapshots`;const mode=document.getElementById('mode');if(mode)mode.textContent=active?(r.liveStatus==='finished'?'HISTÓRICO':'LIVE'):'IDLE';const q=Number(r.quality?.score||0),i=Number(r.intelligence?.readiness||0),c=Number(r.capture?.observedMinutes?.length||0);if(readiness)readiness.textContent=Math.round(i);if(menus)menus.textContent=String(r.menuCapture?.uniqueMenus||0);if(quality)quality.textContent=Math.round(q);if(coverage)coverage.textContent=c;source.textContent=`Fonte ${r.lastSnapshotSource||'—'} · IA ${Math.round(i)}/100`;
  // Local AI Engine status
  try{
    const d=r.diagnostics||{};
    const aiOk=!!d.lastLocalAiOk;
    const aiAt=d.lastLocalAiPushAt?new Date(d.lastLocalAiPushAt).toLocaleTimeString():null;
    if(status && active){
      status.textContent = (status.textContent||'') + (aiOk?` · Engine OK (${aiAt})`:(d.lastLocalAiError?` · Engine ERR`:' · Engine aguardando'));
    }
  }catch{}
}async function armOnOpen(){
  // 9.2.0: verifica se o service worker responde antes de qualquer fluxo
  try{
    const ping=await msg("REQUEST_STATE");
    if(ping && ping.error && /Receiving end|context invalidated|sem resposta/i.test(String(ping.error))){
      statusTitle.textContent="Service Worker offline";
      status.textContent="Recarregue a extensão em chrome://extensions e a aba do SokkerPRO.";
      return;
    }
  }catch{}
  // Segurança: abrir o popup NÃO inicia nem reseta a sessão da partida.
  // A captura só começa quando o usuário clica explicitamente em "Capturar".
  try{
    const t=await activeSokker();
    if(t?.id){
      statusTitle.textContent="Partida pronta";
      status.textContent="Clique em Capturar para iniciar sem interromper a página.";
    }else{
      statusTitle.textContent="Aguardando partida";
      status.textContent="Abra uma partida no SokkerPRO e clique em Capturar.";
    }
  }catch(e){
    statusTitle.textContent="Aguardando partida";
    status.textContent="Abra uma partida no SokkerPRO e clique em Capturar.";
  }
  await refresh();
}
armOnOpen();
setInterval(refresh,2000);

async function refreshWebhook(){
  try{
    const w=await chrome.runtime.sendMessage({type:"GET_WEBHOOK"});
    const url=document.getElementById("webhookUrl");
    const en=document.getElementById("webhookEnabled");
    const st=document.getElementById("webhookStatus");
    if(url) url.value=(w?.url!=null&&w.url!=="")?w.url:"http://127.0.0.1:8080/api/cornerai/feed";
    if(en) en.checked=w?.enabled!==false;
    if(st) st.textContent=`Outbox ${w?.pending||0} · enviados ${w?.sent||0} · falhas ${w?.failed||0} · drop ${w?.dropped||0}${w?.bridgeOffline?" · BRIDGE OFFLINE":" · Bridge OK"}${w?.lastError?` · err ${w.lastError}`:""}`;
  }catch(e){}
}
document.getElementById("webhookSave")?.addEventListener("click",async()=>{
  const url=document.getElementById("webhookUrl")?.value||"";
  const enabled=!!document.getElementById("webhookEnabled")?.checked;
  const r=await chrome.runtime.sendMessage({type:"SET_WEBHOOK",url,enabled});
  const st=document.getElementById("webhookStatus");
  if(st) st.textContent=r?.ok?`Salvo · ${enabled?"ativo":"pausado"}`:(r?.error||"Falha ao salvar");
  await refreshWebhook();
});
document.getElementById("webhookPush")?.addEventListener("click",async()=>{
  const st=document.getElementById("webhookStatus");
  if(st) st.textContent="Enviando…";
  const r=await chrome.runtime.sendMessage({type:"PUSH_ANALYST",reason:"popup"});
  if(st) st.textContent=r?.ok?`OK · pending ${r.flushed?.pending??"—"}`:`Bloqueado: ${r?.reason||r?.error||"erro"}`;
  await refreshWebhook();
});
refreshWebhook();
setInterval(refreshWebhook,4000);


// --- Alert prefs + history ---
async function refreshAlerts(){
  try{
    const r=await chrome.runtime.sendMessage({type:"GET_ALERT_PREFS"});
    const p=r?.prefs||{};
    const set=(id,v)=>{const el=document.getElementById(id);if(el) el.checked=!!v};
    set("alertEnabled",p.enabled!==false);
    set("alertFav",p.favorite_losing!==false);
    set("alertCpi",p.cpi_high!==false);
    set("alertAppm",p.appm_accel!==false);
    set("alertCorner",p.corner_prediction!==false);
    set("alertRed",p.red_cards!==false);
    const thr=document.getElementById("alertCpiThr"); if(thr) thr.value=p.cpiThreshold??0.72;
    const pt=document.getElementById("alertPredThr"); if(pt) pt.value=p.cornerPredThreshold??0.55;
    const st=document.getElementById("alertStatus"); if(st) st.textContent="Alertas carregados";
  }catch(e){}
}
document.getElementById("alertSave")?.addEventListener("click",async()=>{
  const prefs={
    enabled:!!document.getElementById("alertEnabled")?.checked,
    favorite_losing:!!document.getElementById("alertFav")?.checked,
    cpi_high:!!document.getElementById("alertCpi")?.checked,
    appm_accel:!!document.getElementById("alertAppm")?.checked,
    corner_prediction:!!document.getElementById("alertCorner")?.checked,
    red_cards:!!document.getElementById("alertRed")?.checked,
    cpiThreshold:Number(document.getElementById("alertCpiThr")?.value||0.72),
    cornerPredThreshold:Number(document.getElementById("alertPredThr")?.value||0.55)
  };
  const r=await chrome.runtime.sendMessage({type:"SET_ALERT_PREFS",prefs});
  const st=document.getElementById("alertStatus");
  if(st) st.textContent=r?.ok?"Alertas salvos":(r?.error||"Falha");
});
document.getElementById("historyBtn")?.addEventListener("click",async()=>{
  const box=document.getElementById("historyList");
  const st=document.getElementById("historyStatus");
  if(st) st.textContent="Carregando…";
  const r=await chrome.runtime.sendMessage({type:"GET_MATCH_HISTORY",limit:15});
  if(!r?.ok){ if(st) st.textContent=r?.error||"Sem histórico"; return; }
  if(st) st.textContent=`${r.count||0} partida(s)`;
  if(box){
    const rows=r.matches||[];
    box.innerHTML=rows.length?rows.map(m=>`<div class="row"><b>${escapeHtml(m.home||"?")} ${escapeHtml(m.score?.home??"?")}×${escapeHtml(m.score?.away??"?")} ${escapeHtml(m.away||"?")}</b> · cantos ${escapeHtml(m.corners?.home??"—")}×${escapeHtml(m.corners?.away??"—")} · ${escapeHtml(m.competition||"—")}</div>`).join(""):"Nenhuma partida arquivada ainda.";
  }
});
document.getElementById("feedbackBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("historyStatus");
  const r=await chrome.runtime.sendMessage({type:"GET_FEEDBACK_STATS"});
  if(!r?.ok){ if(st) st.textContent="Feedback indisponível"; return; }
  const s=r.stats||{};
  if(st) st.textContent=`Feedback n=${s.n||0} · hit=${s.hitRate??"—"} · brier=${s.brier??"—"} · avgPred=${s.avgPred??"—"} · pending ${r.pending||0}`;
});
refreshAlerts();


// --- Auto-Gemini ---
async function refreshGemini(){
  try{
    const r=await chrome.runtime.sendMessage({type:"GET_GEMINI"});
    const c=r?.config||{};
    const en=document.getElementById("geminiEnabled"); if(en) en.checked=!!c.enabled;
    const au=document.getElementById("geminiAuto"); if(au) au.checked=!!c.auto;
    const oa=document.getElementById("geminiOnAlert"); if(oa) oa.checked=c.onAlert!==false;
    const eco=document.getElementById("geminiEconomy"); if(eco) eco.checked=c.economy!==false;
    const crit=document.getElementById("geminiCritical"); if(crit) crit.checked=!!c.onlyCriticalWindows;
    const model=document.getElementById("geminiModel");
    if(model&&c.model){
      const ok=[...model.options].some(o=>o.value===c.model);
      model.value=ok?c.model:"gemini-3.5-flash-lite";
    }
    const iv=document.getElementById("geminiInterval"); if(iv) iv.value=Math.round((c.intervalMs||60000)/1000);
    const mm=document.getElementById("geminiMaxMatch"); if(mm) mm.value=c.maxCallsPerMatch||12;
    const key=document.getElementById("geminiKey");
    if(key && c.hasKey && !key.value) key.placeholder="•••• API key salva";
    const st=document.getElementById("geminiStatus");
    if(st){
      const last=c.lastOkAt?new Date(c.lastOkAt).toLocaleTimeString():"—";
      const tok=Math.round(((c.estInputTokens||0)+(c.estOutputTokens||0))/1000);
      st.textContent=`${c.hasKey?"Key OK":"Sem key"} · runs ${c.runs||0} · skip ${c.skipped||0} · dia ${c.dayRuns||0}/${c.maxCallsPerDay||80} · ~${tok}k tok · last ${last}${c.lastError?" · err "+c.lastError:""}`;
    }
    const box=document.getElementById("geminiReply");
    if(box && c.lastReplyPreview) box.textContent=c.lastReplyPreview;
  }catch(e){}
}
document.getElementById("geminiSave")?.addEventListener("click",async()=>{
  const keyEl=document.getElementById("geminiKey");
  const enEl=document.getElementById("geminiEnabled");
  // If user pastes a key and forgets "Ativo", enable automatically so Auto works later
  if(keyEl && keyEl.value.trim() && enEl && !enEl.checked){
    enEl.checked=true;
  }
  const payload={
    enabled:!!document.getElementById("geminiEnabled")?.checked,
    auto:!!document.getElementById("geminiAuto")?.checked,
    onAlert:!!document.getElementById("geminiOnAlert")?.checked,
    economy:!!document.getElementById("geminiEconomy")?.checked,
    onlyCriticalWindows:!!document.getElementById("geminiCritical")?.checked,
    model:document.getElementById("geminiModel")?.value||"gemini-3.5-flash-lite",
    intervalMs:Math.max(60, Number(document.getElementById("geminiInterval")?.value||60))*1000,
    maxCallsPerMatch:Math.max(1, Number(document.getElementById("geminiMaxMatch")?.value||30))
  };
  if(keyEl && keyEl.value.trim()) payload.apiKey=keyEl.value.trim();
  const r=await chrome.runtime.sendMessage({type:"SET_GEMINI", config:payload});
  const st=document.getElementById("geminiStatus");
  if(st){
    if(!r?.ok) st.textContent=r?.error||"Falha ao salvar";
    else if(!r.config?.hasKey) st.textContent="Salvo · falta API key";
    else if(!r.config?.enabled) st.textContent="Salvo · marque Ativo para Auto/Alertas (Analisar agora já funciona)";
    else st.textContent="Gemini salvo · pronto";
  }
  if(keyEl && payload.apiKey){ keyEl.value=""; keyEl.placeholder="•••• API key salva"; }
  await refreshGemini();
});
document.getElementById("geminiRun")?.addEventListener("click",async()=>{
  const st=document.getElementById("geminiStatus");
  const box=document.getElementById("geminiReply");
  if(st) st.textContent="Consultando Gemini…";
  // Ensure config loaded; manual run does not require Ativo
  const r=await chrome.runtime.sendMessage({type:"RUN_GEMINI", reason:"popup"});
  if(!r?.ok){
    if(st) st.textContent=`Erro: ${r?.error||"falha"}`;
    if(box) box.textContent=String(r?.error||"");
    return;
  }
  if(st) st.textContent="OK · análise recebida";
  if(box) box.textContent=(r.result?.reply||"").slice(0,2000);
  await refreshGemini();
});
document.getElementById("geminiResults")?.addEventListener("click",async()=>{
  const r=await chrome.runtime.sendMessage({type:"GET_GEMINI_RESULTS", limit:5});
  const box=document.getElementById("geminiReply");
  const st=document.getElementById("geminiStatus");
  const rows=r?.results||[];
  if(st) st.textContent=`${rows.length} resultado(s)`;
  if(box){
    box.innerHTML = rows.length
      ? rows.map(x=>`<div class="row"><b>${escapeHtml(x.match?.home||"?")} ${escapeHtml(x.match?.score?.home??"?")}×${escapeHtml(x.match?.score?.away??"?")} ${escapeHtml(x.match?.away||"?")}</b> · ${escapeHtml(x.reason||"")}<br/>${escapeHtml(String(x.reply||"").slice(0,320))}</div>`).join("")
      : "Nenhuma análise ainda.";
  }
});
refreshGemini();
setInterval(refreshGemini, 8000);


// --- Explain + Drift ---
document.getElementById("explainBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("explainStatus");
  const box=document.getElementById("explainBox");
  if(st) st.textContent="Calculando…";
  const r=await chrome.runtime.sendMessage({type:"GET_EXPLAIN"});
  if(!r?.ok){ if(st) st.textContent=r?.error||"Falha"; return; }
  const ex=r.explain?.explanation||r.lastAlert||{};
  if(st) st.textContent=`${ex.verdict||"—"} · P ${ex.probability!=null?Math.round(ex.probability*100)+"%":"—"} · thr ${ex.threshold!=null?Math.round(ex.threshold*100)+"%":"—"}`;
  if(box){
    const reasons=(ex.reasons||[]).map(x=>`+ ${escapeHtml(x.text)}`).join("<br/>");
    const against=(ex.against||[]).map(x=>`− ${escapeHtml(x.text)}`).join("<br/>");
    box.innerHTML=`<div class="row"><b>${escapeHtml(ex.summary||"Sem resumo")}</b></div>
      <div class="row">${reasons||"Sem motivos a favor"}</div>
      <div class="row">${against||"Sem ressalvas"}</div>`;
  }
});
document.getElementById("driftBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("explainStatus");
  const box=document.getElementById("explainBox");
  if(st) st.textContent="CUSUM…";
  const r=await chrome.runtime.sendMessage({type:"GET_DRIFT"});
  if(!r?.ok){ if(st) st.textContent=r?.error||"Falha"; return; }
  const d=r.drift||{};
  if(st) st.textContent=d.active?`DRIFT ativo · ${(d.hits||[]).length} hit(s)`:`Sem drift · séries ${Object.keys(d.series||{}).length}`;
  if(box){
    const recent=(d.recent||[]).slice(0,6).map(h=>`<div class="row"><b>${escapeHtml(h.name)}</b> ${escapeHtml(h.direction)} @ ${escapeHtml(h.minute??"?")}′ · val ${Number(h.value).toFixed(3)} μ ${Number(h.mean).toFixed(3)}</div>`).join("");
    const series=Object.entries(d.series||{}).map(([k,v])=>`${escapeHtml(k)}: μ=${escapeHtml(v.mean??"—")} +/${escapeHtml(v.pos)} -/${escapeHtml(v.neg)} n=${escapeHtml(v.n)}`).join("<br/>");
    box.innerHTML=(recent||"<div class='row'>Nenhum alerta de drift ainda</div>")+`<div class="row">${series}</div>`;
  }
});


// --- Skill API Monitor ---
async function refreshSkillMonitor(){
  const st=document.getElementById("skillMonStatus");
  const box=document.getElementById("skillMonBox");
  const healthEl=document.getElementById("skillHealth");
  const latEl=document.getElementById("skillLatency");
  const totEl=document.getElementById("skillTotals");
  try{
    const r=await chrome.runtime.sendMessage({type:"GET_SKILL_MONITOR"});
    if(!r?.ok){ if(st) st.textContent=r?.error||"Falha monitor"; return; }
    const m=r.monitor||{};
    if(healthEl) healthEl.textContent=m.healthLabel||m.health||"—";
    if(latEl) latEl.textContent=m.connection?.latencyMs!=null?`lat ${m.connection.latencyMs}ms`:"lat —";
    if(totEl) totEl.textContent=`${m.totals?.requests||0} req · ${m.totals?.ok||0} ok · ${m.totals?.fail||0} fail`;
    const tips=(m.tips||[]).join(" · ");
    if(st) st.textContent=`${m.healthLabel||"—"} · key ${m.config?.hasKey?"OK":"NÃO"} · model ${m.config?.model||"—"} · ${tips.slice(0,120)}`;
    if(box){
      const lines=[];
      lines.push(`<div class="row"><b>Entrada (último envio)</b></div>`);
      if(m.lastIn){
        lines.push(`<div class="row">${escapeHtml(m.lastIn.at||"—")} · ${escapeHtml(m.lastIn.reason||"—")} · model ${escapeHtml(m.lastIn.model||"—")} · fix ${escapeHtml(m.lastIn.fixtureId||"—")} · ${escapeHtml(m.lastIn.promptChars||0)} chars · tok~${escapeHtml(m.lastIn.estTokens||0)}</div>`);
        if(m.lastIn.match) lines.push(`<div class="row">${escapeHtml(m.lastIn.match.home||"?")} × ${escapeHtml(m.lastIn.match.away||"?")} · ${escapeHtml(m.lastIn.match.minute??"—")}'</div>`);
      } else lines.push(`<div class="row">Nenhum envio ainda</div>`);
      lines.push(`<div class="row"><b>Saída (última resposta)</b></div>`);
      if(m.lastOut){
        lines.push(`<div class="row">${escapeHtml(m.lastOut.at||"—")} · ${escapeHtml(m.lastOut.model||"—")} · ${escapeHtml(m.lastOut.latencyMs??"—")}ms · ${escapeHtml(m.lastOut.replyChars||0)} chars</div>`);
        lines.push(`<div class="row">${escapeHtml(String(m.lastOut.replyPreview||"").slice(0,280))}</div>`);
      } else lines.push(`<div class="row">Nenhuma resposta ainda</div>`);
      if(m.lastError){
        lines.push(`<div class="row"><b>Último erro</b></div>`);
        lines.push(`<div class="row" style="color:#ff8a9a">${escapeHtml((m.lastError.message||"").slice(0,220))}</div>`);
      }
      lines.push(`<div class="row"><b>Log I/O (recentes)</b></div>`);
      const log=m.log||[];
      if(!log.length) lines.push(`<div class="row">vazio</div>`);
      for(const e of log.slice(0,12)){
        const tag=e.ok===true?"✓":(e.ok===false?"✗":"·");
        const det=e.error||e.replyPreview||e.phase||"";
        lines.push(`<div class="row">${tag} ${escapeHtml(e.phase||"?")} ${escapeHtml(e.reason||"")} ${escapeHtml(e.model||"")} ${e.latencyMs!=null?escapeHtml(e.latencyMs)+"ms":""} ${escapeHtml(String(det).slice(0,100))}</div>`);
      }
      if(m.connection?.models?.length){
        lines.push(`<div class="row"><b>Modelos disponíveis (teste)</b></div>`);
        lines.push(`<div class="row">${escapeHtml(m.connection.models.slice(0,10).join(", "))}</div>`);
      }
      box.innerHTML=lines.join("");
    }
  }catch(e){ if(st) st.textContent=e?.message||String(e); }
}
document.getElementById("skillTestBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("skillMonStatus");
  if(st) st.textContent="Testando API Gemini…";
  const r=await chrome.runtime.sendMessage({type:"TEST_SKILL_CONNECTION"});
  if(st) st.textContent=r?.ok?`Conexão OK · ${r.workingModel||""} · ${r.connection?.latencyMs||"?"}ms`:`Falha: ${r?.error||"?"}`;
  await refreshSkillMonitor();
});
document.getElementById("skillRefreshBtn")?.addEventListener("click",()=>refreshSkillMonitor());
document.getElementById("skillClearBtn")?.addEventListener("click",async()=>{
  await chrome.runtime.sendMessage({type:"CLEAR_SKILL_MONITOR"});
  await refreshSkillMonitor();
});
document.getElementById("skillPayloadBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("skillMonStatus");
  const box=document.getElementById("skillMonBox");
  const r=await chrome.runtime.sendMessage({type:"GET_SKILL_LAST_PAYLOAD"});
  if(!r?.ok){ if(st) st.textContent=r?.error||"Falha"; return; }
  if(st) st.textContent=`Payload atual · ${r.promptChars||0} chars prompt`;
  if(box){
    const payloadStr=JSON.stringify(r.payload,null,2).slice(0,2500);
    const promptStr=String(r.prompt||"").slice(0,1500);
    box.innerHTML=`<div class="row"><b>Micro-payload (entrada)</b></div><pre style="white-space:pre-wrap;font-size:10px">${escapeHtml(payloadStr)}</pre>
      <div class="row"><b>Prompt (trecho)</b></div><pre style="white-space:pre-wrap;font-size:10px">${escapeHtml(promptStr)}</pre>`;
  }
  try{ await navigator.clipboard.writeText(JSON.stringify({payload:r.payload,prompt:r.prompt},null,2)); if(st) st.textContent+=" · copiado"; }catch{}
});
// auto-refresh monitor when opening popup
setTimeout(()=>{ try{ refreshSkillMonitor(); }catch{} }, 400);


// --- Skill JSON manual (alimentar chat da skill) ---
let __lastSkillPack = null;
function skillFeedStatus(t){ const el=document.getElementById("skillFeedStatus"); if(el) el.textContent=t; }
function skillFeedPreview(text){
  const el=document.getElementById("skillFeedPreview");
  if(el) el.textContent = String(text||"").slice(0,2500);
}
async function refreshSkillPack(){
  skillFeedStatus("Gerando…");
  try{
    const r = await chrome.runtime.sendMessage({type:"EXPORT_SKILL_PACK"});
    if(!r?.ok){ skillFeedStatus("Erro: "+(r?.error||"falha")); return null; }
    __lastSkillPack = r;
    const j = r.json || r.pack;
    const name = r.filename || "cornerai_skill_feed.json";
    skillFeedPreview(JSON.stringify(j, null, 2));
    const m = j?.match || j?.live || {};
    const br = r.bridgeOk ? " · salvo no bridge" : (r.bridgeErr ? " · bridge: "+r.bridgeErr : "");
    skillFeedStatus(`OK · ${m.home||"?"} x ${m.away||"?"} · ${m.minute??"—"}' · ${name}${br}`);
    return r;
  }catch(e){
    skillFeedStatus("Erro: "+(e?.message||e));
    return null;
  }
}
document.getElementById("skillJsonBtn")?.addEventListener("click", async()=>{
  await refreshSkillPack();
});
document.getElementById("skillCopyBtn")?.addEventListener("click", async()=>{
  let r = __lastSkillPack;
  if(!r) r = await refreshSkillPack();
  if(!r?.ok) return;
  const text = r.pasteText || JSON.stringify(r.json||r.pack, null, 2);
  try{
    await navigator.clipboard.writeText(text);
    skillFeedStatus((document.getElementById("skillFeedStatus")?.textContent||"")+" · copiado");
  }catch(e){
    skillFeedStatus("Falha ao copiar: "+(e?.message||e));
  }
});
document.getElementById("skillDlBtn")?.addEventListener("click", async()=>{
  let r = __lastSkillPack;
  if(!r) r = await refreshSkillPack();
  if(!r?.ok) return;
  // [FIX v6.9.9.67] aborta o download se a validação estrita encontrou dado corrompido/ausente
  if(r.validation && !r.validation.ok){
    skillFeedStatus(`Download bloqueado: ${r.validation.errors.length} erro(s) de validação (ver console)`);
    return;
  }
  const body = r.pasteText || JSON.stringify(r.json||r.pack, null, 2);
  const name = r.filename || "cornerai_skill_feed.json";
  const blob = new Blob([body], {type: name.endsWith(".md")?"text/markdown;charset=utf-8":"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 2000);
  skillFeedStatus("Download: "+name);
});

// --- Coleta histórica em lote ---
let __batchPoll=null;
function renderBatchJob(job){
  const st=document.getElementById("batchStatus");
  const box=document.getElementById("batchList");
  if(!job){ if(st) st.textContent="Pronto · bridge precisa estar ligado"; return; }
  const prog=job.running?`Rodando ${job.index}/${job.total}`:(job.finishedAt?`Concluído ${job.ok} ok · ${job.fail} falha`:"Pronto");
  if(st) st.textContent=`${prog}${job.current?` · atual ${job.current}`:""}${job.lastError?` · ${job.lastError}`:""}`;
  if(box){
    const rows=job.items||[];
    box.innerHTML=rows.length?rows.map(it=>{
      const mark=it.status==="ok"?"✓":it.status==="fail"?"✗":it.status==="running"?"…":it.status==="skipped"?"–":"·";
      return `<div class="row"><b>${mark} ${escapeHtml(it.fixtureId)}</b> · ${escapeHtml(it.status)}${it.detail?` · ${escapeHtml(it.detail)}`:""}</div>`;
    }).join(""):"";
  }
}
async function pollBatch(){
  try{
    const r=await chrome.runtime.sendMessage({type:"GET_BATCH_STATUS"});
    if(r?.ok) renderBatchJob(r.job);
    if(r?.job?.running) return;
  }catch{}
  if(__batchPoll){ clearInterval(__batchPoll); __batchPoll=null; }
}
document.getElementById("batchScanBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("batchStatus");
  if(st) st.textContent="Detectando fixtures na aba…";
  try{
    const r=await chrome.runtime.sendMessage({type:"SCAN_PAGE_FIXTURES"});
    if(!r?.ok){ if(st) st.textContent=r?.error||"Falha ao detectar"; return; }
    const lines=(r.fixtures||[]).map(f=>f.url||f.fixtureId).join("\n");
    const ta=document.getElementById("batchLines");
    if(ta) ta.value=lines;
    if(st) st.textContent=`${r.count||0} fixture(s) detectada(s) · revise e clique Iniciar lote`;
    renderBatchJob({running:false,total:r.count||0,index:0,ok:0,fail:0,items:(r.fixtures||[]).map(f=>({fixtureId:f.fixtureId,status:"queued",detail:f.label||""}))});
  }catch(e){ if(st) st.textContent=e.message; }
});
document.getElementById("batchStartBtn")?.addEventListener("click",async()=>{
  const st=document.getElementById("batchStatus");
  const ta=document.getElementById("batchLines");
  const lines=String(ta?.value||"").split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  if(!lines.length){ if(st) st.textContent="Cole URLs/IDs ou use Detectar na aba"; return; }
  if(st) st.textContent="Iniciando lote…";
  try{
    const r=await chrome.runtime.sendMessage({type:"START_BATCH_HISTORICAL",lines});
    if(!r?.ok){ if(st) st.textContent=r?.error||"Falha ao iniciar"; return; }
    renderBatchJob(r.job);
    if(__batchPoll) clearInterval(__batchPoll);
    __batchPoll=setInterval(pollBatch,1200);
  }catch(e){ if(st) st.textContent=e.message; }
});
document.getElementById("batchStopBtn")?.addEventListener("click",async()=>{
  try{
    const r=await chrome.runtime.sendMessage({type:"STOP_BATCH_HISTORICAL"});
    renderBatchJob(r?.job);
  }catch{}
});

// --- Auto-salvar jogos do dia ---
async function refreshDailySave(){
  const st=document.getElementById("dailySaveStatus");
  const ck=document.getElementById("dailySaveEnabled");
  try{
    const r=await chrome.runtime.sendMessage({type:"GET_DAILY_SAVE"});
    if(ck && r?.enabled!=null) ck.checked=!!r.enabled;
    if(st){
      const n=(r?.savedToday||[]).length;
      const last=r?.last;
      st.textContent=r?.ok
        ? `Dia ${r.day||"—"} · ${n} jogo(s) salvos`+(last?` · último ${last.home||"?"}×${last.away||"?"} (${last.fixtureId||""})`:"")
        : (r?.error||"—");
    }
  }catch(e){ if(st) st.textContent=e.message; }
}
document.getElementById("dailySaveEnabled")?.addEventListener("change",async(e)=>{
  const on=!!e.target.checked;
  await chrome.runtime.sendMessage({type:"SET_DAILY_SAVE",enabled:on});
  refreshDailySave();
});
document.getElementById("dailySaveNow")?.addEventListener("click",async()=>{
  const st=document.getElementById("dailySaveStatus");
  if(st) st.textContent="Salvando jogo atual…";
  const r=await chrome.runtime.sendMessage({type:"FORCE_DAILY_SAVE",reason:"manual"});
  if(st) st.textContent=r?.ok?(r.skipped?"Já estava salvo hoje":`Salvo · ${r.fixtureId||""}`):(r?.error||"Falha");
  refreshDailySave();
});
document.getElementById("dailySaveRefresh")?.addEventListener("click",refreshDailySave);
refreshDailySave();

try{
  const vb=document.getElementById("visionBtn");
  if(vb) vb.onclick=async()=>{
    // FIX 12.5.9: chrome.sidePanel.open() só funciona dentro do gesto de clique
    // original. Antes ele passava por chrome.runtime.sendMessage → background
    // (contexto separado do service worker) com 2 awaits antes da chamada
    // (ensureStateLoaded + windows.getCurrent), o que invalida a ativação do
    // usuário no Chrome e faz sidePanel.open() falhar silenciosamente,
    // deixando o painel/chat sem abrir e sem reagir aos botões.
    try{
      if(chrome.sidePanel && typeof chrome.sidePanel.open==="function"){
        const w=await chrome.windows.getCurrent();
        await chrome.sidePanel.open({windowId:w.id});
        statusTitle.textContent="Visão IA aberta";
        status.textContent="Side panel";
        window.close();
        return;
      }
    }catch(e){/* cai no fallback abaixo */}
    const r=await msg("OPEN_SIDE_PANEL");
    statusTitle.textContent=r?.ok?"Visão IA aberta":"Visão indisponível";
    status.textContent=r?.ok?String(r.mode||"Side panel"):String(r?.error||"falha ao abrir");
  };
}catch{}

// AURA QUANT-X central UI entry points
document.getElementById("openCentral")?.addEventListener("click", async () => {
  try { await msg("OPEN_CENTRAL"); } catch (e) { console.warn(e); }
});
document.getElementById("openChatK")?.addEventListener("click", async () => {
  try { await msg("OPEN_KANTEIRO_CHAT"); } catch (e) { console.warn(e); }
});
document.getElementById("openLegacyDash")?.addEventListener("click", async () => {
  try { await msg("OPEN_LEGACY_DASHBOARD"); } catch (e) {
    try { await msg("OPEN_DASHBOARD"); } catch (e2) { console.warn(e2); }
  }
});


/* ── Match picker: abas abertas + histórico + ID/URL ── */
let __pickerMode = "live";
async function loadMatchPicker(){
  const box = document.getElementById("pickerList");
  const st = document.getElementById("pickerStatus");
  if(!box) return;
  box.innerHTML = '<div class="picker-empty">Carregando…</div>';
  try{
    if(__pickerMode === "live"){
      const r = await chrome.runtime.sendMessage({type:"GET_LIVE_FEED", limit:40});
      const rows = r?.fixtures || [];
      if(!rows.length){
        box.innerHTML = '<div class="picker-empty">Nenhum jogo detectado. Abra o SokkerPro (livescores) e clique ⟳.</div>';
        if(st) st.textContent = r?.error || "Feed vazio — abra a lista ao vivo no SokkerPro";
        return;
      }
      const cur = await msg("REQUEST_STATE");
      box.innerHTML = rows.map(t=>{
        const score = t.score ? `${t.score.home??"?"}×${t.score.away??"?"}` : "";
        const teams = (t.home && t.away) ? `${t.home} ${score} ${t.away}` : (t.label || ("Fixture "+t.fixtureId));
        const sub = [t.fixtureId?("#"+t.fixtureId):null, t.minute!=null?(t.minute+"'"):null, t.live?"AO VIVO":null, t.source||null].filter(Boolean).join(" · ");
        const on = cur?.fixtureId && String(cur.fixtureId)===String(t.fixtureId);
        return `<button type="button" class="picker-item${on?" active-cap":""}${t.live?" is-live":""}" data-fid="${escapeHtml(t.fixtureId||"")}" data-url="${escapeHtml(encodeURIComponent(t.url||""))}">
          <b>${escapeHtml(teams)}</b><span>${escapeHtml(sub)}</span></button>`;
      }).join("");
      if(st) st.textContent = `${rows.length} jogo(s) no feed — clique para carregar`;
    } else if(__pickerMode === "tabs"){
      const r = await chrome.runtime.sendMessage({type:"LIST_SOKKER_TABS"});
      const tabs = r?.tabs || [];
      if(!tabs.length){
        box.innerHTML = '<div class="picker-empty">Nenhuma aba SokkerPro aberta. Cole o ID/URL abaixo ou abra o site.</div>';
        if(st) st.textContent = "0 abas";
        return;
      }
      const cur = await msg("REQUEST_STATE");
      box.innerHTML = tabs.map(t=>{
        const label = (t.title && t.title.length>8) ? t.title : (t.fixtureId ? ("Fixture "+t.fixtureId) : t.url);
        const sub = [t.fixtureId?("#"+t.fixtureId):null, t.active?"ativa":null].filter(Boolean).join(" · ");
        const on = cur?.fixtureId && t.fixtureId && String(cur.fixtureId)===String(t.fixtureId);
        return `<button type="button" class="picker-item${on?" active-cap":""}" data-tab-id="${escapeHtml(t.tabId||"")}" data-fid="${escapeHtml(t.fixtureId||"")}" data-url="${escapeHtml(encodeURIComponent(t.url||""))}">
          <b>${escapeHtml(label)}</b><span>${escapeHtml(sub||t.url||"")}</span></button>`;
      }).join("");
      if(st) st.textContent = `${tabs.length} aba(s) SokkerPro — clique para carregar`;
    } else {
      const r = await chrome.runtime.sendMessage({type:"GET_MATCH_HISTORY", limit:20});
      const rows = r?.matches || [];
      if(!rows.length){
        box.innerHTML = '<div class="picker-empty">Nenhuma partida recente arquivada ainda.</div>';
        if(st) st.textContent = "Histórico vazio";
        return;
      }
      box.innerHTML = rows.map(m=>{
        const score = `${m.score?.home??"?"}×${m.score?.away??"?"}`;
        const label = `${m.home||"?"} ${score} ${m.away||"?"}`;
        const sub = [m.fixtureId?("#"+m.fixtureId):null, m.competition||null].filter(Boolean).join(" · ");
        return `<button type="button" class="picker-item" data-fid="${escapeHtml(m.fixtureId||"")}" data-url="">
          <b>${escapeHtml(label)}</b><span>${escapeHtml(sub)}</span></button>`;
      }).join("");
      if(st) st.textContent = `${rows.length} recente(s) — clique para reabrir no SokkerPro`;
    }
    box.querySelectorAll(".picker-item").forEach(btn=>{
      btn.addEventListener("click", ()=> openPickerItem(btn));
    });
  }catch(e){
    box.innerHTML = `<div class="picker-empty">Erro: ${escapeHtml(String(e?.message||e))}</div>`;
  }
}
function escapeHtml(s){
  return String(s||"").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}
async function openPickerItem(btn){
  const st = document.getElementById("pickerStatus");
  const statusTitle = document.getElementById("statusTitle");
  const status = document.getElementById("status");
  const tabId = Number(btn.dataset.tabId||0);
  const fid = String(btn.dataset.fid||"").trim();
  let url = "";
  try{ url = decodeURIComponent(btn.dataset.url||""); }catch{ url = btn.dataset.url||""; }
  if(st) st.textContent = "Abrindo e armando captura…";
  if(statusTitle) statusTitle.textContent = "Carregando partida…";
  try{
    const r = await chrome.runtime.sendMessage({
      type:"OPEN_AND_ARM_FIXTURE",
      fixtureId: fid || undefined,
      url: url || undefined,
      tabId: tabId || undefined
    });
    if(!r?.ok){
      if(st) st.textContent = r?.error || "Falha ao carregar";
      if(statusTitle) statusTitle.textContent = "Falha";
      if(status) status.textContent = r?.error || "Tente de novo";
      return;
    }
    if(st) st.textContent = `OK · fixture ${r.fixtureId} · snaps ${r.acceptedSnapshots||0}`;
    if(statusTitle) statusTitle.textContent = "Captura ativa";
    if(status) status.textContent = `${r.home||"?"} × ${r.away||"?"} · #${r.fixtureId}`;
    await refresh();
    await loadMatchPicker();
  }catch(e){
    if(st) st.textContent = String(e?.message||e);
  }
}
async function openFixtureFromInput(){
  const input = document.getElementById("fixtureInput");
  const raw = String(input?.value||"").trim();
  if(!raw){ const st=document.getElementById("pickerStatus"); if(st) st.textContent="Cole um ID ou URL"; return; }
  let fid="", url="";
  if(/^https?:\/\//i.test(raw)){
    url = raw;
    const m = raw.match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
    if(m) fid = m[1];
  } else if(/^\d{5,}$/.test(raw)){
    fid = raw;
    url = `https://sokkerpro.com/fixture/${fid}`;
  } else {
    const st=document.getElementById("pickerStatus"); if(st) st.textContent="Use ID numérico ou URL do SokkerPro"; return;
  }
  const fake = document.createElement("button");
  fake.dataset.fid = fid;
  fake.dataset.url = encodeURIComponent(url);
  await openPickerItem(fake);
}
document.getElementById("openFixtureBtn")?.addEventListener("click", openFixtureFromInput);
document.getElementById("refreshPickerBtn")?.addEventListener("click", loadMatchPicker);
document.getElementById("fixtureInput")?.addEventListener("keydown", e=>{ if(e.key==="Enter") openFixtureFromInput(); });
document.querySelectorAll(".picker-tab").forEach(tab=>{
  tab.addEventListener("click", ()=>{
    document.querySelectorAll(".picker-tab").forEach(t=>t.classList.remove("on"));
    tab.classList.add("on");
    __pickerMode = tab.dataset.picker || "tabs";
    loadMatchPicker();
  });
});
loadMatchPicker();
