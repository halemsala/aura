const DIAGNOSTIC_VERSION="12.7.0";
// Compatibilidade de contrato legado é mantida apenas nos nomes de campos; a versão efetiva vem do manifesto.

function runtime(type,payload={}){
  return new Promise(resolve=>{
    try{
      chrome.runtime.sendMessage({type,...payload},r=>{
        const err=chrome.runtime.lastError;
        if(err)return resolve({ok:false,error:err.message});
        resolve(r||{ok:false,error:"background sem resposta"});
      });
    }catch(e){resolve({ok:false,error:e?.message||String(e)})}
  });
}

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const num=v=>{const n=Number(v);return Number.isFinite(n)?n:0};

async function probeLocalService(name,url){
  const started=performance.now();
  const ctrl=typeof AbortController!=="undefined"?new AbortController():null;
  const timer=ctrl?setTimeout(()=>ctrl.abort(),2200):null;
  try{
    const r=await fetch(url,{method:"GET",cache:"no-store",signal:ctrl?.signal});
    const data=await r.json().catch(()=>null);
    return {name,url,ok:r.ok,status:r.status,latencyMs:Math.round(performance.now()-started),detail:r.ok?"HTTP online":String(data?.error||`HTTP ${r.status}`)};
  }catch(e){
    const raw=String(e?.message||e||"erro desconhecido");
    const low=raw.toLowerCase();
    const detail=low.includes("abort")||low.includes("timeout")?"timeout: nenhum health respondeu em 2,2s":"sem conexão: nenhum processo respondeu nessa porta";
    return {name,url,ok:false,status:0,latencyMs:Math.round(performance.now()-started),detail:`${detail} (${raw})`};
  }finally{if(timer)clearTimeout(timer)}
}
async function probeLocalServices(){
  return Promise.all([
    probeLocalService("Bridge","http://127.0.0.1:8080/health"),
    probeLocalService("Engine","http://127.0.0.1:8765/health"),
    probeLocalService("Voice","http://127.0.0.1:8099/api/voice/health")
  ]);
}
const clean=v=>String(v??"").replace(/\s+/g," ").trim().slice(0,240);

function analyzeCharts(page,state){
  const c=state?.chartsUnified||state?.charts||page?.snapshot?.charts||page?.charts||{};
  const pc=page?.pageDiag||{};
  const sh=page?.activationDiag?.siteHealth||{};
  // tabs pode ser array de strings ou objetos {id}
  const tabList=Array.isArray(c.tabs)?c.tabs:[];
  const tabs=Math.max(tabList.length, Number(c.tabCount||0), Number(c.signals?.tabCount||0));
  const series=Math.max(Number(c.seriesCount||0), Array.isArray(c.series)?c.series.length:0);
  const loading=Number(sh.loadingNodes||pc.loadingNodes||0);
  const mutationRate=Number(sh.chartMutations||pc.chartMutations||0);
  const problems=[];
  // Mesma regra do bloco report.charts + pressure-dual do integrity
  const barKeys = (c.pressureBars && typeof c.pressureBars === "object") ? Object.keys(c.pressureBars).length : 0;
  const pressureN=Math.max(
    Number(c.pressureIntervals||0)||0,
    Array.isArray(c.pressureIntervals)?c.pressureIntervals.length:0,
    barKeys,
    Number(c.signals?.pressureBlocks||0)||0,
    Array.isArray(c.history)?c.history.length:0,
    // fallback: integrity pressure-dual good count quando state.charts ainda vazio no 1º tick
    Number(state?.integrity?.checks?.find?.(x=>x.id==="pressure-dual")?.detail?.match?.(/good\s+(\d+)/)?.[1]||0)
  );
  const effectiveSeries=Math.max(series, pressureN);
  if(effectiveSeries===0) problems.push("Nenhuma série de gráfico disponível");
  if(tabs>0&&effectiveSeries===0) problems.push("abas de gráficos existem mas nenhuma série foi capturada");
  if(loading>0 && effectiveSeries===0) problems.push(`${loading} elemento(s) ainda mostram Loading/Sem dados`);
  if(mutationRate>80) problems.push(`alta mutação dos gráficos (${mutationRate}) — possível piscar/re-render`);
  if(Number(pc.longTasks||0)>5) problems.push(`muitos long tasks durante captura (${pc.longTasks})`);
  const softProblems=problems.filter(p=>{
    if(effectiveSeries>0 && /Loading|Sem dados|Nenhuma série|abas de gráficos/i.test(p)) return false;
    return true;
  });
  const ok = effectiveSeries>0 || softProblems.length===0;
  return {
    ok,
    series:effectiveSeries,
    pressureIntervals:pressureN,
    tabs,
    loadingNodes:loading,
    chartMutations:mutationRate,
    longTasks:Number(sh.longTasks||pc.longTasks||0),
    zeroSizeCharts:Number(sh.zeroSizeCharts||0),
    visibleCharts:Number(sh.visibleCharts||page?.activationDiag?.domChecks?.find?.(x=>x.id==="charts-area")?.ok?1:0),
    problems:softProblems
  };
}
function classifyPageErrors(page){
  const errs=[...(page?.pageDiag?.errors||[]),...(page?.pageDiag?.rejections||[])];
  const own=errs.filter(e=>/cornerai|extension|chrome-extension/i.test(JSON.stringify(e)));
  const site=errs.filter(e=>!own.includes(e));
  return {total:errs.length,extensionRelated:own.length,siteRelated:site.length,extensionErrors:own.slice(-10),siteErrors:site.slice(-10)};
}

async function findSokkerTab(){
  const isSokker=t=>/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(t?.url||"");
  try{
    // Diagnóstico pode estar em janela própria. Nunca tratar a própria janela
    // do diagnóstico como origem da partida.
    const target=await runtime("GET_CAPTURE_TARGET");
    if(target?.tabId){
      try{
        const t=await chrome.tabs.get(Number(target.tabId));
        if(t?.id&&isSokker(t)) return t;
      }catch{}
    }
    const active=await chrome.tabs.query({active:true,currentWindow:true});
    const current=active.find(isSokker);
    if(current)return current;
    const all=await chrome.tabs.query({});
    return all.filter(isSokker).sort((a,b)=>(b.lastAccessed||0)-(a.lastAccessed||0))[0]||null;
  }catch{return null}
}

function askPage(tab){
  return new Promise(resolve=>{
    if(!tab?.id)return resolve({ok:false,error:"nenhuma aba SokkerPRO",tabId:null});
    try{
      chrome.tabs.sendMessage(tab.id,{type:"COLLECT_DIAGNOSTICS"},r=>{
        const err=chrome.runtime.lastError;
        if(err)return resolve({ok:false,error:err.message,tabId:tab.id,url:tab.url});
        resolve(r||{ok:false,error:"content script sem resposta",tabId:tab.id,url:tab.url});
      });
    }catch(e){resolve({ok:false,error:e?.message||String(e),tabId:tab.id,url:tab.url})}
  });
}

function pageSnapshot(page){
  return page?.snapshot||{};
}

function activationSection(page, bg){
  const ad = page?.activationDiag || bg?.state?.diagnostics?.lastActivationDiag || null;
  if(!ad) return { available:false, note:"Nenhum ciclo de ativação registrado ainda. Arme a captura numa partida SokkerPRO." };
  return {
    available:true,
    severity: ad.severity || "unknown",
    summary: ad.summary || "",
    ok: !!ad.ok,
    trigger: ad.trigger || null,
    at: ad.at || null,
    counts: ad.counts || {},
    messaging: ad.messaging || null,
    domRequiredFailed: ad.dom?.requiredFailed || [],
    runtimeErrors: (ad.runtimeErrors||[]).slice(0,8),
    networkFailures: (ad.networkFailures||[]).slice(0,8)
  };
}


function buildHealth(result){
  const bg=result?.background||{};
  const state=bg?.state||{};
  const cap=state.capture||{};
  const d=state.diagnostics||{};
  const page=result?.page||{};
  const pc=page.capture||{};
  const snap=pageSnapshot(page);
  // 9.2.8: never under-report accepts — messaging / snapshotCount / content ack can lead
  const accepted=Math.max(
    num(cap.acceptedSnapshots),
    num(state.snapshotCount),
    num(result?.messaging?.contentToBackground?.response?.acceptedSnapshots),
    num(result?.activation?.messaging?.contentToBackground?.response?.acceptedSnapshots),
    num(pc.lastBackgroundAck?.acceptedSnapshots),
    num(page?.backgroundAck?.acceptedSnapshots)
  );
  // 9.2.2: lastCapture is a TIMESTAMP, not a counter. Treat any attempt/dispatch as evidence.
  const attempted=num(pc.lastCaptureAttempt)>0 || num(pc.lastCapture)>0 || num(pc.lastDispatchAt)>0 || num(pc.lastCaptureSuccess)>0;
  const sent=Math.max(num(pc.lastSentAt)>0?1:0, accepted>0?1:0, num(pc.lastDispatchAt)>0 && (pc.lastDispatchResult?.ok||pc.lastDispatchResult?.accepted)?1:0);
  const captures=Math.max(attempted?1:0, accepted>0?1:0);
  const statRows=num(page.statRows);
  const hasTeams=!!(page.teams?.home&&page.teams?.away);
  const hasScore=!!page.score;
  const hasStats=Object.keys(snap.stats||{}).length>0 ||
                  Object.keys(snap.extendedStats||{}).length>0 ||
                  Object.keys(snap).some(k=>/^(attacks|dangerous|shots|corners|xg|possession)$/.test(k));

  let pipeline="indeterminado";
  // 9.2.4: background evidence wins (harvest path)
  const bgHasData = accepted>0 || num(state.snapshotCount)>0 || !!(state.home&&state.away) || (state.score&&state.score.home!=null) || num(state.minute)>0;
  if(bgHasData) pipeline="OK";
  else if(captures===0) pipeline="DOM → sem captura";
  else if(captures>0 && sent===0) pipeline="DOM → envio quebrado";
  else if(sent>0 && accepted===0) pipeline="envio → background/rejeição";
  else pipeline="OK";

  const eventIntegrity=result?.background?.eventIntegrity||{total:num(state.eventCount),unique:num(state.eventCount),duplicates:0};
  const contract=result?.background?.captureContract||{};
  const captureExpected=!!contract.manualConsent||!!contract.armed||!!pc.manualConsent||!!pc.armed;

  const checks=[
    {id:"tab",ok:!!result?.tab,message:result?.tab?"aba SokkerPRO encontrada":"nenhuma aba SokkerPRO encontrada"},
    {id:"content",ok:page.ok===true,message:page.ok===true?"content script respondeu":"content script indisponível"},
    {id:"fixture",ok:!!(page.fixtureId||state.fixtureId||(page.teams?.home&&page.teams?.away)||(state.home&&state.away)),message:(page.fixtureId||state.fixtureId)?`fixture ${page.fixtureId||state.fixtureId}`:((page.teams?.home&&page.teams?.away)||(state.home&&state.away)?`${page.teams?.home||state.home}×${page.teams?.away||state.away} (id pendente)`:"fixture ausente")},
    {id:"dom",ok:num(page.bodyLength)>0||num(accepted)>0||num(statRows)>0,message:num(page.bodyLength)>0?`${num(page.bodyLength)} caracteres no DOM`:(num(accepted)>0||num(statRows)>0?"DOM útil via snapshot (bodyLength=0 no momento do diagnóstico)":"DOM vazio")},
    {id:"capture",ok:!captureExpected||captures>0||bgHasData,message:!captureExpected?"captura não armada — aguardando comando explícito":(captures>0||bgHasData)?"captura executada":"nenhuma captura executada"},
    {id:"send",ok:!captureExpected||sent>0,message:!captureExpected?"não aplicável até armar a captura":sent>0?"snapshot saiu do content script":"snapshot não foi enviado"},
    {id:"accept",ok:!captureExpected||accepted>0,message:!captureExpected?"não aplicável até armar a captura":accepted>0?`${accepted} snapshot(s) aceito(s)`:"background aceitou 0 snapshots"},
    {id:"state",ok:num(state.snapshotCount)>0 || accepted>0 || hasStats || hasTeams || hasScore,
      message:(num(state.snapshotCount)>0||accepted>0||hasStats||hasTeams||hasScore)?"estado contém dados":"estado sem dados"},
    {id:"dispatch",ok:num(d.captureDispatchFailures)===0,message:`falhas de envio: ${num(d.captureDispatchFailures)}`},
    {id:"persist",ok:num(d.persistErrors)===0,message:`erros de persistência: ${num(d.persistErrors)}`},
    {id:"bridge",ok:!(state.webhook?.bridgeOffline),message:state.webhook?.bridgeOffline?`bridge offline · outbox ${Number((state.outbox||[]).length)}`:"bridge online"},
    {id:"foreign",ok:num(d.foreignFixturePayloads)===0,message:`payloads de outra partida: ${num(d.foreignFixturePayloads)}; aba externa rejeitada: ${num(d.foreignTabPayloads)} (isolamento)`},
    {id:"active-tab",ok:!contract.armed||contract.activeTabId!=null,message:contract.armed?`aba ativa ${contract.activeTabId??"ausente"}`:"captura não armada"},
    {id:"manual-contract",ok:contract.manualOnly!==false && (!!contract.manualOnly===true || contract.armed===false),message:contract.armed?`captura manual ativa (${contract.activeTabId??"aba?"})`:"captura manual não armada"},
    {id:"event-integrity",ok:num(eventIntegrity.duplicates)===0,message:`eventos únicos ${num(eventIntegrity.unique)}/${num(eventIntegrity.total)}; duplicados persistidos: ${num(eventIntegrity.duplicates)}`},
    {id:"page-errors",ok:Number(result?.page?.pageDiag?.errors?.length||0)+Number(result?.page?.pageDiag?.rejections?.length||0)===0,message:`erros/rejeições da página: ${Number(result?.page?.pageDiag?.errors?.length||0)+Number(result?.page?.pageDiag?.rejections?.length||0)}`},
    {id:"chart-runtime",ok:Number(result?.page?.pageDiag?.longTasks?.length||0)<6,message:`long tasks >80ms: ${Number(result?.page?.pageDiag?.longTasks?.length||0)}`},
    {id:"chart-mutations",ok:Number(result?.page?.pageDiag?.chartMutations||0)<80,message:`mutações dos gráficos: ${Number(result?.page?.pageDiag?.chartMutations||0)}`},
    {id:"chart-data",ok:Number(state?.chartsUnified?.seriesCount||state?.charts?.seriesCount||0)>0 || Number(state?.chartsUnified?.readyCount||0)>0,message:`séries capturadas: ${Number(state?.chartsUnified?.seriesCount||state?.charts?.seriesCount||0)}`}
  ];

  return {
    pipeline,
    captures,
    snapshotsSent:sent>0?1:0,
    snapshotsAccepted:accepted,
    snapshotCount:num(state.snapshotCount),
    statRows,
    hasTeams,hasScore,hasStats,
    fixtureId:page.fixtureId??state.fixtureId??null,
    contentScript:page.ok===true?"connected":"disconnected",
    hook:page.hookActive===true?"active":page.hookActive===false?"inactive":"unknown",
    forceCapture:result?.forceResult?.ok===true?"ok":result?.forceResult?.ok===false?"failed":"unknown",
    duplicateEvents:num(d.duplicateEvents), snapshotDuplicates:num(d.snapshotDuplicates),
    duplicateEventDetections:num(d.duplicateEventDetections),
    persistedEventDuplicates:num(eventIntegrity.duplicates),
    unknownStatsRecovered:num(d.unknownStatsRecovered),
    extendedStats:num(d.extendedStats),
    lastCaptureAt:num(pc.lastCapture), acceptedPerCapture:captures>0?Number((num(state.snapshotCount||0)/captures).toFixed(2)):0,
    checks
  };
}

function severityOf(error){
  if(!error) return "ok";
  const e=String(error).toUpperCase();
  if(e.includes("CONTENT SCRIPT")||e.includes("INDISPONÍVEL")||e.includes("INDISPONIVEL")
     ||e.includes("BACKGROUND")||e.includes("SERVICE WORKER")
     ||e.includes("NENHUMA ABA")||e.includes("ENVIO QUEBRADO")
     ||e.includes("DOM → SEM CAPTURA")||e.includes("MOTOR DOM")) return "critical";
  if(e.includes("FIXTURE")||e.includes("REJEIT")||e.includes("PERSIST")||e.includes("FALHAS NO ENVIO")) return "high";
  return "medium";
}

function rootError(result){
  const h=result.health||buildHealth(result);
  const state=result?.background?.state||{};
  const d=state.diagnostics||{};
  const page=result?.page||{};
  const force=result?.forceResult||{};

  if(result?.background?.ok===false) return `BACKGROUND | ${clean(result.background.error||"service worker sem resposta")}`;
  if(!result?.tab)return "CAPTURA | nenhuma aba SokkerPRO encontrada";
  // Content script failure is CRITICAL — always surface it first
  if(page.ok===false && force.ok===false)return `CAPTURA | ${clean(force.error||page.error||"Content script indisponível. Recarregue a aba do SokkerPRO.")}`;
  if(page.ok===false)return `CAPTURA | content script: ${clean(page.error||"sem resposta — recarregue a aba")}`;
  if(!Boolean(result?.background?.captureContract?.manualConsent||result?.background?.captureContract?.armed||page?.capture?.manualConsent||page?.capture?.armed)){
    return null;
  }
  if(force.ok===false && /content script|indispon/i.test(String(force.error||"")))
    return `CAPTURA | ${clean(force.error)}`;
  const hasTeamsNow=!!(page.teams?.home&&page.teams?.away)||!!(state.home&&state.away);
  if(!h.fixtureId && !hasTeamsNow)return "FIXTURE | identificador da partida não encontrado";
  // times presentes sem id numérico: aviso, não erro crítico (SPA sem /fixture/ na URL)
  // bodyLength===0 sozinho NÃO é erro se o pipeline já aceitou snapshots/stats.
  const hasUsefulData = num(h.snapshotsAccepted)>0 || num(h.statRows)>0 || num(h.snapshotCount)>0
    || !!(page.teams?.home && page.teams?.away) || !!(page.score)
    || Object.keys(pageSnapshot(page)||{}).length>3;
  if(num(page.bodyLength)===0 && !hasUsefulData)return "DOM | página sem conteúdo";
  if(h.pipeline==="DOM → sem captura")return "CAPTURA | motor DOM não executou nenhuma captura";
  if(h.pipeline==="DOM → envio quebrado")return "CAPTURA | captura executou mas snapshot não foi enviado";
  if(h.pipeline==="envio → background/rejeição"){
    if(num(d.foreignFixturePayloads)>0)return "FIXTURE | snapshot enviado foi rejeitado por divergência de partida";
    if(num(d.foreignTabPayloads)>0)return "TAB | snapshot enviado foi rejeitado por divergência de aba";
    return "CAPTURA | snapshot enviado mas background aceitou 0";
  }
  if(num(d.captureDispatchFailures)>0)return "CAPTURA | falhas no envio";
  if(num(d.persistErrors)>0)return "STORAGE | erro de persistência";
  // Bridge offline não invalida a captura DOM/background: os dados ficam preservados no outbox.
  // O status do Bridge é reportado como aviso separado.
  if(num(result?.background?.eventIntegrity?.duplicates)>0)return "EVENTOS | evento duplicado";
  return null;
}

function makeReport(result){
  const health=buildHealth(result);
  result.health=health;
  const bg=result?.background||{};
  const state=bg?.state||{};
  const d=state?.diagnostics||{};
  const page=result?.page||{};
  const snap=pageSnapshot(page);
  const error=rootError(result);
  const serviceFailures=(Array.isArray(result?.services)?result.services:[]).filter(s=>!s.ok).map(s=>({id:`service-${String(s.name||"unknown").toLowerCase()}`,message:`${s.name||"serviço"} offline · ${s.detail||"sem resposta"}`,url:s.url||null,latencyMs:s.latencyMs??null}));
  const severityBase=severityOf(error);
  const severity=severityBase==="ok"&&serviceFailures.length?"warning":severityBase;
  const failedChecks=[...(health.checks||[]).filter(c=>!c.ok).map(c=>({id:c.id,message:c.message})),...serviceFailures];

  // Relatório compacto + severidade sempre visível para erros graves.
  const report={
    error:error||null,
    severity,
    version:state?.version||DIAGNOSTIC_VERSION,
    fixtureId:health.fixtureId??null,
    capture:health.captures>0,
    sent:health.snapshotsSent>0,
    accepted:health.snapshotsAccepted>0,
    snapshots:Number(health.snapshotCount||0),
    stats:Number(health.statRows||0),
    // Sempre expõe pipeline e content script — nunca esconde falha crítica
    pipeline:health.pipeline||"indeterminado",
    contentScript:health.contentScript||"unknown",
    failedChecks:failedChecks.length?failedChecks:undefined,
    criticalAlert:severity==="critical"?String(error):undefined,
    serviceFailures:serviceFailures.length?serviceFailures:undefined,
    activation: activationSection(page, bg),
    siteErrors: classifyPageErrors(page),
    chartsHealth: null, // recalculado após bloco charts
    eventosFlask: null, // preenchido em render()
    allToolsTest: d.lastToolTest ? {
      schema:d.lastToolTest.schema||null,
      fixtureId:d.lastToolTest.fixtureId||null,
      durationMs:Number(d.lastToolTest.durationMs||0),
      summary:d.lastToolTest.summary||null,
      results:Array.isArray(d.lastToolTest.results) ? d.lastToolTest.results.map(x=>({id:x.id||null,label:x.label||null,status:x.status||null,detail:clean(x.detail||"")})) : [],
      background:d.lastToolTest.background||null,
      capturedAt:d.lastToolTest.finishedAt||d.lastToolTest.startedAt||null
    } : null,
    services:Array.isArray(result?.services)?result.services:[],
    telemetry: {
      diagCount: Number(d.diagCount||0),
      lastDiagAt: d.lastDiagAt||null,
      lastCritical: d.lastCritical||null,
      // Compact by design: expose only the last root diagnostic event.
      // Full timeline/health samples created very large JSON without improving root-cause analysis.
      lastCritical: d.lastCritical?{
        level:d.lastCritical.level||null,
        layer:d.lastCritical.layer||null,
        code:d.lastCritical.code||null,
        message:clean(d.lastCritical.message||""),
        fixtureId:d.lastCritical.fixtureId||null,
        at:d.lastCritical.at||null
      }:null
    },
    layers: (function(){
      const ld=state.layerDiag||{};
      const wh=state.webhook||{};
      const out=Array.isArray(state.outbox)?state.outbox:[];
      return {
        outbox:{pending:out.length,sent:Number(wh.sent||0),failed:Number(wh.failed||0),dropped:Number(wh.dropped||0),lastError:wh.lastError||null,lastOkAt:wh.lastOkAt||0,bridgeOffline:!!wh.bridgeOffline,hint:wh.bridgeOffline?"Bridge offline — rode: python bridge/server.py":(out.length>0&&!wh.lastOkAt?"Outbox pending, bridge nunca respondeu":"ok")},
        storage:{bytes:ld.storageBytes??null,idbCount:ld.idbCount??null,idbEnabled:true},
        ws:{binaryDecoded:Number(d.binaryWsDecoded||ld.binaryWsDecoded||0),binaryUnknown:Number(d.binaryWsUnknown||ld.binaryWsUnknown||0),hookMessages:Number(d.hookMessages||ld.hookMessages||0),networkResponses:Number(d.networkResponses||ld.networkResponses||0),chunkStats:(page&&page.chunkStats)||{buffered:0,flushed:0,overflow:0,complete:0,timeout:0,note:"no-active-chunks"}},
        isolation:{foreignFixture:Number(d.foreignFixturePayloads||ld.foreignFixture||0),foreignTab:Number(d.foreignTabPayloads||ld.foreignTab||0)},
        gemini:{fallback:!!(d.geminiFallback||ld.geminiFallback),lastAt:d.geminiLastAt||ld.geminiLastAt||null,lastError:d.geminiLastError||ld.geminiLastError||null},
        alarms:Array.isArray(ld.alarms)?ld.alarms:[],
        layerDiagAt:ld.at||null
      };
    })()
  };
  // Prefer semantic coverage from state when CSS row count is 0 (panel hidden / layout drift).
  const st=state.statStatus||{};
  const confirmed=Object.values(st).filter(m=>m&&["CONFIRMED","RECOVERED","ZERO"].includes(String(m.status||"").toUpperCase())).length;
  const fromState=Object.values(state.stats||{}).filter(v=>v&&(v.home!=null||v.away!=null)).length;
  if(report.stats===0 && (confirmed>0||fromState>0)){
    report.stats=Math.max(confirmed,fromState);
    report.statsSource="state";
  } else if(report.stats>0){
    report.statsSource="dom-rows";
  }


  // Advanced diagnostics: always attach a compact summary of statMeta + xG provenance.
  // Full detail expands only when there is an error OR an explicit xG conflict.
  const xgProv=state.xgProvenance||snap.xgMeta||null;
  const statStatus=state.statStatus||snap.statMeta||null;
  const hasXgConflict=!!(xgProv&&xgProv.conflict);
  const statusSummary={};
  if(statStatus&&typeof statStatus==="object"){
    for(const [k,meta] of Object.entries(statStatus)){
      if(!meta||typeof meta!=="object")continue;
      statusSummary[k]=String(meta.status||"UNKNOWN");
    }
  }
  if(Object.keys(statusSummary).length){
    report.statStatus=statusSummary;
    // Separate optional MISSING from real errors — these are often absent in SokkerPRO DOM
    const optionalMissing=["offsides","red","subs","crosses","passesFailed"];
    const missingOptional=optionalMissing.filter(k=>String(statusSummary[k]||"").toUpperCase()==="MISSING");
    const confirmed=Object.entries(statusSummary).filter(([,s])=>["CONFIRMED","RECOVERED","ZERO"].includes(String(s).toUpperCase())).map(([k])=>k);
    report.statCoverage={
      confirmed:confirmed.length,
      missingOptional:missingOptional.length?missingOptional:undefined,
      note:missingOptional.length?"MISSING opcionais = fonte não publicou (não é erro de captura)":undefined
    };
  }
  if(xgProv&&typeof xgProv==="object"){
    report.xg={
      home:xgProv.home??null,
      away:xgProv.away??null,
      confidence:xgProv.confidence??null,
      method:xgProv.method??null,
      candidateCount:xgProv.candidateCount??0,
      conflict:xgProv.conflict||null
    };
  }

  // --- Charts (SokkerPRO graph tabs) ---
  const ch=state.charts||snap.charts||{};
  const chartTabs=Array.isArray(ch.tabs)?ch.tabs:[];
  report.charts={
    activeId:ch.activeId||null,
    activeLabel:ch.activeLabel||null,
    tabs:[...new Set(chartTabs.map(t=>t.id||t).filter(Boolean))].slice(0,12),
    tabCount:chartTabs.length,
    seriesCount:Array.isArray(ch.series)?ch.series.length:Number(ch.seriesCount||0),
    pressureIntervals:Math.max(Number(ch.pressureIntervals||0)||0, ch.pressureBars&&typeof ch.pressureBars==="object"?Object.keys(ch.pressureBars).length:0),
    hasMacd:!!(ch.signals&&ch.signals.hasMacd),
    hasAi:!!(ch.signals&&ch.signals.hasAi),
    sources:ch.signals&&Array.isArray(ch.signals.sources)?[...new Set(ch.signals.sources)]:[],
    networkUrls:Array.isArray(ch.networkUrls)?ch.networkUrls.slice(0,5):[],
    bySource:(()=>{const s={};for(const p of (Array.isArray(ch.series)?ch.series:[])){const k=p.src||"unknown";s[k]=(s[k]||0)+1}return s})()
  };
  // chartsHealth alinhado ao mesmo objeto que o relatório exporta
  report.chartsHealth = analyzeCharts(page, {
    ...state,
    charts: {
      ...(state.charts||{}),
      seriesCount: report.charts.seriesCount,
      pressureIntervals: report.charts.pressureIntervals,
      tabs: report.charts.tabs,
      tabCount: report.charts.tabCount,
      pressureBars: (state.charts&&state.charts.pressureBars)||{},
      history: (state.charts&&state.charts.history)||[],
      signals: (state.charts&&state.charts.signals)||{}
    }
  });


  // --- Menus (compact) ---
  const mc=state.menuCapture||{};
  const menuKeys=Object.keys(mc.menus||{});
  const menuIdSet=[...new Set(menuKeys.map(k=>String(k).split("|")[0]).filter(Boolean))];
  const discovered=Array.isArray(mc.discovered)?mc.discovered:[];
  const discoveredIds=[...new Set(discovered.map(x=>typeof x==="string"?x:(x?.id||"")).filter(Boolean))];
  const sweep=mc.sweep||{};
  // Prefer page-level lastResult (written by menu-capture) when state has none
  const pageSweep = (page && page.menuSweep) || null;
  const sweepResult = sweep.lastResult || (pageSweep && pageSweep.lastResult) || null;
  const sweepActive = !!(sweep.active || (pageSweep && pageSweep.active));
  report.menus={
    captured:menuIdSet.filter(id=>id!=="unknown").length || Number(mc.uniqueMenus||0),
    entries:menuKeys.length,
    dataPoints:Number(mc.dataPoints||0),
    lastCaptureAt:mc.lastCaptureAt||0,
    ids:menuIdSet.slice(0,20),
    discovered:discoveredIds.slice(0,20),
    hasStats:discoveredIds.includes("estatisticas")||menuIdSet.includes("estatisticas"),
    hasH2H:discoveredIds.includes("h2h")||menuIdSet.includes("h2h"),
    hasXG:discoveredIds.includes("xg")||menuIdSet.includes("xg"),
    sweep:sweepResult?{
      opened:Number(sweepResult.opened||0),
      restored:!!sweepResult.restored,
      discovered:Number(sweepResult.discovered||0),
      errors:Array.isArray(sweepResult.errors)?sweepResult.errors.length:0,
      at:sweepResult.at||null
    }:(sweepActive?{active:true}:null)
  };

  // --- H2H (compact parameters) ---
  const h2h=state.h2h||{};
  const avg=h2h.averages&&typeof h2h.averages==="object"?h2h.averages:{};
  const params=h2h.parameters&&typeof h2h.parameters==="object"?h2h.parameters:{};
  const summary=h2h.summary&&typeof h2h.summary==="object"?h2h.summary:{};
  report.h2h={
    captured:!!h2h.captured,
    attempted:!!h2h.attempted,
    rootFound:!!h2h.rootFound,
    tables:Array.isArray(h2h.tables)?h2h.tables.length:0,
    matches:Array.isArray(h2h.matches)?h2h.matches.length:0,
    rows:Array.isArray(h2h.rows)?h2h.rows.length:0,
    textLength:String(h2h.text||"").length,
    updatedAt:h2h.updatedAt||0,
    summary:Object.keys(summary).length?summary:null,
    parameters:Object.keys(params).length?params:null,
    averages:Object.keys(avg).length?avg:null
  };

  // ============================================================
  // REVISÃO COMPLETA DOS DADOS CAPTURADOS + APROVAÇÃO
  // ============================================================
  const minute=state.minute!=null?Number(state.minute):(page.minute!=null?Number(page.minute):null);
  const extra=Number(state.extraMinute||page.extraMinute||0)||0;
  const liveStatus=String(state.liveStatus||page.status||page.liveStatus||"unknown");
  const clockDisplay=state.clockDisplay||(liveStatus==="finished"||state.dataMode==="historical"?"FT":null);
  const lastLiveMinute=state.lastLiveMinute!=null?Number(state.lastLiveMinute):(minute!=null?minute:null);
  const lastLiveExtra=Number(state.lastLiveExtra!=null?state.lastLiveExtra:extra)||0;
  const scoreH=state.score?.home??page.score?.home??null;
  const scoreA=state.score?.away??page.score?.away??null;
  const homeName=state.home||page.teams?.home||null;
  const awayName=state.away||page.teams?.away||null;
  const integrity=state.integrity||bg?.integrity||null;
  const integrityChecks=Array.isArray(integrity?.checks)?integrity.checks:(Array.isArray(state.quality?.checks)?state.quality.checks:[]);
  const integrityFailed=integrityChecks.filter(c=>c&&c.ok===false);
  const integrityPassed=integrityChecks.filter(c=>c&&c.ok===true);
  const cornersHome=Number(state.stats?.corners?.home);
  const cornersAway=Number(state.stats?.corners?.away);
  const cornerEvents=(state.cornerEvents||[]);
  const cornerEvH=cornerEvents.filter(e=>e.side==="home").length;
  const cornerEvA=cornerEvents.filter(e=>e.side==="away").length;
  const ageMs=state.lastUpdate?Math.max(0,Date.now()-Number(state.lastUpdate)):null;
  const isFinished=liveStatus==="finished"||state.dataMode==="historical";

  // Clock validation rules
  const clockOk=minute!=null&&Number.isFinite(minute)&&minute>=0&&minute<=130;
  const clockReason=!clockOk
    ?(minute==null?"minuto não capturado":minute<0||minute>130?`minuto fora da faixa (${minute})`:"inválido")
    :(extra>15?`extra alto (${extra}') mas aceito`:null);

  // Build review checklist
  const reviewChecks=[];
  const pushCheck=(id,ok,detail,severity="medium")=>{
    reviewChecks.push({id,ok:!!ok,detail:String(detail||""),severity:ok?"ok":severity});
  };
  pushCheck("clock",clockOk,clockOk?(clockDisplay==="FT"?`FT · último ao vivo ${minute}${extra?`+${extra}`:""}' · ${liveStatus}`:`${minute}${extra?`+${extra}`:""}' · ${liveStatus}`):clockReason,"critical");
  pushCheck("fixture",!!((report.fixtureId||(homeName&&awayName))&&homeName&&awayName),
    report.fixtureId?`${report.fixtureId} · ${homeName||"?"} × ${awayName||"?"}`:(homeName&&awayName?`${homeName} × ${awayName} (id pendente)`:"fixture/times ausentes"),
    report.fixtureId?"critical":(homeName&&awayName?"medium":"critical"));
  pushCheck("score",scoreH!=null&&scoreA!=null&&Number.isFinite(Number(scoreH))&&Number.isFinite(Number(scoreA)),
    scoreH!=null?`${scoreH} × ${scoreA}`:"placar ausente","high");
  pushCheck("pipeline",report.pipeline==="OK",report.pipeline||"indeterminado","critical");
  pushCheck("contentScript",report.contentScript==="connected",report.contentScript||"unknown","critical");
  pushCheck("snapshots",Number(report.snapshots||0)>0,`${report.snapshots||0} aceitos`,"high");
  const liveMinReview=Number(minute)||0;
  // Mesma lógica tolerante do integrity check em background.js (lib/corner-align.js):
  // side-skew ≤1/lado com total batendo não é falha de captura, é defasagem de
  // atribuição de lado entre a stat agregada e o parser de eventos discretos.
  const cornerAlignReview=CornerAILib.evaluateCornerAlign({
    statsHome:cornersHome,statsAway:cornersAway,eventsHome:cornerEvH,eventsAway:cornerEvA,
    liveMinute:liveMinReview,
    isLive:liveStatus==="live",
    hasEventChannel:Number(state.diagnostics?.hookMessages||0)>0
  });
  pushCheck("corners-align", cornerAlignReview.ok, cornerAlignReview.detail, "high");
  pushCheck("xg",report.xg&&report.xg.home!=null&&report.xg.away!=null,
    report.xg?`${report.xg.home} × ${report.xg.away} (${Math.round((report.xg.confidence||0)*100)}%)`:"xG ausente","medium");
  pushCheck("integrity",integrityFailed.length===0,
    integrity?`${integrityPassed.length}/${integrityChecks.length} PASS · score ${integrity.integrityScore??integrity.score??"—"}`:`${integrityPassed.length} checks`,
    "high");
  pushCheck("freshness",isFinished||(ageMs!=null&&ageMs<15000),
    isFinished?"partida finalizada (stale OK)":(ageMs!=null?`${(ageMs/1000).toFixed(1)}s`:"sem timestamp"),
    "medium");
  pushCheck("no-critical-error",!error,error||"sem erro raiz","critical");

  // Integrity detail from background — listed as medium (already counted under "integrity")
  if(integrityChecks.length){
    for(const c of integrityChecks){
      if(!c||!c.id) continue;
      if(c.ok===false){
        pushCheck(`integrity:${c.id}`,false,c.detail||c.message||"FAIL","medium");
      }
    }
  }

  const failedReview=reviewChecks.filter(c=>!c.ok);
  const criticalFails=failedReview.filter(c=>c.severity==="critical");
  // Count unique high-severity families (integrity:* collapses into integrity)
  const highFails=failedReview.filter(c=>c.severity==="high");
  const highUnique=[...new Set(highFails.map(c=>c.id.startsWith("integrity")||c.id==="corners-align"?"integrity":c.id))];

  // Verdict — only REJECT on critical, or 2+ distinct high families
  let verdict="APPROVED";
  let verdictReason="Todos os critérios críticos e de alta prioridade passaram.";
  if(criticalFails.length){
    verdict="REJECTED";
    verdictReason=`Falha crítica: ${criticalFails.map(c=>c.id).join(", ")}`;
  } else if(highUnique.length>=2){
    verdict="REJECTED";
    verdictReason=`Múltiplas falhas de alta prioridade: ${highUnique.join(", ")}`;
  } else if(highUnique.length===1){
    // Single high issue → REVIEW (not hard reject), e.g. corner side-skew
    verdict="REVIEW";
    verdictReason=`Atenção: ${highFails[0].id} — ${highFails[0].detail}`;
  } else if(failedReview.length){
    verdict="APPROVED_WITH_WARNINGS";
    verdictReason=`Aprovado com avisos: ${failedReview.map(c=>c.id).join(", ")}`;
  }

  report.match={
    home:homeName,
    away:awayName,
    score:scoreH!=null&&scoreA!=null?`${scoreH}×${scoreA}`:null,
    minute:minute,
    extraMinute:extra,
    // FT for finished; keep last live minute as secondary so 83' freeze is explained
    clock:clockDisplay==="FT"
      ?(lastLiveMinute!=null?`FT (último ao vivo ${lastLiveMinute}${lastLiveExtra?`+${lastLiveExtra}`:""}')`:"FT")
      :(minute!=null?`${minute}${extra?`+${extra}`:""}'`:null),
    clockDisplay:clockDisplay||null,
    lastLiveMinute:lastLiveMinute,
    lastLiveExtra:lastLiveExtra,
    status:liveStatus,
    dataMode:state.dataMode||null,
    finished:isFinished,
    ageMs:ageMs,
    corners:{stats:[cornersHome,cornersAway],events:[cornerEvH,cornerEvA]},
    events:Number(state.matchEvents?.length||0),
    cornerEvents:cornerEvents.length
  };

  report.review={
    verdict,
    reason:verdictReason,
    approved:verdict==="APPROVED"||verdict==="APPROVED_WITH_WARNINGS",
    needsReview:verdict==="REVIEW",
    rejected:verdict==="REJECTED",
    checkedAt:new Date().toISOString(),
    checksTotal:reviewChecks.length,
    checksPassed:reviewChecks.filter(c=>c.ok).length,
    checksFailed:failedReview.length,
    criticalFails:criticalFails.map(c=>c.id),
    highFails:highFails.map(c=>c.id),
    checks:reviewChecks
  };

  report.integrity={
    score:integrity?.integrityScore??integrity?.score??null,
    pass:integrityFailed.length===0,
    failed:integrityFailed.map(c=>c.id),
    checks:integrityChecks.map(c=>({id:c.id,ok:!!c.ok,detail:c.detail||c.message||""}))
  };

  // Só expõe contexto adicional quando existe uma falha real ou conflito de xG.
  if(error||hasXgConflict||verdict==="REJECTED"){
    report.pipeline=health.pipeline;
    const bgError=bg?.error||d?.lastError||d?.lastBackgroundError||null;
    if(bgError) report.detail=clean(bgError);
    if(Number(d.foreignFixturePayloads||0)>0) report.fixtureRejected=Number(d.foreignFixturePayloads);
    if(Number(d.foreignTabPayloads||0)>0) report.tabRejected=Number(d.foreignTabPayloads);
    if(Number(d.persistErrors||0)>0) report.persistErrors=Number(d.persistErrors);
    if(Number(d.sourceConflicts||0)>0) report.sourceConflicts=Number(d.sourceConflicts);
    // Full multi-source xG candidates when conflict is present.
    if(hasXgConflict&&Array.isArray(xgProv.candidates)&&xgProv.candidates.length){
      report.xgCandidates=xgProv.candidates.slice(0,5).map(c=>({
        home:c.home,away:c.away,method:c.method,confidence:c.confidence??c.score
      }));
    }
    // Per-stat detail only on error path (keeps default report small).
    if(error&&statStatus&&typeof statStatus==="object"){
      const detail={};
      for(const [k,meta] of Object.entries(statStatus)){
        if(!meta||typeof meta!=="object")continue;
        detail[k]={status:meta.status,home:meta.home??null,away:meta.away??null,confidence:meta.confidence??null,method:meta.method||null};
      }
      report.statMeta=detail;
    }
  }

  return report;
}

async function collect(){
  const tab=await findSokkerTab();
  if(!tab?.id){
    try{await runtime("GET_LAYER_DIAG");}catch{}
    const background=await runtime("GET_DIAGNOSTICS");
    const result={background,page:{ok:false,error:"nenhuma aba SokkerPRO"},tab:null,forceResult:{ok:false,ignored:true,error:"nenhuma aba SokkerPRO"},services:await probeLocalServices()};
    result.health=buildHealth(result); return result;
  }

  // READ-ONLY: diagnostico nunca arma captura por conta propria.
  // A captura so inicia no comando explicito do usuario (botao Capturar / popup).
  const initial=await runtime("GET_DIAGNOSTICS");
  const contract=initial?.captureContract||{};
  const alreadyArmed=!!contract.manualConsent&&Number(contract.activeTabId)===Number(tab.id);
  const forceResult=alreadyArmed
    ? {ok:true,ignored:true,phase:"already-armed",activeTabId:tab.id,fixtureId:initial?.state?.fixtureId||null}
    : {ok:false,ignored:true,phase:"diagnostic-read-only",error:"MANUAL_CAPTURE_REQUIRED"};

  let page=await askPage(tab);
  // Somente enriquece menus/H2H quando existe uma sessao de captura ja autorizada.
  if(alreadyArmed){
    try{await runtime("MENU_SWEEP",{options:{allowClicks:false,maxOpen:0}});}catch{}
    await sleep(150);
    try{await runtime("H2H_POLL");}catch{}
    await sleep(250);
    page=await askPage(tab);
  }

  const background=await runtime("GET_DIAGNOSTICS");
  const services=await probeLocalServices();
  const result={background,page,tab,forceResult,services};
  result.health=buildHealth(result);
  return result;
}

async function explicitCapture(){
  const tab=await findSokkerTab();
  if(!tab?.id) return render();
  try{
    await runtime("ARM_ACTIVE_GAME",{tabId:tab.id});
    await sleep(350);
  }catch{}
  return render();
}

async function render(){
  if(!document.getElementById('report')&&!document.getElementById('summary')) return;
  const loading={error:null,diagnosticVersion:DIAGNOSTIC_VERSION,pipeline:"verificando..."};
  setReport(loading);renderSummary(loading);
  try{
    const result=await collect();
    const report=makeReport(result);
    try{
      const ev=await fetchEventosDiag();
      if(ev) report.eventosFlask=ev;
    }catch{}
    setReport(report);renderSummary(report);
    renderAllToolsAudit(report.allToolsTest,report.services);
    refreshFlaskTelemetry().catch(()=>{});
    return report;
  }catch(e){
    const report={error:`SISTEMA | ${clean(e?.message||e)}`,diagnosticVersion:DIAGNOSTIC_VERSION,pipeline:"erro no diagnóstico"};
    setReport(report);renderSummary(report);
    refreshFlaskTelemetry().catch(()=>{});
    return report;
  }
}


function renderSummary(report){
  const el=document.getElementById("summary");
  if(!el)return;
  const layers=report?.layers||{};
  const out=layers.outbox||{};
  const pending=Number(out.pending||0);
  const severity=String(report?.severity||"ok").toLowerCase();
  const tools=Array.isArray(report?.allToolsTest?.results)?report.allToolsTest.results:[];
  const bridgeTool=tools.find(x=>x.id==="bridge");
  const engineTool=tools.find(x=>x.id==="local-ai");
  const services=Array.isArray(report?.services)?report.services:[];
  const bridgeProbe=services.find(x=>x.name==="Bridge");
  const engineProbe=services.find(x=>x.name==="Engine");
  const voiceProbe=services.find(x=>x.name==="Voice");
  const bridgeOffline=!!out.bridgeOffline||bridgeProbe?.ok===false||/offline|failed to fetch|indisponível/i.test(String(bridgeTool?.detail||""));
  const engineOffline=engineProbe?.ok===false||/failed to fetch|offline|indisponível|erro:/i.test(String(engineTool?.detail||""));
  const voiceOffline=voiceProbe?.ok===false;
  const issues=[];
  if(bridgeOffline)issues.push(`Bridge :8080 OFFLINE — ${out.lastError||bridgeProbe?.detail||bridgeTool?.detail||"sem resposta"}`);
  if(engineOffline)issues.push(`Engine :8765 OFFLINE — ${engineProbe?.detail||engineTool?.detail||"sem resposta"}`);
  if(voiceOffline)issues.push(`Voice :8099 OFFLINE — ${voiceProbe?.detail||"sem resposta"}`);
  const title=issues.length?"SERVIÇOS LOCAIS OFFLINE":(report?.error?"DIAGNÓSTICO COM ALERTA":"SISTEMA OPERACIONAL");
  const tone=issues.length||severity==="critical"?"critical":(severity==="warning"||pending>0?"warning":"ok");
  const serviceMeta=services.length?services.map(s=>`${s.name} ${s.ok?"ONLINE":"OFFLINE"} · ${s.latencyMs??"—"}ms`).join(" | "):"health ainda não testado";
  const hint=issues.length
    ? `${issues.join(" · ")} · ${serviceMeta} · execute AURA_INSTALAR_E_INICIAR_TUDO.bat e aguarde os health checks.`
    : (pending>0?`Outbox pendente: ${pending} item(ns).`:(report?.pipeline||"Pipeline verificando..."));
  const fixture=report?.fixtureId?`Fixture ${escapeHtml(report.fixtureId)}`:"Fixture não identificada";
  el.innerHTML=`<div class="diag-summary diag-${tone}">
    <div class="diag-summary-main"><span class="diag-dot"></span><div><strong>${escapeHtml(title)}</strong><span>${fixture}</span></div></div>
    <div class="diag-summary-meta"><span>Pipeline: ${escapeHtml(report?.pipeline||"—")}</span><span>Outbox: ${pending}</span><span>${escapeHtml(hint)}</span></div>
  </div>`;
}
function escapeHtml(v){return String(v??"").replace(/[&<>\"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));}

function renderAllToolsAudit(test,services=[]){
  const box=document.getElementById("allToolsAudit");
  const pill=document.getElementById("allToolsPill");
  if(!box||!pill)return;
  if(!test){pill.textContent="NÃO EXECUTADO";box.textContent="Nenhum teste executado. Use 🧪 Testar TODAS.";return;}
  const sm=test.summary||{};
  pill.textContent=`${Number(sm.pass||0)} PASS · ${Number(sm.fail||0)} FAIL · ${Number(sm.pending||0)} AGUARDANDO`;
  const rows=Array.isArray(test.results)?test.results:[];
  const serviceMap=new Map((Array.isArray(services)?services:[]).map(s=>[s.name,s]));
  box.innerHTML=rows.map(x=>{
    const probe=x.id==="bridge"?serviceMap.get("Bridge"):x.id==="local-ai"?serviceMap.get("Engine"):null;
    const status=probe?probe.ok?"PASS":"FAIL":x.status;
    const icon=status==="PASS"?"🟢":status==="FAIL"?"🔴":"🟡";
    const detail=probe?`${probe.detail} · ${probe.url} · ${probe.latencyMs??"—"}ms`:x.detail||"";
    return `<div class="tool-row"><b>${icon} ${escapeHtml(x.label||x.id||"Ferramenta")}</b><span>${escapeHtml(detail)}</span></div>`;
  }).join("")+`<div class="tool-meta">Fixture ${escapeHtml(test.fixtureId||"—")} · ${Number(test.durationMs||0)} ms · ${rows.length} verificações · health HTTP separado para Bridge/Engine/Voice</div>`;
}

async function runAllToolsFromDiagnostics(){
  const tab=await findSokkerTab();
  const pill=document.getElementById("allToolsPill");
  const box=document.getElementById("allToolsAudit");
  if(!tab?.id){if(pill)pill.textContent="SEM ABA";if(box)box.textContent="Abra uma partida do SokkerPRO.";return render();}
  if(pill)pill.textContent="EXECUTANDO…";
  if(box)box.textContent="Armand o motor e testando todas as famílias de captação…";
  try{
    const r=await runtime("RUN_ALL_TOOLS_TEST",{tabId:tab.id});
    if(r?.ok&&r.report){renderAllToolsAudit(r.report);return render();}
    if(pill)pill.textContent="FALHA";
    if(box)box.textContent=`Falha ao executar: ${clean(r?.error||"sem resposta")}`;
  }catch(e){
    if(pill)pill.textContent="FALHA";
    if(box)box.textContent=`Falha ao executar: ${clean(e?.message||e)}`;
  }
  return render();
}

function setReport(report){
  const el=document.getElementById("report");
  if(el)el.textContent=JSON.stringify(report);
  return report;
}


async function fetchEventosDiag(){
  try{
    const r = await runtime("GET_EVENTOS_DIAG");
    if(r && r.ok) return r.eventos || {enabled:false, optional:true};
    return {enabled:false, optional:true, error:r?.error||"background sem resposta"};
  }catch(e){
    return {enabled:false, optional:true, error:e?.message||String(e)};
  }
}

function fmtTs(ts){
  if(!ts) return "—";
  try{
    const d = new Date(Number(ts));
    if(Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit",second:"2-digit"});
  }catch{ return String(ts); }
}

function renderFlaskTelemetry(ev){
  const box = document.getElementById("flaskTelemetry");
  const pill = document.getElementById("flaskTelePill");
  if(!box) return;
  if(!ev){
    box.textContent = "Telemetria Flask :5000 é legado opcional. Fluxo oficial: Bridge :8080.";
    if(pill) pill.textContent = "OPCIONAL";
    return;
  }
  if(ev.optional && ev.enabled===false){
    if(pill) pill.textContent = ev.error ? "DESATIVADO" : "DESATIVADO";
  }
  const okRate = (ev.sent||0) + (ev.failed||0) > 0
    ? Math.round(100 * (ev.sent||0) / ((ev.sent||0)+(ev.failed||0)))
    : null;
  if(pill){
    if(!ev.enabled) pill.textContent = "DESATIVADO";
    else if(ev.lastOk === true) pill.textContent = "OK";
    else if(ev.lastOk === false) pill.textContent = "FALHA";
    else pill.textContent = "AGUARDANDO";
  }
  const last = ev.lastPayload || {};
  const hist = Array.isArray(ev.history) ? ev.history.slice().reverse() : [];
  const histRows = hist.slice(0,10).map(h=>{
    const icon = h.ok ? "✅" : "❌";
    const lat = h.latencyMs != null ? `${h.latencyMs}ms` : "—";
    const fx = h.fixtureId || "—";
    const teams = [h.home,h.away].filter(Boolean).join(" x ") || "—";
    const min = h.minute != null ? `${h.minute}'` : "—";
    const bytes = h.payloadBytes != null ? `${h.payloadBytes} B` : "—";
    const err = h.error ? ` · ${escapeHtml(h.error)}` : "";
    return `<div class="tool-row"><b>${icon} ${escapeHtml(fmtTs(h.ts))}</b><span>${escapeHtml(teams)} · ${escapeHtml(String(min))} · ${escapeHtml(String(fx))} · ${lat} · ${bytes}${err}</span></div>`;
  }).join("") || `<div class="tool-row"><b>—</b><span>Nenhum POST registrado nesta sessão.</span></div>`;

  box.innerHTML = `
    <div class="tool-row"><b>Endpoint</b><span>${escapeHtml(ev.url||"—")}</span></div>
    <div class="tool-row"><b>Telemetria</b><span>${escapeHtml(ev.telemetryUrl||"—")}</span></div>
    <div class="tool-row"><b>Enviados / Falhas</b><span style="color:${(ev.failed||0)>0?"#f87171":"#34d399"}">${Number(ev.sent||0)} / ${Number(ev.failed||0)}${okRate!=null?` (${okRate}% ok)`:""}</span></div>
    <div class="tool-row"><b>Última latência</b><span>${ev.lastLatencyMs!=null?ev.lastLatencyMs+"ms":"—"} · ${fmtTs(ev.lastSentAt)}</span></div>
    <div class="tool-row"><b>Último erro</b><span style="color:${ev.lastError?"#f87171":"#94a3b8"}">${escapeHtml(ev.lastError||"nenhum")}</span></div>
    <div class="tool-row"><b>Último payload</b><span>${escapeHtml([last.home,last.away].filter(Boolean).join(" x ")||"—")} · min ${last.minute!=null?last.minute:"—"} · fx ${escapeHtml(String(last.fixtureId||"—"))} · ${last.payloadBytes!=null?last.payloadBytes+" B":"—"}</span></div>
    <div class="tool-meta" style="margin-top:8px">Histórico recente (sessão)</div>
    ${histRows}
  `;
}

async function refreshFlaskTelemetry(){
  const ev = await fetchEventosDiag();
  renderFlaskTelemetry(ev);
  return ev;
}

async function testEventosFlaskFromDiag(){
  const pill = document.getElementById("flaskTelePill");
  if(pill) pill.textContent = "TESTANDO…";
  try{
    const r = await runtime("TEST_EVENTOS_FLASK",{});
    await refreshFlaskTelemetry();
    if(r && r.ok){
      if(pill) pill.textContent = "OK";
    }else{
      if(pill) pill.textContent = "FALHA";
    }
    return r;
  }catch(e){
    if(pill) pill.textContent = "FALHA";
    await refreshFlaskTelemetry();
    return {ok:false, error: e?.message||String(e)};
  }
}


document.getElementById("refresh").onclick=()=>render();
document.getElementById("force").onclick=()=>explicitCapture();
document.getElementById("allToolsTest")?.addEventListener("click",runAllToolsFromDiagnostics);
document.getElementById("flaskTeleRefresh")?.addEventListener("click",()=>refreshFlaskTelemetry());
document.getElementById("flaskTeleTest")?.addEventListener("click",()=>testEventosFlaskFromDiag());
document.getElementById("pruneStorage")?.addEventListener("click",async()=>{
  if(!confirm("Compactar storage agora? Remove históricos pesados e limpa handoffs.")) return;
  const r=await runtime("PRUNE_STORAGE");
  alert(r?.ok?`Storage compactado. Bytes: ${r.bytes??"?"}`:`Falha: ${r?.error||"?"}`);
  await render();
});
document.getElementById("copy").onclick=async()=>{
  try{await navigator.clipboard.writeText(document.getElementById("report").textContent)}catch{}
};
document.getElementById("export").onclick=()=>{
  const blob=new Blob([document.getElementById("report").textContent],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download=`cornerai-diagnostic-${Date.now()}.json`;a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
};
document.getElementById("reset").onclick=async()=>{
  if(confirm("Limpar o estado desta partida?")){await runtime("RESET_STATE");await render();}
};

setReport({error:null,diagnosticVersion:DIAGNOSTIC_VERSION,pipeline:"inicializando..."});
renderSummary({error:null,diagnosticVersion:DIAGNOSTIC_VERSION,pipeline:"inicializando..."});
renderAllToolsAudit(null);
refreshFlaskTelemetry();
render();
