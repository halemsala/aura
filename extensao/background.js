// AURA_MAXFIX_EVENTOS_SCOPE
// EVENTOS runtime guard: keep failures explicit instead of converting them to false PASS.
function eventosRuntimeGuard(name, value) {
  if (typeof value === "undefined") {
    throw new Error(`EVENTOS_SCOPE_ERROR:${name}`);
  }
  return value;
}

try{importScripts("lib/fixture-id.js","lib/clock-parse.js","lib/pressure-dual.js","lib/corner-align.js","lib/event-clock.js","lib/ws-decode.js","lib/chunk-buffer.js","local-ai-client.js","gemini-connector.js","gemini-v10-connector.js","background-state-manager.js");}catch(e){console.warn("[CornerAI] lib importScripts",e);}// AURA_QUANT_X MAXFIX: trace every capture cycle across the pipeline.
function createCaptureCorrelationId() {
  const now = new Date();
  const stamp = now.toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  const rnd = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `CAP-${stamp}-${rnd}`;
}


const VERSION="12.8.12";

// Feed de jogos ao vivo (scan DOM + abas abertas)
let __liveFeedRegistry = new Map();
function upsertLiveFeed(items, source){
  const now=Date.now();
  for(const it of (items||[])){
    const fid=String(it.fixtureId||"").replace(/\D/g,"");
    if(!/^\d{5,}$/.test(fid)) continue;
    const prev=__liveFeedRegistry.get(fid)||{};
    __liveFeedRegistry.set(fid,{
      fixtureId:fid,
      url:it.url||prev.url||("https://sokkerpro.com/fixture/"+fid),
      label:it.label||prev.label||"",
      home:it.home||prev.home||null,
      away:it.away||prev.away||null,
      score:it.score||prev.score||null,
      minute:(it.minute!=null?it.minute:prev.minute),
      live:!!(it.live||prev.live),
      seenAt:now,
      source:source||it.source||prev.source||"scan"
    });
  }
  for(const [k,v] of [...__liveFeedRegistry.entries()]){
    if(now-(v.seenAt||0)>30*60*1000) __liveFeedRegistry.delete(k);
  }
}
function listLiveFeed(limit){
  limit=Number(limit||40)||40;
  return [...__liveFeedRegistry.values()]
    .sort((a,b)=>Number(b.live)-Number(a.live)||(b.seenAt||0)-(a.seenAt||0))
    .slice(0,limit);
}


// --- Local AI :8765 telemetry bridge ---
let __lastLocalAiPush=0;
async function pushLocalAITelemetry(reason){
  try{
    if(typeof CornerAILocalClient==="undefined"||!CornerAILocalClient.sendTelemetryToLocalAI) return;
    if(!state.fixtureId||!state.capture?.armed) return;
    const now=Date.now();
    if(now-__lastLocalAiPush<800) return;
    __lastLocalAiPush=now;
    const payload={
      schema:"cornerai-local-telemetry-1",
      reason:reason||"tick",
      fixtureId:state.fixtureId,
      home:state.home,away:state.away,
      score:state.score,minute:state.minute,extraMinute:state.extraMinute,
      liveStatus:state.liveStatus,
      stats:state.stats,
      corners:state.stats?.corners||null,
      xg:state.stats?.xg||null,
      quality:state.quality,
      intelligence:state.intelligence,
      acceptedSnapshots:Number(state.capture?.acceptedSnapshots||0),
      // v12.6.0 — Weight of Money: linha/odd asiática de escanteios para o
      // motor aplicar o Filtro Anti-Red (puramente analítico/defensivo).
      market_stats:state.wom||null,
      oddsMarkets:state.oddsMarkets||null,
      oddsHistory:Array.isArray(state.oddsHistory)?state.oddsHistory.slice(-12):[],
      events:Array.isArray(state.matchEvents)?state.matchEvents.slice(-40):[],
      h2h:state.h2h||null,
      ts:now
    };
    const r=await CornerAILocalClient.sendTelemetryToLocalAI(payload);
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.lastLocalAiPushAt=now;
    state.diagnostics.lastLocalAiOk=!!r?.ok;
    if(!r?.ok) state.diagnostics.lastLocalAiError=r?.error||"fail";
  }catch(e){
    try{state.diagnostics.lastLocalAiError=String(e?.message||e);}catch{}
  }
}


// Ao selecionar jogo: pede ao content-script varredura imediata de mercados escanteios/gols (SokkerPro / labels Bet365).
function forceMarketScanOnTabs(){
  try{
    chrome.tabs.query({url:["*://*.sokkerpro.com/*","*://sokkerpro.com/*","*://*.sokkerpro.*/*"]}, (tabs)=>{
      void chrome.runtime.lastError;
      (tabs||[]).forEach((t)=>{
        if(!t.id) return;
        try{ chrome.tabs.sendMessage(t.id,{type:"FIXTURE_SELECTED"},()=>{void chrome.runtime.lastError;}); }catch(_){}
        try{ chrome.tabs.sendMessage(t.id,{type:"FORCE_MARKET_SCAN"},()=>{void chrome.runtime.lastError;}); }catch(_){}
      });
    });
  }catch(_){}
}

const PARAMS={manualCaptureOnly:false,autoCaptureEnabled:true,diagnosticReadOnly:true,minDataConfidence:0.70,criticalDataConfidence:0.50,minOdds:1.01,maxOdds:1000,maxXGPerTeam:10,maxAttacksPerMinute:20,maxDangerousPerMinute:15,maxDuplicateWindowMs:3000,fixtureIsolation:true,autoCorrection:true,rejectInvalidRecords:true,domFallback:true,apiPriority:true,layoutDriftDetection:true,selfTestOnStartup:true,selfTestIntervalMs:30000,snapshotIntervalMs:1200,minuteHeartbeatMs:500,persistDebounceMs:250,maxMinuteSnapshots:1800,aiFeedSchema:"cornerai-ai-feed-12",analystSchema:"cornerai-analyst-1",criticalWindows:[{from:28,to:48},{from:78,to:105}],criticalDomMinMs:180,criticalHeartbeatMs:500,criticalPulseMs:200,predictiveSchema:"cornerai-predictive-3",webhookEnabled:true,webhookTimeoutMs:4000,outboxMax:200,analystMinQuality:50,analystMaxStaleMs:15000,analystMaxStaleCriticalMs:5000,aiFeedMaxEvents:5000,aiFeedMaxIndicators:2000,performancePointMax:500,historyCacheLimit:400,diagnosticHeartbeatMs:3000,adaptiveDomFallback:true,liveSnapshotHeartbeatMs:30000,alwaysVisibleWindow:true,menuCapture:true,menuMaxEntries:80,menuMaxText:120000,menuMaxTableRows:400,menuMaxOdds:1500,siteStorageScan:true,teamContextCacheLimit:80,cpiHalfLifeMin:6,cpiWeights:{dangerous:0.28,shotsOn:0.18,xg:0.16,corners:0.12,appm:0.14,possession:0.07,favorite:0.05},notificationsEnabled:true,notifyMinGapMs:45000,notifyPerKindGapMs:90000,homeAdvantageFactor:1.08,historyRetentionDays:30,idbEnabled:true};
const STAT_KEYS=["attacks","dangerous","shots","shotsOn","shotsOff","corners","xg","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed","possession"];
const EXTENDED_STAT_LIMIT=120;
const CUMULATIVE=new Set(["attacks","dangerous","shots","shotsOn","shotsOff","corners","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed"]);
const LIMITS={attacks:300,dangerous:250,shots:100,shotsOn:100,shotsOff:100,corners:60,xg:15,fouls:80,offsides:30,yellow:20,red:10,subs:15,crosses:200,saves:60,passes:2000,passesFailed:1000,possession:100};
const emptyPair=(h=null,a=null)=>({home:h,away:a});
function defaultState(){return{version:VERSION,stateVersion:0,fixtureId:null,url:"",home:"",away:"",minute:null,extraMinute:0,liveStatus:"inactive",dataMode:"unknown",captureMode:"manual",dataCompleteness:"none",score:emptyPair(),stats:Object.fromEntries(STAT_KEYS.map(k=>[k,emptyPair()])),cornerEvents:[],matchEvents:[],teamData:{home:{side:"home",name:"",stats:{},events:[],cornerMinutes:[],history:[]},away:{side:"away",name:"",stats:{},events:[],cornerMinutes:[],history:[]}},teamHistory:{home:[],away:[]},h2h:{captured:false,attempted:false,lastAttemptAt:0,rows:[],tables:[],text:"",averages:{},updatedAt:0},statTimeline:[],statChangeEvents:[],metricEvents:[],unifiedTimeline:[],eventSummary:{byTeam:{home:{team:"",counts:{}},away:{team:"",counts:{}}},total:0},cornerContexts:[],cornerIndicatorTimeline:[],oddsHistory:[],oddsChanges:[],oddsMarkets:{},marketExpectations:[],wom:{asian_corner_line:0.0,asian_corner_odds:0.0,asian_goal_line:0.0,asian_goal_odds:0.0,last_update:0},openingOdds:null,fixedFavorite:null,openingOddsLockedAt:0,historicalTextEvents:[],extendedStats:{},charts:{schema:"cornerai-charts-1",activeId:null,tabs:[],series:[],pressureBars:{},history:[],lastCaptureAt:0},menuCapture:{schema:"cornerai-menu-feed-1",current:null,menus:{},discovered:[],history:[],lastCaptureAt:0,lastHash:"",uniqueMenus:0,dataPoints:0,sweep:{active:false,tabIds:[],startedAt:0,requested:0,completed:0}},quality:{score:0,grade:"unknown",checks:[]},captureHealth:{score:0,grade:"offline",status:"aguardando",signals:{},ageMs:null,updatedAt:0},capture:{eventDedup:{},unknownStatCache:{},lastPayloadAt:0,lastChangedAt:0,lastMinuteKey:null,lastPayloadHash:null,acceptedSnapshots:0,duplicateSnapshots:0,sourcePriorityWins:0,minuteKeys:[],persistQueueDepth:0,activeTabId:null,observedMinutes:[],missingMinutes:[],lastObservedMinute:null,lastSemanticSnapshotKey:null},aiFeed:{schema:"cornerai-ai-feed-12",updatedAt:0},analyst:{schema:"cornerai-analyst-1",updatedAt:0},integrity:null,integrityHistory:[],diagTimeline:[],healthSamples:[],outbox:[],webhook:{url:"http://127.0.0.1:8080/api/cornerai/feed",lastOkAt:0,lastError:null,sent:0,failed:0,dropped:0,bridgeOffline:false,pending:0,offlineSince:0,lastRecoveryAt:0},chartData:{},xgProvenance:null,statStatus:{},provenance:{stats:{},conflicts:[],sourceCounts:{dom:0,network:0,hook:0,"dom-text":0}},intelligence:{schema:"cornerai-intelligence-1",readiness:0,confidence:0,features:{},trends:{},momentum:{home:0,away:0},anomalies:[],sourceConsensus:{score:1,conflicts:0,samples:0},derivedAt:0},sources:{dom:{lastUpdate:0,count:0},network:{lastUpdate:0,count:0},hook:{lastUpdate:0,count:0}},lastUpdate:0,snapshotCount:0,eventCount:0,cornerEventCount:0,oddsCount:0,lastSnapshotSource:null,errors:[],diagnostics:{networkRequests:0,networkResponses:0,hookMessages:0,interceptedPayloads:0,rejectedStats:0,rejectedEvents:0,duplicateEvents:0,duplicateEventDetections:0,lastEndpoint:"",lastHookAt:0,lastEventAt:0,sourceConflicts:0,staleSnapshots:0,sourceConflictsByKey:0,persistErrors:0,oddsQuotes:0,oddsChanges:0,oddsRejected:0,oddsDuplicates:0,contaminatedOdds:0,lowConfidence:0,layoutDrift:0,extendedStats:0,staleMessages:0,networkPayloadsRejected:0,oddsNoiseRejected:0,foreignFixturePayloads:0,foreignTabPayloads:0,captureDispatchFailures:0,captureDispatchRetries:0,canonicalRecovered:0,unknownStatsRecovered:0,snapshotDuplicates:0,statConflicts:0,statSourceUpgrades:0,statAnomalies:0,unknownEndpointMessages:0,invalidPerformancePoints:0,aiFeatureBuilds:0,menuSnapshots:0,menuDuplicates:0,menuDiscoveries:0,menuBytes:0,menuErrors:0,historicalSessions:0,historicalSnapshots:0,statusCorrections:0,sessionStartedAt:Date.now(),lastDiagnosticAt:0,diagnosticRuns:0,lastMessageSource:"",lastMessageAt:0,lastMessageFixture:null,lastToolTest:null}}}
let state=defaultState();
function clearRecoveredStorageCritical(){
  try{
    const bytes=Number(state.layerDiag?.storageBytes||0);
    if(bytes>0 && bytes<50*1024*1024 && state.diagnostics?.lastCritical?.code==="STORAGE_NEAR_QUOTA"){
      state.diagnostics.lastCritical=null;
    }
  }catch{}
}
const clone=v=>JSON.parse(JSON.stringify(v));
function addError(message){state.errors.unshift({time:Date.now(),message:String(message).slice(0,700)});state.errors=state.errors.slice(0,50)}
const DIAG_RING_MAX=400;

async function refreshLayerDiagnostics(){
  const out={at:Date.now(),outboxPending:Array.isArray(state.outbox)?state.outbox.length:0,
    webhookSent:Number(state.webhook?.sent||0),webhookFailed:Number(state.webhook?.failed||0),
    webhookLastError:state.webhook?.lastError||null,webhookLastOkAt:state.webhook?.lastOkAt||0,
    binaryWsDecoded:Number(state.diagnostics?.binaryWsDecoded||0),
    binaryWsUnknown:Number(state.diagnostics?.binaryWsUnknown||0),
    hookMessages:Number(state.diagnostics?.hookMessages||0),
    networkResponses:Number(state.diagnostics?.networkResponses||0),
    foreignFixture:Number(state.diagnostics?.foreignFixturePayloads||0),
    foreignTab:Number(state.diagnostics?.foreignTabPayloads||0),
    geminiFallback:!!state.diagnostics?.geminiFallback,
    geminiLastAt:state.diagnostics?.geminiLastAt||null,
    geminiLastError:state.diagnostics?.geminiLastError||null,
    idbCount:null,storageBytes:null,alarms:[]};
  try{ if(PARAMS.idbEnabled && typeof idbListMatches==="function"){ const list=await idbListMatches(500); out.idbCount=list.length; } }catch(e){ out.idbError=String(e?.message||e); }
  try{ if(chrome.storage?.local?.getBytesInUse){ out.storageBytes=await chrome.storage.local.getBytesInUse(null); } }catch{}
  try{ const al=await chrome.alarms.getAll(); out.alarms=(al||[]).map(a=>a.name); }catch{}
  state.layerDiag=out;
  clearRecoveredStorageCritical();
  return out;
}
function setupCornerAlarms(){
  try{
    chrome.alarms.create("cornerai-health",{periodInMinutes:0.5});
    chrome.alarms.create("cornerai-outbox",{periodInMinutes:1});
    chrome.alarms.create("cornerai-layer",{periodInMinutes:2});
  }catch(e){}
}
try{ chrome.alarms.onAlarm.addListener((alarm)=>{
  try{
    if(alarm.name==="cornerai-health"){ try{ if(typeof buildCaptureHealth==="function") state.captureHealth=buildCaptureHealth(); }catch{} }
    if(alarm.name==="cornerai-health"){ try{ void pushLocalAITelemetry("alarm"); }catch{} }
if(alarm.name==="cornerai-outbox"){ if(PARAMS.webhookEnabled&&typeof flushAnalystOutbox==="function") flushAnalystOutbox().catch(()=>{}); }
    if(alarm.name==="cornerai-layer"){ refreshLayerDiagnostics().catch(()=>{}); }
  }catch(e){}
}); }catch{}
try{ setupCornerAlarms(); }catch{}
try{ chrome.runtime.onStartup.addListener(()=>{ try{setupCornerAlarms();}catch{} }); }catch{}
try{ chrome.runtime.onInstalled.addListener(async (details)=>{
  try{setupCornerAlarms();}catch{}
  // Após update/install: restaura API key dos backups (não pede de novo)
  try{
    await loadGeminiConfig();
    if (__geminiCfg && __geminiCfg.apiKey) {
      console.log("[CornerAI] API key restaurada após", details.reason || "install");
    }
  }catch{}
}); }catch{}

function logSW(level,code,message,extra){
  try{
    const entry={
      id:`${Date.now().toString(36)}-${Math.random().toString(36).slice(2,7)}`,
      at:new Date().toISOString(),epoch:Date.now(),
      level:String(level||"INFO").toUpperCase(),
      layer:"sw",code:String(code||"SW"),message:String(message||"").slice(0,500),
      fixtureId:state?.fixtureId||null,version:VERSION,
      extra:extra&&typeof extra==="object"?extra:undefined
    };
    state.diagTimeline=Array.isArray(state.diagTimeline)?state.diagTimeline:[];
    state.diagTimeline.push(entry);
    if(state.diagTimeline.length>DIAG_RING_MAX) state.diagTimeline=state.diagTimeline.slice(-DIAG_RING_MAX);
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.lastDiagAt=Date.now();
    state.diagnostics.diagCount=(state.diagnostics.diagCount||0)+1;
    if(entry.level==="CRITICAL"||entry.level==="ERROR"){
      state.diagnostics.lastCritical=entry;
      try{addError(`${entry.code}: ${entry.message}`);}catch{}
    }
    try{chrome.storage.session.set({__sw_alive_at:Date.now(),__sw_log_tail:state.diagTimeline.slice(-30)});}catch{}
    return entry;
  }catch(e){try{addError("logSW:"+e.message);}catch{} return null;}
}
try{
  self.addEventListener("error",(e)=>{logSW("CRITICAL","SW_UNCAUGHT",e.message||"error",{filename:e.filename,lineno:e.lineno,colno:e.colno,stack:e.error?.stack?.slice(0,800)});});
  self.addEventListener("unhandledrejection",(e)=>{const r=e.reason;logSW("ERROR","SW_UNHANDLED_REJECTION",r?.message||String(r),{stack:r?.stack?.slice(0,800)});});
  setInterval(()=>{try{chrome.storage.session.set({__sw_alive_at:Date.now()});}catch{}},5000);
}catch{}

function finite(n){return Number.isFinite(Number(n))}
function normalizeSemanticPair(k,v){
 if(!v||typeof v!=="object")return null;
 let h=finite(v.home)?Number(v.home):null,a=finite(v.away)?Number(v.away):null;
 if(h==null&&a==null)return null;
 if(k==="xg"){
   // xG is already expressed in expected goals by the provider. Never
   // reinterpret 25 as 0.25: that can turn unrelated values into plausible xG.
   // Values outside the physical range are rejected by the merge validator.
   if(h!=null&&(h<0||h>PARAMS.maxXGPerTeam))return null;
   if(a!=null&&(a<0||a>PARAMS.maxXGPerTeam))return null;
 } else if(k==="possession"){
   // Accept decimal fractions only when both sides clearly sum to 1.
   if(h!=null&&a!=null&&h<=1.001&&a<=1.001&&Math.abs(h+a-1)<=0.02){h*=100;a*=100;}
 } else if(/_pct$|percentage|percent|accuracy|rate/.test(String(k).toLowerCase())){
   if(h!=null&&h<=1.001)h*=100;
   if(a!=null&&a<=1.001)a*=100;
 }
 return {home:h,away:a};
}
function validPair(k,v){if(!v||!finite(v.home)||!finite(v.away))return false;const h=Number(v.home),a=Number(v.away);if(h<0||a<0)return false;if(k==="xg"&&(h>PARAMS.maxXGPerTeam||a>PARAMS.maxXGPerTeam))return false; if(k!=="xg"&&LIMITS[k]!=null&&(h>LIMITS[k]||a>LIMITS[k]))return false;if(k==="possession"&&(h>100||a>100||Math.abs(h+a-100)>1.5))return false;return true}
function validScore(v){return v&&finite(v.home)&&finite(v.away)&&v.home>=0&&v.away>=0&&v.home<=30&&v.away<=30}
function teamName(v){return typeof v==="string"?v.trim():v&&typeof v==="object"?(v.name||v.title||v.shortName||v.teamName||v.label||"").toString().trim():""}
function isCleanTeamName(s){
  if(!s||typeof s!=="string") return false;
  const t=s.trim();
  if(t.length<2||t.length>45) return false;
  if(/dashboard|favoritos|competi|vis[aã]o|todos|ao vivo|pr[oó]ximos|estat[ií]sticas|replays|assine|leagues cup|concacaf|ofc|primera division|north & central|south america|minist[eé]rio|gambling|privacy|cookie|terms|gdpr|about us|contact|escanteios|cart[oõ]es|escala/i.test(t)) return false;
  if(/\d{2}:\d{2}/.test(t)) return false;
  if((t.match(/\s/g)||[]).length>5) return false;
  return true;
}
function mergeTeams(p){
  const h=teamName(p.home),a=teamName(p.away);
  if(!h||!a||h.toLowerCase()===a.toLowerCase()) return false;
  if(!isCleanTeamName(h)||!isCleanTeamName(a)) {
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.contaminatedTeams=(state.diagnostics.contaminatedTeams||0)+1;
    return false;
  }
  if(!state.home&&!state.away){state.home=h;state.away=a;return true}
  if(state.home===h&&state.away===a) return false;
  // Se já temos nomes limpos, não sobrescreve com lixo
  if(isCleanTeamName(state.home)&&isCleanTeamName(state.away)) {
    state.diagnostics.sourceConflicts++;
    return false;
  }
  state.home=h; state.away=a;
  return true;
}
function normalizeClock(v, fallbackExtra=0){
 if(v==null)return null;
 if(typeof v==="string"){const m=v.trim().match(/^(\d{1,3})(?:\+(\d{1,2}))?$/);if(m){const minute=Number(m[1]),extra=Number(m[2]||fallbackExtra);if(Number.isFinite(minute)&&minute>=0&&minute<=130)return{minute:Math.floor(minute),extraMinute:Math.max(0,extra)}}}
 const n=Number(v);if(!Number.isFinite(n)||n<0||n>130)return null;return{minute:Math.floor(n),extraMinute:Math.max(0,Number(fallbackExtra)||0)}
}
function normalizeMinute(v){const c=normalizeClock(v);return c?c.minute:null}
function normalizePeriod(v,minute,extra=0){const s=String(v??"").toLowerCase();if(/2|second|segundo/.test(s))return 2;if(/1|first|primeiro/.test(s))return 1;return minute>=46?2:1}
function normalizeMatchEvent(e,source){
 if(!e||typeof e!=="object")return null;
 const typeRaw=String(e.type??e.eventType??e.kind??e.incidentType??e.event_name??e.event??"").toLowerCase().trim();
 const label=String(e.label??e.description??e.name??e.text??"").replace(/\s+/g," ").trim();
 const blob=(typeRaw+" "+label).toLowerCase();
 const map=[
  ["corner",/corner|escante|canto/],
  // Semantic priority: "Chute no Gol/Alvo" is a shot on target, never a goal.
  ["shot_on",/(?:shot|chute|finaliza[cç][aã]o)[^\n]{0,24}(?:on|no|a|ao)?\s*(?:target|gol|alvo)|(?:on|no)\s+(?:target|gol|alvo)/],
  ["goal",/\b(?:goal|gol)\b|\b\d{1,2}\s*[-x]\s*\d{1,2}\b/],
  ["yellow",/yellow|amarelo|cart[aã]o amarelo/],
  ["red",/red card|cart[aã]o vermelho|vermelho/],
  ["substitution",/substitut|substitui[cç][aã]o|entra|sai/],
  ["shot_off",/shot off target|off target|finaliza[cç][aã]o.*fora|chute.*fora|ao lado/],
  ["foul",/foul|falta/],["offsides",/offside|impedimento/]
 ];
 const match=map.find(([,rx])=>rx.test(blob)); if(!match)return null;
 const minute=normalizeMinute(e.minute??e.min??e.elapsed??e.elapsedMinute??e.matchMinute); if(minute==null)return null;
 const extra=Math.max(0,Number(e.extraMinute??e.stoppage??e.addedTime??0)||0);
 let side=String(e.side??e.teamSide??e.teamSideId??"").toLowerCase().trim();
 if(/^(casa|home|mandante)$/.test(side))side="home"; else if(/^(away|visitante|fora)$/.test(side))side="away";
 const team=teamName(e.teamName??e.teamObject??e.team??e.teamData);
 if(side!=="home"&&side!=="away"&&team){if(state.home&&team.toLowerCase()===state.home.toLowerCase())side="home";else if(state.away&&team.toLowerCase()===state.away.toLowerCase())side="away"}
 if(side!=="home"&&side!=="away")return null;
 const period=normalizePeriod(e.period??e.half??e.stage,minute,extra);
 const rawId=e.eventId??e.event_id??e.uid??e.id??null;
 const type=match[0];
 const playerName=String(e.playerName||e.player||e.athlete||e.scorer||"").replace(/\s+/g," ").trim().slice(0,80)||null;
 const playerId=e.playerId||e.player_id||(playerName?`name:${playerName.toLowerCase()}`:null);
 const labelHash=String(label||"").toLowerCase().replace(/[^a-z0-9]+/g,"").slice(0,24)||"x";
 const playerHash=String(playerId||playerName||"").toLowerCase().replace(/[^a-z0-9:_-]+/g,"").slice(0,40)||"x";
 const fid=String(state.fixtureId||e.fixtureId||"unknown");
 // Canonical identity: fixture + event semantics + actor when available.
 // This prevents false deduplication of same-minute events from the same side.
 const signature=`${fid}|${type}|${period}|${minute}|${extra}|${side}|${labelHash}|${playerHash}`;
 const eventId=rawId?`${fid}|raw|${String(rawId).slice(0,48)}` : signature;
 return {
   eventId:String(eventId),
   signature,
   fixtureId:fid,
   minute,extraMinute:extra,period,
   team:team||(side==="home"?state.home:state.away),
   side,type,
   label:label.slice(0,180),
   playerName,playerId,
   source,
   confidence:Math.min(1,Math.max(0,Number(e.confidence)||sourceBaseConfidence(source))),
   timestamp:Number(e.timestamp)||Date.now()
 };
}
function normalizeEvent(e,source){
 if(!e||typeof e!=="object")return null;
 const type=String(e.type||e.eventType||e.kind||e.incidentType||"").toLowerCase().trim();
 if(!/^(corner|escanteio|escanteios|canto|cantos)$/.test(type)&&!/corner|escante/.test(type))return null;
 const minute=normalizeMinute(e.minute??e.min??e.elapsed??e.elapsedMinute??e.matchMinute); if(minute==null)return null;
 const extra=Math.max(0,Number(e.extraMinute??e.stoppage??e.addedTime??0)||0);
 let side=String(e.side??e.teamSide??e.teamSideId??"").toLowerCase().trim();
 if(/^(casa|home|mandante)$/.test(side))side="home"; else if(/^(away|visitante|fora)$/.test(side))side="away";
 const team=teamName(e.teamName??e.teamObject??e.team??e.teamData);
 if(side!=="home"&&side!=="away"&&team){if(state.home&&team.toLowerCase()===state.home.toLowerCase())side="home";else if(state.away&&team.toLowerCase()===state.away.toLowerCase())side="away"}
 if(side!=="home"&&side!=="away")return null;
 const period=normalizePeriod(e.period??e.half??e.stage,minute,extra);
 const rawId=e.eventId??e.event_id??e.id??e.uid??null;
 const text=String(e.label??e.description??e.name??"").replace(/\s+/g," ").trim().slice(0,160);
 const signature=`${state.fixtureId||e.fixtureId||"unknown"}|corner|${period}|${minute}|${extra}|${side}|${text}`;
 const id=String(rawId||signature);
 return{eventId:id,signature,fixtureId:e.fixtureId?String(e.fixtureId):state.fixtureId,minute,extraMinute:extra,period,team:team||(side==="home"?state.home:state.away),side,type:"corner",source,confidence:Math.min(1,Math.max(0,Number(e.confidence)||0.8)),timestamp:Number(e.timestamp)||Date.now()}
}
function rebuildTeamData(){
 const make=(side,name)=>({side,name:name||"",stats:{},events:[],cornerMinutes:[],history:[]});
 const td={home:make("home",state.home),away:make("away",state.away)};
 const history=state.teamHistory||{home:[],away:[]};
 td.home.history=clone(history.home||[]); td.away.history=clone(history.away||[]);
 // Never convert an unavailable metric (null) into a fake zero.
 // Some metrics are not exposed by the source and must remain explicitly unavailable.
 for(const k of STAT_KEYS){
   td.home.stats[k]=state.stats?.[k]?.home==null?null:Number(state.stats[k].home);
   td.away.stats[k]=state.stats?.[k]?.away==null?null:Number(state.stats[k].away);
 }
 // Event-backed metrics can be reconstructed safely when the provider omits the
 // aggregate stat. This fixes false 0 values for cards, offsides and substitutions.
 const eventDerived={offsides:"offsides",yellow:"yellow",red:"red",subs:"substitution"};
 for(const [metric,type] of Object.entries(eventDerived)){
   for(const side of ["home","away"]){
     if(td[side].stats[metric]==null){
       td[side].stats[metric]=(state.matchEvents||[]).filter(e=>e.side===side&&e.type===type).length;
     }
   }
 }
 for(const e of state.cornerEvents){
   const side=e.side==="away"?"away":"home";
   td[side].events.push(clone(e));
   td[side].cornerMinutes.push({minute:e.minute,extraMinute:e.extraMinute||0,period:e.period});
 }
 td.home.events.sort(eventOrder); td.away.events.sort(eventOrder);
 td.home.cornerMinutes.sort(minuteOrder); td.away.cornerMinutes.sort(minuteOrder);
 state.teamData=td;
 rebuildChartData();
 rebuildUnifiedTimeline();
}
function eventOrder(a,b){return (a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||((a.timestamp||0)-(b.timestamp||0))}
function minuteOrder(a,b){return (a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))}
function rebuildChartData(){
 const events=(state.cornerEvents||[]).slice().sort(eventOrder);
 let ht=0,at=0;
 const cornerTimeline=events.map((e,i)=>{if(e.side==='home')ht++;else at++;return {index:i+1,fixtureId:e.fixtureId,period:e.period,minute:e.minute,extraMinute:e.extraMinute||0,team:e.team||'',side:e.side,type:e.type,source:e.source,confidence:e.confidence,homeTotal:ht,awayTotal:at}});
 const metrics=STAT_KEYS.map(k=>({key:k,home:state.stats?.[k]?.home??null,away:state.stats?.[k]?.away??null}));
 const history=Array.isArray(state.statTimeline)?state.statTimeline.slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||((a.timestamp||0)-(b.timestamp||0))):[];
 const series={}; for(const k of STAT_KEYS){series[k]={home:history.map(p=>({minute:p.minute,extraMinute:p.extraMinute||0,period:p.period,value:p.stats?.[k]?.home??null})),away:history.map(p=>({minute:p.minute,extraMinute:p.extraMinute||0,period:p.period,value:p.stats?.[k]?.away??null}))}};
 const windows=[{key:'0-15',from:0,to:15,period:1},{key:'16-30',from:16,to:30,period:1},{key:'31-45+',from:31,to:45,period:1},{key:'46-60',from:46,to:60,period:2},{key:'61-75',from:61,to:75,period:2},{key:'76-90+',from:76,to:130,period:2}];
 const byWindow=Object.fromEntries(windows.map(w=>[w.key,{home:Object.fromEntries(STAT_KEYS.map(k=>[k,0])),away:Object.fromEntries(STAT_KEYS.map(k=>[k,0])),cornerEvents:{home:[],away:[]}}]));
 for(const e of events){const w=windows.find(x=>x.period===e.period&&e.minute>=x.from&&e.minute<=x.to);if(w){byWindow[w.key][e.side].corners++;byWindow[w.key].cornerEvents[e.side].push({minute:e.minute,extraMinute:e.extraMinute||0})}}
 const teamEventTimeline=events.map((e,i)=>({...e,index:i+1}));
 state.chartData={metrics,cornersByTeam:{home:{team:state.home,minutes:state.teamData?.home?.cornerMinutes||[],total:state.stats?.corners?.home??0},away:{team:state.away,minutes:state.teamData?.away?.cornerMinutes||[],total:state.stats?.corners?.away??0}},cornerTimeline,teamEventTimeline,periods:{firstHalf:{home:events.filter(e=>e.period===1&&e.side==='home').length,away:events.filter(e=>e.period===1&&e.side==='away').length},secondHalf:{home:events.filter(e=>e.period===2&&e.side==='home').length,away:events.filter(e=>e.period===2&&e.side==='away').length}},teamSeries:series,statTimeline:history,metricEvents:state.metricEvents||[],windows:byWindow,teamSnapshots:compactTimeline(),cornerIndicatorTimeline:state.cornerIndicatorTimeline||[]};
}
function metricDeltaEvents(prev,p,nextSource){
 const out=[]; for(const k of STAT_KEYS){
   const ph=prev?.stats?.[k]?.home, pa=prev?.stats?.[k]?.away;
   const h=p?.stats?.[k]?.home, a=p?.stats?.[k]?.away;
   if(Number.isFinite(Number(ph))&&Number.isFinite(Number(h))){const dh=Number(h)-Number(ph);if(dh>0)out.push({eventId:`${p.fixtureId}|metric|${p.period}|${p.minute}|${p.extraMinute||0}|home|${k}|${h}`,fixtureId:p.fixtureId,period:p.period,minute:p.minute,extraMinute:p.extraMinute||0,side:'home',team:state.home,metric:k,from:Number(ph),to:Number(h),delta:dh,source:nextSource,timestamp:p.timestamp})}
   if(Number.isFinite(Number(pa))&&Number.isFinite(Number(a))){const da=Number(a)-Number(pa);if(da>0)out.push({eventId:`${p.fixtureId}|metric|${p.period}|${p.minute}|${p.extraMinute||0}|away|${k}|${a}`,fixtureId:p.fixtureId,period:p.period,minute:p.minute,extraMinute:p.extraMinute||0,side:'away',team:state.away,metric:k,from:Number(pa),to:Number(a),delta:da,source:nextSource,timestamp:p.timestamp})}
 }
 return out;
}
function rebuildMetricEvents(){
 const arr=(state.statTimeline||[]).slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||((a.timestamp||0)-(b.timestamp||0)));
 let prev=null; const out=[];
 for(const p of arr){out.push(...metricDeltaEvents(prev,p,p.source));prev=p}
 const seen=new Set(); state.metricEvents=out.filter(e=>!seen.has(e.eventId)&&seen.add(e.eventId)).slice(-8000);
}
function rebuildQuality(){
 const checks=[];const add=(key,ok,weight=1,detail="")=>checks.push({key,ok:!!ok,weight,detail});
 const isFinished=state.liveStatus==="finished",isHistorical=isFinished||state.dataMode==="historical";
 add("teams",!!(state.home&&state.away),2);add("fixture",!!state.fixtureId,2);
 const arr=(state.statTimeline||[]).slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0)));
 const unique=[...new Set(arr.map(p=>`${p.period}|${p.minute}|${p.extraMinute||0}`))];
 add("timeline",arr.length>0,2,`${arr.length} snapshots`);add("teamSplit",!!(state.teamData?.home?.name&&state.teamData?.away?.name),2);
 add("cornersSplit",!!(state.teamData?.home?.cornerMinutes&&state.teamData?.away?.cornerMinutes),2);
 add("chronology",(state.cornerEvents||[]).every((e,i,a)=>i===0||eventOrder(a[i-1],e)<=0),2);
 add("noCrossFixture",[...(state.cornerEvents||[]),...(state.matchEvents||[]),...(state.oddsHistory||[])].every(e=>!e.fixtureId||!state.fixtureId||String(e.fixtureId)===String(state.fixtureId)),4);
 add("source",!!state.lastSnapshotSource,1);
 const sourceCount=Object.values(state.sources||{}).filter(s=>Number(s?.count||0)>0).length;
 add("sourceDiversity",isFinished||sourceCount>=1,1,`${sourceCount} fonte(s) com dados`);
 add("hookNetworkSignal",isHistorical||Number(state.diagnostics.hookMessages||0)>0||Number(state.diagnostics.networkRequests||0)>0||Number(state.diagnostics.networkResponses||0)>0,2,isHistorical?"modo histórico — hook/network opcional":"hook/network sem sinal durante partida ao vivo");
 const meaningful=state.matchEvents.length>0||state.cornerEvents.length>0||arr.length>0||state.oddsHistory.length>0;add("meaningfulData",meaningful,2);
 add("statusKnown",!['unknown','inactive'].includes(state.liveStatus),1);
 add("oddsIntegrity",Number(state.diagnostics.contaminatedOdds||0)===0,2,`${state.diagnostics.contaminatedOdds||0} odds contaminadas`);
 add("confidenceGate",Number(state.diagnostics.lowConfidence||0)===0,2);
 let gaps=0,missing=[];if(state.liveStatus==='live'&&unique.length){for(let i=1;i<arr.length;i++){const a=arr[i-1],b=arr[i];if(a.period!==b.period)continue;for(let m=a.minute+1;m<b.minute;m++){gaps++;missing.push(`${b.period}|${m}|0`)}}}
 const latest=arr[arr.length-1];add("minuteContinuity",isFinished||gaps===0,4,gaps?`${gaps} minuto(s) sem snapshot observado`:"sem lacunas observadas");
 const expected=isHistorical?Math.max(1,Math.min(90,Number(latest?.minute||state.minute||90))):Math.max(1,Number(state.minute||0)-1);const coverage=isHistorical?Math.min(1,Math.max(unique.length?unique.length/Math.max(1,expected):0, meaningful?0.5:0)):Math.min(1,unique.length/expected);
 add("minuteCoverage",isHistorical?meaningful:coverage>=0.85,4,isHistorical?`${unique.length} snapshot(s) finais + ${Number(state.matchEvents?.length||0)} evento(s) históricos`:`${unique.length}/${expected||unique.length} minutos observados`);
 const canonical=STAT_KEYS.filter(k=>state.stats?.[k]?.home!=null&&state.stats?.[k]?.away!=null).length;
 const extras=Object.keys(state.extendedStats||{}).filter(k=>!/^\d+$/.test(k)).length;
 const eventCount=Number(state.matchEvents?.length||0), cornerCount=Number(state.cornerEvents?.length||0);
 const completeness=canonical>=STAT_KEYS.length ? "complete" : (canonical>=Math.ceil(STAT_KEYS.length*0.7) || eventCount>=10 ? "partial" : "minimal");
 state.dataCompleteness=completeness;
 const missingCanonical=STAT_KEYS.filter(k=>state.stats?.[k]?.home==null||state.stats?.[k]?.away==null); add("canonicalStats",canonical>=Math.min(12,STAT_KEYS.length),3,`${canonical}/${STAT_KEYS.length} parâmetros canônicos; ausentes: ${missingCanonical.length?missingCanonical.join(", "):"nenhum"}`);
 add("extendedStats",extras>=1,2,`${extras} parâmetros adicionais`);
 add("historicalEvidence",!isHistorical || (arr.length>0 && (eventCount>0 || canonical>=10)),3,isHistorical?`${eventCount} eventos, ${canonical}/${STAT_KEYS.length} canônicos`:"modo ao vivo");
 const rejects=Number(state.diagnostics.rejectedStats||0)+Number(state.diagnostics.rejectedEvents||0);add("lowRejections",rejects===0,2,`${rejects} rejeições`);
 const weighted=checks.reduce((a,c)=>a+c.weight,0),passed=checks.reduce((a,c)=>a+(c.ok?c.weight:0),0),score=Math.round(passed/Math.max(1,weighted)*100),grade=score>=95?"excellent":score>=85?"good":score>=70?"warning":"poor";
 state.capture.observedMinutes=unique.map(k=>k);state.capture.missingMinutes=missing;state.capture.lastObservedMinute=latest?.minute??null;
 state.quality={score,grade,checks,parameters:PARAMS,history:{snapshots:arr.length,uniqueMinutes:unique.length,gaps,rejected:rejects,latestMinute:latest?.minute??null,coverage,canonicalStats:canonical,extendedStats:extras,events:eventCount,corners:cornerCount,dataCompleteness:completeness}};
}

function buildCaptureHealth(){
 const now=Date.now(), d=state.diagnostics||{}, c=state.capture||{}, q=state.quality||{};
 const age=c.lastPayloadAt?Math.max(0,now-Number(c.lastPayloadAt)):null;
 const isFinished=state.liveStatus==="finished" || state.dataMode==="historical";
 // Finished matches legitimately stop updating — do not treat them as stale/degraded
 const staleLimit=isFinished?120000:10000;
 const deadLimit=isFinished?600000:30000;
 const stale=!isFinished && (age==null || age>staleLimit);
 const dead=!isFinished && (age==null || age>deadLimit);
 const tab=!!c.activeTabId;
 const fixture=!!state.fixtureId;
 const teams=!!(state.home&&state.away);
 const snapshot=Number(state.snapshotCount||0)>0 || Number(c.acceptedSnapshots||0)>0 || Number(state.statTimeline?.length||0)>0;
 const recentSnapshot=isFinished ? snapshot : (age!=null&&age<=12000);
 const content=tab && (isFinished || !dead);
 const hook=Number(d.lastHookAt||0)>0 && (isFinished || now-Number(d.lastHookAt||0)<30000);
 const chartUrls=Array.isArray(state.charts?.networkUrls)?state.charts.networkUrls:[];
 const lastEp=String(d.lastEndpoint||"");
 const urlHint=[...chartUrls,lastEp].some(u=>/m[24]\.sokkerpro\.com|\/x7\b|\/grafic|wss:\/\//i.test(String(u||"")));
 const network=Number(d.networkResponses||0)>0 || Number(d.networkRequests||0)>0 || urlHint;
 const foreignTab=Number(d.foreignTabPayloads||0)>0;
 const foreignFixture=Number(d.foreignFixturePayloads||0)>0;
 const foreignTabRelevant=foreignTab && !c.activeTabId;
 const sessionSafe=!foreignTabRelevant && !foreignFixture && Number(d.staleMessages||0)===0;
 const rejected=Number(d.rejectedStats||0)+Number(d.rejectedEvents||0)+Number(d.networkPayloadsRejected||0);
 const dispatchFailures=Number(d.captureDispatchFailures||0);
 const dispatchRetries=Number(d.captureDispatchRetries||0);
 const persist=Number(d.persistErrors||0)===0;
 const menuData=Number(state.menuCapture?.dataPoints||0)>0||Number(state.menuCapture?.uniqueMenus||0)>0||Object.keys(state.menuCapture?.menus||{}).length>0;
 const menu=menuData || Number(d.menuErrors||0)===0;
 const conflict=Number(d.statConflicts||0)===0 && Number(d.sourceConflicts||0)===0;
 const semantic=Number(state.statTimeline?.length||0)>0 || Number(state.matchEvents?.length||0)>0 || Number(state.cornerEvents?.length||0)>0;
 const signals={
   contentScript:{ok:content,label:content?'OK':'SEM CONEXÃO'},
   fixture:{ok:fixture,label:fixture?String(state.fixtureId):'NÃO IDENTIFICADO'},
   teams:{ok:teams,label:teams?'OK':'PENDENTE'},
   snapshot:{ok:recentSnapshot,label:isFinished?(snapshot?'HISTÓRICO':'NENHUM'):(recentSnapshot?'RECENTE':snapshot?'DESATUALIZADO':'NENHUM')},
   hook:{ok:hook||isFinished,label:isFinished?'FINAL':(hook?'ATIVO':network?'SEM SINAL RECENTE':'INATIVO')},
   network:{ok:network||isFinished,label:isFinished?'FINAL':(network?'SINAL':'SEM SINAL')},
   session:{ok:sessionSafe,label:sessionSafe?'ISOLADA':'ATENÇÃO'},
   integrity:{ok:rejected===0&&conflict,label:(rejected===0&&conflict)?'OK':'CONFLITO'},
   persistence:{ok:persist,label:persist?'OK':'ERRO'},
   menus:{ok:menu,label:menu?'OK':'ERRO'},
   semantic:{ok:semantic,label:semantic?'DADOS REAIS':'SEM DADOS'}
 };
 const weights={contentScript:14,fixture:8,teams:6,snapshot:22,hook:8,network:5,session:12,integrity:10,persistence:5,menus:3,semantic:7};
 let score=0,total=Object.values(weights).reduce((a,b)=>a+b,0);for(const [k,w] of Object.entries(weights))if(signals[k].ok)score+=w;
 if(stale && snapshot) score=Math.max(0,score-12);
 if(dead) score=Math.min(score,25);
 if(dispatchFailures>0) score=Math.max(0,score-Math.min(15,dispatchFailures*3));
 score=Math.round(score/total*100);
 const grade=score>=95?'excellent':score>=85?'good':score>=70?'watch':score>=45?'degraded':'critical';
 const status=isFinished?'finalizada':dead?'interrompida':stale?'degradada':score>=85?'saudável':'atenção';
 return {score,grade,status,ageMs:age,stale,dead,finished:isFinished,signals,metrics:{snapshots:Number(state.statTimeline?.length||0),accepted:Number(c.acceptedSnapshots||0),duplicates:Number(c.duplicateSnapshots||0),dispatchFailures,dispatchRetries,rejected,conflicts:Number(d.statConflicts||0),persistErrors:Number(d.persistErrors||0),lastPayloadAt:Number(c.lastPayloadAt||0),lastUpdate:Number(state.lastUpdate||0)},updatedAt:now};
}

function buildSessionHealth(){const d=state.diagnostics||{},i=state.intelligence||{},q=state.quality||{};const sourceCount=Object.values(state.provenance?.sourceCounts||{}).reduce((n,v)=>n+Number(v||0),0);const conflicts=Number(d.statConflicts||0);const rejected=Number(d.rejectedStats||0)+Number(d.rejectedEvents||0);const dup=Number(d.duplicateEvents||0);const accepted=Number(state.eventCount||0);const duplicateRate=dup/(dup+accepted||1);const integrityPenalty=Math.min(100,conflicts*3+rejected*2);const sourceHealth=Math.min(100,sourceCount?60+Math.min(40,sourceCount):0);const score=Math.max(0,Math.min(100,Math.round(Number(q.score||0)*.50+Number(i.readiness||0)*.35+sourceHealth*.10+Math.max(0,100-integrityPenalty)*.05)));return{score,grade:score>=90?'excellent':score>=75?'good':score>=60?'watch':'poor',duplicateRate:Number(duplicateRate.toFixed(4)),conflicts,rejected,sourceCount,aiReadiness:Number(i.readiness||0),quality:Number(q.score||0),updatedAt:Date.now()}}

function buildAIFeed(){const timeline=(state.statTimeline||[]).slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0)));const minutes=timeline.map(p=>({t:[p.minute,p.extraMinute||0,p.period],score:[p.score?.home??null,p.score?.away??null],v:Object.fromEntries(STAT_KEYS.map(k=>[k,[p.stats?.[k]?.home??null,p.stats?.[k]?.away??null]])),extended:p.extendedStats||{},src:p.source||null,ts:p.timestamp||0,isSnapshot:p.isSnapshot!==false,isDerived:!!p.isDerived,observedAt:p.observedAt||p.timestamp||0,schemaVersion:p.schemaVersion||VERSION}));const indicators=(state.cornerIndicatorTimeline||[]).slice(-PARAMS.aiFeedMaxIndicators).map(p=>({t:[p.minute,p.extraMinute||0,p.period],v:{attacks:[p.attacks?.home??null,p.attacks?.away??null],dangerous:[p.dangerous?.home??null,p.dangerous?.away??null],shotsOn:[p.shotsOn?.home??null,p.shotsOn?.away??null],shotsOff:[p.shotsOff?.home??null,p.shotsOff?.away??null],xg:[p.xg?.home??null,p.xg?.away??null],possession:[p.possession?.home??null,p.possession?.away??null]},appm:p.appm||{},pressure:p.pressure||{},performancePoints:Array.isArray(p.performancePoints)?p.performancePoints.slice(0,PARAMS.performancePointMax):[],src:p.source||null,ts:p.timestamp||0}));const events=(state.matchEvents||[]).slice(-PARAMS.aiFeedMaxEvents).map(e=>[e.period,e.minute,e.extraMinute||0,e.side,e.type,e.team||null,e.source||null,Number(e.confidence||0)]),corners=(state.cornerEvents||[]).slice(-PARAMS.aiFeedMaxEvents).map(e=>[e.period,e.minute,e.extraMinute||0,e.side,e.team||null,e.source||null,Number(e.confidence||0)]);return{schema:PARAMS.aiFeedSchema,version:VERSION,updatedAt:Date.now(),sessionHealth:buildSessionHealth(),captureHealth:buildCaptureHealth(),fixture:{id:state.fixtureId,home:state.home,away:state.away,status:state.liveStatus,dataMode:state.dataMode,captureMode:state.captureMode,clock:[state.minute,state.extraMinute||0],score:[state.score?.home??null,state.score?.away??null]},stats:{keys:STAT_KEYS,xgProvenance:state.xgProvenance||null,latest:Object.fromEntries(STAT_KEYS.map(k=>[k,[state.stats?.[k]?.home??null,state.stats?.[k]?.away??null]])),extended:state.extendedStats||{},catalog:Object.fromEntries(Object.entries(state.extendedStats||{}).filter(([k])=>!/^\d+$/.test(k)).map(([k,v])=>[k,{label:v.label,home:v.home,away:v.away,source:v.source}]))},minutes,indicators,events,corners,oddsCount:state.oddsHistory.length,temporal:{
 snapshotMinutes:minutes.map(x=>`${x.t[0]}${x.t[1]?`+${x.t[1]}`:""}@${x.t[2]}`),
 indicatorPoints:indicators.length,
 observedMinutes:state.capture?.observedMinutes||[],
 missingMinutes:state.capture?.missingMinutes||[]
},quality:{score:state.quality?.score??0,grade:state.quality?.grade??"unknown",historyDepth:timeline.length,rejected:(Number(state.diagnostics.rejectedStats||0)+Number(state.diagnostics.rejectedEvents||0))},capture:{source:state.lastSnapshotSource,accepted:state.capture?.acceptedSnapshots||0,duplicates:state.capture?.duplicateSnapshots||0,minuteKeys:state.capture?.minuteKeys?.length||0,observedMinutes:state.capture?.observedMinutes||[],missingMinutes:state.capture?.missingMinutes||[],activeTabId:state.capture?.activeTabId||null,foreignTabPayloads:state.diagnostics?.foreignTabPayloads||0,foreignFixturePayloads:state.diagnostics?.foreignFixturePayloads||0},intelligence:state.intelligence||null,
momentum:state.intelligence?.momentum||{home:0,away:0},
odds:{
  count:Number(state.oddsHistory?.length||0),
  changes:Number(state.oddsChanges?.length||0),
  markets:Object.keys(state.oddsMarkets||{}).length,
  latestCorners:(state.marketExpectations||[]).slice(-20),
  recent:(state.oddsHistory||[]).slice(-40).map(r=>({t:[r.minute,r.extraMinute||0,r.period],market:r.market,marketType:r.marketType,selection:r.selection,line:r.line,odds:r.odds,fair:r.fairProbability??null,src:r.source||null,ts:r.timestamp||0}))
},
provenance:state.provenance||null,menus:{schema:"cornerai-menu-feed-1",current:state.menuCapture?.current?{menuId:state.menuCapture.current.menuId,menuLabel:state.menuCapture.current.menuLabel,url:state.menuCapture.current.url,title:state.menuCapture.current.title,text:String(state.menuCapture.current.text||"").slice(0,20000),headings:(state.menuCapture.current.headings||[]).slice(0,100),tables:(state.menuCapture.current.tables||[]).slice(0,20),charts:(state.menuCapture.current.charts||[]).slice(0,30),odds:(state.menuCapture.current.odds||[]).slice(0,500)}:null,discovered:(state.menuCapture?.discovered||[]).slice(0,200),uniqueMenus:Number(state.menuCapture?.uniqueMenus||0),recent:(state.menuCapture?.history||[]).slice(-100)},
charts:(()=>{
  const ch=state.charts||{};
  const clock=Number(state.minute);
  const hasClock=Number.isFinite(clock)&&clock>=0;
  const rawBars=ch.pressureBars&&typeof ch.pressureBars==="object"?ch.pressureBars:{};
  const pressureBars={};
  for(const [k,v] of Object.entries(rawBars)){
    if(!v||v.empty) continue;
    const m=String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
    if(!m) continue;
    const start=Number(m[1]);
    if(hasClock&&start>clock) continue;
    let h=Number(v.home),a=Number(v.away),pct=Number(v.pct);
    if(Number.isFinite(pct)&&pct>=0&&pct<=100){
      h=pct; a=Number((100-pct).toFixed(1));
    } else if(Number.isFinite(h)&&Number.isFinite(a)&&h>0&&a>0&&(h>100||a>100||(h<=1.5&&a<=1.5))){
      const ssum=h+a; h=Number(((h/ssum)*100).toFixed(1)); a=Number(((a/ssum)*100).toFixed(1));
    }
    if(!Number.isFinite(h)||!Number.isFinite(a)) continue;
    if(h===0&&a===0) continue;
    if((h===0&&a>0)||(a===0&&h>0)) continue;
    pressureBars[m[1]+"-"+m[2]]={home:h,away:a,pct:Number.isFinite(pct)?pct:null};
  }
  // Pressão minuto a minuto a partir dos indicadores
  const pressureByMinute=(state.cornerIndicatorTimeline||[]).slice(-PARAMS.aiFeedMaxIndicators).map(p=>{
    const pr=p.pressure&&typeof p.pressure==="object"?p.pressure:{};
    const intervals={};
    for(const [ik,iv] of Object.entries(pr)){
      if(!/^\d{1,2}-\d{1,2}$/.test(ik)||!iv) continue;
      const im=ik.match(/(\d{1,2})-(\d{1,2})/);
      if(im&&hasClock&&Number(im[1])>clock) continue;
      const hh=Number(iv.home),aa=Number(iv.away);
      if(!Number.isFinite(hh)||!Number.isFinite(aa)||(hh===0&&aa===0)) continue;
      intervals[ik]={home:hh,away:aa};
    }
    return {t:[p.minute,p.extraMinute||0,p.period],intervals,src:p.source||null,ts:p.timestamp||0};
  }).filter(x=>Object.keys(x.intervals).length>0);
  return {
    schema:"cornerai-charts-1",
    activeId:ch.activeId||null,
    tabs:Array.isArray(ch.tabs)?ch.tabs.slice(0,20):[],
    series:Array.isArray(ch.series)?ch.series.slice(0,40):[],
    pressureBars,
    pressureByMinute,
    history:Array.isArray(ch.history)?ch.history.slice(-30):[],
    lastCaptureAt:Number(ch.lastCaptureAt||0)
  };
})(),
context:{
  h2h:{
    captured:!!state.h2h?.captured,
    averages:state.h2h?.averages||{},
    matches:Array.isArray(state.h2h?.matches)?state.h2h.matches.length:(Array.isArray(state.h2h?.rows)?state.h2h.rows.length:0),
    updatedAt:state.h2h?.updatedAt||0
  },
  teamCache:state.teamContextCache||null,
  attackFactors:{
    home:(typeof computeTeamAttackFactor==="function")?computeTeamAttackFactor("home"):null,
    away:(typeof computeTeamAttackFactor==="function")?computeTeamAttackFactor("away"):null
  },
  formFactors:{
    home:(typeof computeTeamFormFactor==="function")?computeTeamFormFactor("home"):null,
    away:(typeof computeTeamFormFactor==="function")?computeTeamFormFactor("away"):null,
    homeSeries:(state.teamContextCache?.home?.formCorners||[]).slice(-8),
    awaySeries:(state.teamContextCache?.away?.formCorners||[]).slice(-8)
  },
  h2hEnrichment:state.h2h?.averages?{
    corners:state.h2h.averages.corners||null,
    cornersTotal:state.h2h.averages.cornersTotal||null,
    cornersHome:state.h2h.averages.cornersHome||null,
    cornersAway:state.h2h.averages.cornersAway||null,
    variance:state.h2h.averages.cornersTotal?.variance??state.h2h.averages.corners?.variance??null,
    std:state.h2h.averages.cornersTotal?.std??state.h2h.averages.corners?.std??null,
    cornersResultCorr:state.h2h.averages.cornersResultCorr??null,
    drawRate:state.h2h.averages.drawRate??null,
    lowCornerDrawBias:!!state.h2h.averages.lowCornerDrawBias
  }:null,
  calibration:buildCalibrationContext(),
  precision:(typeof buildPrecisionReport==="function")?buildPrecisionReport():null,
  predictive:(typeof buildAdvancedPredictiveFeatures==="function")?buildAdvancedPredictiveFeatures():null,
  explain:(typeof buildExplainabilityBundle==="function")?buildExplainabilityBundle():null,
  drift:state.drift||null,
  feedback:state.feedback?.stats||null,
  temporal:state.temporal?{
    windows:state.temporal.windows,
    peaks:(state.temporal.peaks||[]).slice(-6),
    sequences:(state.temporal.sequences||[]).slice(-8),
    fatigue:state.temporal.fatigue,
    businessRules:state.temporal.businessRules,
    ratesPerMinute:state.temporal.ratesPerMinute
  }:null,
  openingOdds:state.openingOdds||null,
  fixedFavorite:state.fixedFavorite||null,
  diagnostics:{
    historicalBootstrap:Number(state.diagnostics?.historicalBootstrap||0),
    siteStorageScans:Number(state.diagnostics?.siteStorageScans||0),
    siteStorageKeysFound:Number(state.diagnostics?.siteStorageKeysFound||0),
    binaryWsDecoded:Number(state.diagnostics?.binaryWsDecoded||0),
    menuAutoSweeps:Number(state.diagnostics?.menuAutoSweeps||0),
    teamContextCacheWrites:Number(state.diagnostics?.teamContextCacheWrites||0)
  }
}
};}

function captureWindowOf(minute,extra,liveStatus){
  if(liveStatus!=="live") return "idle";
  const m=Number(minute); if(!Number.isFinite(m)) return "normal";
  if((m>=28&&m<=48)||(m>=78&&m<=105)||m>105) return "critical";
  return "normal";
}
function buildIntegrity(){
  try{pruneFutureEvents()}catch{}
  try{reconcileCornerEvents()}catch{}

  const checks=[];
  const age=state.lastUpdate?Math.max(0,Date.now()-Number(state.lastUpdate)):null;
  const observed=Array.isArray(state.capture?.observedMinutes)?state.capture.observedMinutes.map(Number).filter(Number.isFinite).sort((a,b)=>a-b):[];
  const missing=[];
  if(observed.length>=2){
    for(let i=1;i<observed.length;i++){
      const prev=observed[i-1], cur=observed[i];
      if(cur-prev>1 && !(prev===45&&cur>=46) && !(prev===90&&cur>=91)){
        for(let g=prev+1;g<cur&&g<=130;g++) missing.push(g);
      }
    }
  }
  state.capture.missingMinutes=missing.slice(-40);
  const window=captureWindowOf(state.minute,state.extraMinute,state.liveStatus);
  const isFinishedMatch=state.liveStatus==="finished"||state.dataMode==="historical";
  const staleLimit=isFinishedMatch?300000:12000;
  const stale=!isFinishedMatch && age!=null && age>staleLimit;
  const gap=missing.length>0;

  // --- 1) Relógio ---
  const clock=Number(state.minute);
  const hasClock=Number.isFinite(clock);
  const eff=effectiveLiveMinute();
  const clockDetail=hasClock?`${clock}+${state.extraMinute||0}${state.diagnostics?.clockStale?` · corr→${eff}' (DOM travado)`:""}`:"missing";
  checks.push({id:"clock",ok:hasClock||state.liveStatus==="finished",detail:clockDetail});

  // --- 2) Fixture / times ---
  try{recoverFixtureFromCharts();}catch{}
  const hasFid=!!state.fixtureId;
  const hasTeamNames=!!(state.home&&state.away);
  const hasTeams=hasFid && hasTeamNames;
  // [v6.9.9.83] Soft-pass: times + placar/relógio bastam quando SPA não expõe /fixture/ na URL
  const softOk=hasTeamNames&&(Number.isFinite(Number(state.minute))||(state.score&&(state.score.home!=null||state.score.away!=null)));
  checks.push({
    id:"fixture",
    ok:hasTeams||!!recoverFixtureFromCharts()||softOk,
    detail:state.fixtureId||(hasTeamNames?`${state.home}×${state.away} (id pendente)`:"none")
  });

  // --- 3) Cantos: stats vs eventos ---
  const sh=Number(state.stats?.corners?.home);
  const sa=Number(state.stats?.corners?.away);
  const ev=(state.cornerEvents||[]).filter(e=>eventWithinClock?eventWithinClock(e):true);
  const eh=ev.filter(e=>e.side==="home").length;
  const ea=ev.filter(e=>e.side==="away").length;
  const statsOk=Number.isFinite(sh)&&Number.isFinite(sa);
  const eventsOk=ev.length>=0;
  // Lógica de tolerância (side-skew ≤1/lado com total batendo, timeline pendente
  // no início da partida, inflação de eventos) vive em lib/corner-align.js —
  // fonte única compartilhada com o painel de revisão (diagnostics.js) para que
  // os dois nunca discordem sobre os mesmos dados.
  const cornerAlign=CornerAILib.evaluateCornerAlign({
    statsHome:sh,statsAway:sa,eventsHome:eh,eventsAway:ea,
    liveMinute:Number(state.minute)||0,
    isLive:true,
    hasEventChannel:Number(state.diagnostics?.hookMessages||0)>0
  });
  const cornerLagH=cornerAlign.lag[0], cornerLagA=cornerAlign.lag[1];
  const totalStats=cornerAlign.totals[0];
  const cornerInflated=cornerAlign.inflated;
  const timelinePending=cornerAlign.timelinePending;
  checks.push({id:"corners-stats-events",ok:cornerAlign.ok,detail:cornerAlign.detail,pending:timelinePending});

  // --- 4) Eventos futuros (regra única e estrita: m > clock+2) ---
  const clockEff=hasClock?(effectiveLiveMinute()??clock):clock;
  const future=(state.matchEvents||[]).filter(e=>{
    if(!hasClock||String(state.liveStatus)!=="live") return false;
    const m=Number(e.minute);
    return Number.isFinite(m) && m > clockEff + 2;
  });
  // Também limpa cornerEvents no check
  const futureCorners=(state.cornerEvents||[]).filter(e=>{
    if(!hasClock||String(state.liveStatus)!=="live") return false;
    const m=Number(e.minute);
    return Number.isFinite(m) && m > clockEff + 2;
  });
  if(futureCorners.length){
    state.cornerEvents=(state.cornerEvents||[]).filter(e=>{
      const m=Number(e.minute);
      return !(Number.isFinite(m) && m > clockEff + 2);
    });
  }
  checks.push({id:"no-future-events",ok:future.length===0&&futureCorners.length===0,detail:(future.length||futureCorners.length)?[...future,...futureCorners].map(e=>`${e.minute}'${e.type||"corner"}`).slice(0,5).join(","):"ok"});

  // --- 5) Ordem cronológica de cantos ---
  let ordered=true;
  for(let i=1;i<ev.length;i++){
    const a=ev[i-1], b=ev[i];
    const am=(Number(a.minute)||0)+0.01*(Number(a.extraMinute)||0);
    const bm=(Number(b.minute)||0)+0.01*(Number(b.extraMinute)||0);
    if(bm<am){ordered=false;break;}
  }
  checks.push({id:"corners-ordered",ok:ordered,detail:ordered?"ok":"out-of-order"});

  // --- 6) Pressão dual válida ---
  // 0×N ou N×0 é válido (domínio unilateral no intervalo). Só invalida null/NaN/pct fora de 0–100.
  const bars=state.charts?.pressureBars&&typeof state.charts.pressureBars==="object"?state.charts.pressureBars:{};
  let badBars=0, goodBars=0, pressureOk=true;
  if(typeof CornerAILib!=="undefined"&&CornerAILib.evaluatePressureDual){
    const pr=CornerAILib.evaluatePressureDual(bars);
    goodBars=pr.goodBars; badBars=pr.badBars; pressureOk=pr.ok;
  } else {
    for(const [k,v] of Object.entries(bars)){
      if(!v||v.empty) continue;
      const h=Number(v.home), a=Number(v.away), pct=Number(v.pct);
      const dual=
        (Number.isFinite(h)&&Number.isFinite(a)&&h>=0&&a>=0)||
        (Number.isFinite(pct)&&pct>=0&&pct<=100);
      if(dual) goodBars++; else badBars++;
    }
    const totalBars=goodBars+badBars;
    const ratio=totalBars?goodBars/totalBars:1;
    pressureOk=badBars===0||(goodBars>=3&&ratio>=0.75);
  }
  checks.push({id:"pressure-dual",ok:pressureOk,detail:`good ${goodBars} · bad ${badBars}`});

  // --- 7) Placar finito ---
  const scoreOk=state.score&&Number.isFinite(Number(state.score.home))&&Number.isFinite(Number(state.score.away));
  checks.push({id:"score",ok:!!scoreOk,detail:scoreOk?`${state.score.home}x${state.score.away}`:"missing"});

  // --- 8) Stale / gap ---
  checks.push({id:"freshness",ok:!stale,detail:age!=null?`${age}ms`:"n/a"});
  checks.push({id:"minute-coverage",ok:!gap,detail:missing.length?`missing ${missing.slice(0,8).join(",")}`:"ok"});

  const failed=checks.filter(x=>!x.ok);
  const integrityScore=Math.max(0,Math.round(100*(checks.length-failed.length)/Math.max(1,checks.length)));
  const networkOk=/m[24]\.sokkerpro|wss:\/\//i.test(String(state.diagnostics?.lastEndpoint||""))||Number(state.diagnostics?.networkResponses||0)>0;

  const report={
    score:Number(state.quality?.score||0),
    integrityScore,
    pass:failed.length===0,
    failed:failed.map(x=>x.id),
    checks,
    source:state.lastSnapshotSource||null,
    window,
    staleMs:age,
    stale,
    gap,
    missingMinutes:missing.slice(-20),
    observedMinutes:observed.slice(-30),
    corners:{stats:[statsOk?sh:null,statsOk?sa:null],events:[eh,ea],lag:[cornerLagH,cornerLagA],inflated:cornerInflated},
    hookAgeMs:state.diagnostics?.lastHookAt?Math.max(0,Date.now()-Number(state.diagnostics.lastHookAt)):null,
    networkOk,
    accepted:Number(state.capture?.acceptedSnapshots||0),
    rejected:Number(state.diagnostics?.rejectedStats||0)+Number(state.diagnostics?.rejectedEvents||0)
  };
  state.integrity=report;
  // Promove relógio efetivo para UI quando DOM está travado
  try{
    if(state.diagnostics?.clockStale&&state.diagnostics.clockCorrectedTo!=null){
      const to=Number(state.diagnostics.clockCorrectedTo);
      if(Number.isFinite(to)&&to>Number(state.minute||0)){
        state.minute=to;
        state.clockSource="corrected";
      }
    }
  }catch{}
  // Monitoramento em tempo real: série de integridade
  try{
    const hist=Array.isArray(state.integrityHistory)?state.integrityHistory:[];
    const last=hist[hist.length-1];
    const minute=Number(state.minute);
    const sig=JSON.stringify({m:minute,e:state.extraMinute||0,s:report.integrityScore,f:(report.failed||[]).join(",")});
    const lastSig=last?JSON.stringify({m:last.minute,e:last.extra||0,s:last.integrityScore,f:(last.failed||[]).join(",")}):null;
    if(sig!==lastSig){
      hist.push({
        ts:Date.now(),
        minute:Number.isFinite(minute)?minute:null,
        extra:state.extraMinute||0,
        window:report.window||null,
        integrityScore:report.integrityScore,
        pass:!!report.pass,
        failed:[...(report.failed||[])],
        corners:report.corners?{stats:report.corners.stats,events:report.corners.events,lag:report.corners.lag}:null,
        staleMs:report.staleMs??null,
        quality:report.score??null
      });
      state.integrityHistory=hist.slice(-180); // ~3h a 1 pt/min
    }
  }catch{}
  return report;
}


function buildPredictivePayload(){
  // Schema enriquecido para a Skill de IA analisar xG × escanteios com precisão máxima
  pruneFutureEvents();
  reconcileCornerEvents();
  const ts = Date.now();
  const minute = state.minute != null ? Number(state.minute) + (Number(state.extraMinute)||0)/100 : null;

  // --- helpers APPM ---
  function calcAPPM(side, windowMin, key){
    const tl = (state.statTimeline||[]).filter(p => p && p.stats && p.stats[key] != null);
    const nowM = minute != null ? minute : (tl.length ? (tl[tl.length-1].minute + (tl[tl.length-1].extraMinute||0)/100) : 1);
    if(tl.length >= 2){
      const cutoff = nowM - windowMin;
      const recent = tl.filter(p => (Number(p.minute) + (Number(p.extraMinute)||0)/100) >= cutoff);
      if(recent.length >= 2){
        const first = recent[0], last = recent[recent.length-1];
        const v0 = Number(first.stats[key]?.[side]||0);
        const v1 = Number(last.stats[key]?.[side]||0);
        const delta = Math.max(0, v1 - v0);
        const elapsed = Math.max(0.4, (Number(last.minute)+(Number(last.extraMinute)||0)/100) - (Number(first.minute)+(Number(first.extraMinute)||0)/100));
        return Number((delta / elapsed).toFixed(3));
      }
    }
    const lastVal = Number(state.stats?.[key]?.[side]||0);
    const clock = Math.max(1, nowM);
    if(lastVal > 0) return Number((lastVal / clock).toFixed(3));
    const inds = (state.cornerIndicatorTimeline||[]).slice(-5);
    for(let i=inds.length-1;i>=0;i--){
      const ap = inds[i]?.appm;
      if(!ap) continue;
      const winKey = windowMin<=1?"1m":windowMin<=3?"3m":windowMin<=5?"5m":"10m";
      const pair = ap[winKey];
      if(pair && Number.isFinite(Number(pair[side]))) return Number(Number(pair[side]).toFixed(3));
    }
    return 0;
  }

  // --- corners chronology enriquecida ---
  const rawCorners = (state.cornerEvents||[]).slice().sort((a,b)=>
    (Number(a.minute)+(Number(a.extraMinute)||0)/100) - (Number(b.minute)+(Number(b.extraMinute)||0)/100)
  );

  // Contextos já capturados (últimos 10 min antes de cada canto)
  const contexts = Array.isArray(state.cornerContexts) ? state.cornerContexts : [];
  const matchEvents = Array.isArray(state.matchEvents) ? state.matchEvents : [];

  function eventsInWindow(beforeMinute, windowMin, side){
    const lo = beforeMinute - windowMin;
    return matchEvents.filter(e=>{
      const m = Number(e.minute) + (Number(e.extraMinute)||0)/100;
      if(!Number.isFinite(m) || m < lo || m >= beforeMinute) return false;
      if(side && e.side && e.side !== side) return false;
      return true;
    });
  }

  function countTypes(evts){
    const c = {shot_on:0, shot_off:0, corner:0, offside:0, foul:0, yellow:0, red:0, other:0};
    for(const e of evts){
      const t = String(e.type||"").toLowerCase();
      if(t.includes("shot_on")||t.includes("chute no")||t.includes("on target")) c.shot_on++;
      else if(t.includes("shot_off")||t.includes("bloqueado")||t.includes("ao lado")||t.includes("off target")) c.shot_off++;
      else if(t.includes("corner")||t.includes("escanteio")) c.corner++;
      else if(t.includes("offside")||t.includes("impedimento")) c.offside++;
      else if(t.includes("foul")||t.includes("falta")) c.foul++;
      else if(t.includes("yellow")||t.includes("amarelo")) c.yellow++;
      else if(t.includes("red")||t.includes("vermelho")) c.red++;
      else c.other++;
    }
    return c;
  }

  // xG no momento mais próximo do canto (via timeline)
  function xGNear(minuteVal, side){
    const tl = (state.statTimeline||[]).filter(p=>p&&p.stats&&p.stats.xg);
    if(!tl.length) return null;
    let best=null, bestDist=999;
    for(const p of tl){
      const m = Number(p.minute)+(Number(p.extraMinute)||0)/100;
      const d = Math.abs(m - minuteVal);
      if(d < bestDist){ bestDist=d; best=p; }
    }
    if(!best) return null;
    return Number(best.stats.xg?.[side]||0);
  }

  const corners_enriched = rawCorners.map((e, idx)=>{
    const m = Number(e.minute) + (Number(e.extraMinute)||0)/100;
    const side = e.side === "away" ? "away" : "home";
    const period = e.period === 2 ? 2 : (m >= 46 ? 2 : 1);
    const pre10 = eventsInWindow(m, 10, side);
    const pre5 = eventsInWindow(m, 5, side);
    const types10 = countTypes(pre10);
    const types5 = countTypes(pre5);
    const xgAt = xGNear(m, side);
    // qualidade do canto: score simples baseado em contexto
    let quality = 0.3;
    if(types10.shot_on > 0) quality += 0.25;
    if(types5.shot_on > 0) quality += 0.15;
    if(types10.shot_off >= 2) quality += 0.1;
    if(types10.corner >= 1) quality += 0.1; // pressão sustentada
    quality = Math.min(1, Number(quality.toFixed(2)));

    // Corner Sequential Density — time_delta_seconds between consecutive corners
    let time_delta_seconds = null;
    let canto_casado = false;
    if(idx > 0){
      const prev = rawCorners[idx-1];
      const prevM = Number(prev.minute) + (Number(prev.extraMinute)||0)/100;
      time_delta_seconds = Math.round((m - prevM) * 60);
      if(time_delta_seconds <= 120) canto_casado = true;
    }

    return {
      minute: Number(m.toFixed(2)),
      team: side,
      period,
      index: idx + 1,
      quality_score: quality,
      xg_at_moment: xgAt,
      context_10m: types10,
      context_5m: types5,
      has_shot_on_10m: types10.shot_on > 0,
      has_shot_on_5m: types5.shot_on > 0,
      pressure_signal: types10.shot_on + types10.shot_off + types10.corner,
      time_delta_seconds,
      canto_casado
    };
  });

  // Agregados por equipe para a Skill
  function teamCornerStats(side){
    const list = corners_enriched.filter(c=>c.team===side);
    const withShotOn = list.filter(c=>c.has_shot_on_10m);
    const xgVals = list.map(c=>c.xg_at_moment).filter(v=>v!=null);
    const totalCorners = Number(state.stats?.corners?.[side])||list.length;
    const xgNow = Number(state.stats?.xg?.[side])||0;
    const baseXgPerCorner = totalCorners > 0 ? (xgNow/totalCorners) : 0;
    const scale = (typeof xgPerCornerScale !== "undefined" && xgPerCornerScale[side]) ? xgPerCornerScale[side] : 1.0;
    return {
      total: totalCorners,
      events_captured: list.length,
      with_shot_on_context: withShotOn.length,
      pct_quality_corners: list.length ? Number((withShotOn.length/list.length).toFixed(2)) : 0,
      avg_quality_score: list.length ? Number((list.reduce((s,c)=>s+c.quality_score,0)/list.length).toFixed(2)) : 0,
      xg_per_corner: Number((baseXgPerCorner * scale).toFixed(3)),
      xg_per_corner_base: Number(baseXgPerCorner.toFixed(3)),
      xg_scale_factor: scale,
      xg_current: xgNow,
      minutes: list.map(c=>c.minute),
      canto_casado_count: list.filter(c=>c.canto_casado).length
    };
  }

  const appmHome = {
    last_5: calcAPPM("home", 5, "attacks"),
    last_10: calcAPPM("home", 10, "attacks"),
    last_100: calcAPPM("home", 100, "attacks"),
    dangerous_last_5: calcAPPM("home", 5, "dangerous"),
    dangerous_last_10: calcAPPM("home", 10, "dangerous"),
    dangerous_last_100: calcAPPM("home", 100, "dangerous")
  };
  const appmAway = {
    last_5: calcAPPM("away", 5, "attacks"),
    last_10: calcAPPM("away", 10, "attacks"),
    last_100: calcAPPM("away", 100, "attacks"),
    dangerous_last_5: calcAPPM("away", 5, "dangerous"),
    dangerous_last_10: calcAPPM("away", 10, "dangerous"),
    dangerous_last_100: calcAPPM("away", 100, "dangerous")
  };

  // --- APPM Acceleration Velocity (ΔAPPM) ---
  const deltaAppmHome = Number((appmHome.last_5 - appmHome.last_10).toFixed(3));
  const deltaAppmAway = Number((appmAway.last_5 - appmAway.last_10).toFixed(3));
  const offensive_acceleration = {
    home: deltaAppmHome > 1.5,
    away: deltaAppmAway > 1.5,
    delta: { home: deltaAppmHome, away: deltaAppmAway }
  };

  let ftHome = Number(state.extendedStats?.final_third?.home ?? state.extendedStats?.possession_final_third?.home ?? state.stats?.possession?.home ?? 0);
  let ftAway = Number(state.extendedStats?.final_third?.away ?? state.extendedStats?.possession_final_third?.away ?? state.stats?.possession?.away ?? 0);

  // --- Final Third Dominance Density (FTDD) ---
  const FTDD = {
    home: Number(((ftHome * (appmHome.dangerous_last_5 || 0)) / 100).toFixed(4)),
    away: Number(((ftAway * (appmAway.dangerous_last_5 || 0)) / 100).toFixed(4))
  };

  // --- Refined Red Card Game-State Shock ---
  const redHome = Number(state.stats?.red?.home) || 0;
  const redAway = Number(state.stats?.red?.away) || 0;
  const redCardEvents = (state.matchEvents||[]).filter(e=>{
    const t = String(e.type||"").toLowerCase();
    return t.includes("red") || t.includes("vermelho") || t.includes("expuls");
  }).map(e=>({
    minute: Number(e.minute)+(Number(e.extraMinute)||0)/100,
    team: e.side==="away"?"away":"home",
    ts: e.ts || e.timestamp || 0
  }));
  let xgPerCornerScale = { home: 1.0, away: 1.0 };
  let containment_collapse = { home: false, away: false, triggered_at: null };
  if(redHome > redAway){
    // Away has numerical superiority
    xgPerCornerScale.away = 1.25;
    // Check if home final_third dropped below 15% in subsequent 180s
    const lastRed = redCardEvents.filter(r=>r.team==="home").slice(-1)[0];
    if(lastRed && minute != null && (minute - lastRed.minute) <= 3){
      if(ftHome < 15){
        containment_collapse.home = true;
        containment_collapse.triggered_at = lastRed.minute;
      }
    }
  } else if(redAway > redHome){
    xgPerCornerScale.home = 1.25;
    const lastRed = redCardEvents.filter(r=>r.team==="away").slice(-1)[0];
    if(lastRed && minute != null && (minute - lastRed.minute) <= 3){
      if(ftAway < 15){
        containment_collapse.away = true;
        containment_collapse.triggered_at = lastRed.minute;
      }
    }
  }

  // --- Odds Deviation Volatility (σ_odds) / smart_money_validation ---
  function computeSmartMoneyValidation(enrichedCorners){
    const history = Array.isArray(state.oddsHistory) ? state.oddsHistory : [];
    if(!history.length || !enrichedCorners.length) return { smart_money_validation: false, details: [] };
    const details = [];
    let anyValid = false;
    for(const c of enrichedCorners){
      if(c.quality_score < 0.55) continue;
      const cornerTsApprox = Date.now() - Math.max(0, (minute - c.minute) * 60000);
      // Look for odds movement around the corner (±45s window approximated via history timestamps)
      const nearby = history.filter(o=>{
        const ots = Number(o.timestamp || o.ts || 0);
        return ots > 0 && Math.abs(ots - cornerTsApprox) <= 45000;
      });
      if(nearby.length < 2) continue;
      const sorted = nearby.slice().sort((a,b)=>(a.timestamp||a.ts||0)-(b.timestamp||b.ts||0));
      const firstOdd = Number(sorted[0].odds);
      const lastOdd = Number(sorted[sorted.length-1].odds);
      if(!Number.isFinite(firstOdd) || !Number.isFinite(lastOdd)) continue;
      const deltaOdd = Math.abs(firstOdd - lastOdd);
      if(deltaOdd > 0.15){
        anyValid = true;
        details.push({
          corner_minute: c.minute,
          team: c.team,
          delta_odd: Number(deltaOdd.toFixed(3)),
          quality: c.quality_score
        });
      }
    }
    return { smart_money_validation: anyValid, details: details.slice(-8) };
  }
  const smartMoney = computeSmartMoneyValidation(corners_enriched);

  const isCrit = (function(){
    const m = Number(state.minute);
    if(!Number.isFinite(m)) return false;
    return (m>=28 && m<=48) || (m>=78 && m<=105);
  })();

  
  // --- Clusters de cantos (2+ em janela de 5 min) ---
  function buildCornerClusters(enriched){
    const clusters = [];
    const sorted = enriched.slice().sort((a,b)=>a.minute-b.minute);
    let i = 0;
    while(i < sorted.length){
      const group = [sorted[i]];
      let j = i + 1;
      while(j < sorted.length && (sorted[j].minute - sorted[i].minute) <= 5){
        group.push(sorted[j]);
        j++;
      }
      if(group.length >= 2){
        const teams = {};
        group.forEach(c=>{ teams[c.team]=(teams[c.team]||0)+1; });
        const qualityAvg = group.reduce((s,c)=>s+c.quality_score,0)/group.length;
        const hasShotOn = group.some(c=>c.has_shot_on_10m);
        const highPressureCluster = group.length >= 2 && hasShotOn;
        clusters.push({
          start_minute: group[0].minute,
          end_minute: group[group.length-1].minute,
          count: group.length,
          teams,
          avg_quality: Number(qualityAvg.toFixed(2)),
          has_shot_on: hasShotOn,
          high_pressure: group.length >= 3 || qualityAvg >= 0.6,
          high_pressure_cluster: highPressureCluster
        });
      }
      i = j > i+1 ? j : i+1;
    }
    return clusters;
  }
  const cornerClusters = buildCornerClusters(corners_enriched);

  // --- Substituições ---
  const subsHome = Number(state.stats?.subs?.home)||0;
  const subsAway = Number(state.stats?.subs?.away)||0;
  const subEvents = (state.matchEvents||[]).filter(e=>{
    const t=String(e.type||"").toLowerCase();
    return t.includes("sub")||t.includes("substit");
  }).map(e=>({
    minute: Number(e.minute)+(Number(e.extraMinute)||0)/100,
    team: e.side==="away"?"away":"home",
    period: e.period===2?2:1
  }));

  // Impacto de sub na pressão: se houve sub e APPM 5m caiu vs 10m
  function subPressureImpact(side){
    const subs = side==="home"?subsHome:subsAway;
    if(subs<=0) return {subs:0, impact:"none"};
    const appm5 = side==="home"?appmHome.dangerous_last_5:appmAway.dangerous_last_5;
    const appm10 = side==="home"?appmHome.dangerous_last_10:appmAway.dangerous_last_10;
    let impact = "neutral";
    if(appm5 < appm10 * 0.7) impact = "pressure_drop";
    else if(appm5 > appm10 * 1.3) impact = "pressure_rise";
    return {subs, appm5, appm10, impact};
  }

  // --- Favorito perdendo (odds + placar) ---
  function detectFavoriteLosing(){
    const scoreH = Number(state.score?.home)||0;
    const scoreA = Number(state.score?.away)||0;
    // Extract current 1X2 snapshot
    let oddHome=null, oddDraw=null, oddAway=null;
    const hist = Array.isArray(state.oddsHistory)?state.oddsHistory:[];
    for(let i=hist.length-1;i>=0;i--){
      const o = hist[i];
      if(!o) continue;
      if(o.home!=null) oddHome=Number(o.home);
      if(o.draw!=null) oddDraw=Number(o.draw);
      if(o.away!=null) oddAway=Number(o.away);
      if(o.odds){
        if(o.odds.home!=null) oddHome=Number(o.odds.home);
        if(o.odds.draw!=null) oddDraw=Number(o.odds.draw);
        if(o.odds.away!=null) oddAway=Number(o.odds.away);
      }
      // Prefer 1X2 market
      const mt = String(o.marketType||o.market||"").toLowerCase();
      if((mt.includes("1x2")||mt.includes("match result")||mt.includes("resultado")||!mt) && (oddHome||oddAway)) break;
    }
    const mk = state.oddsMarkets||{};
    for(const k of Object.keys(mk)){
      const m=mk[k];
      if(!m) continue;
      const mt = String(k||m.market||"").toLowerCase();
      if(m.home!=null&&oddHome==null) oddHome=Number(m.home);
      if(m.away!=null&&oddAway==null) oddAway=Number(m.away);
      if(m.draw!=null&&oddDraw==null) oddDraw=Number(m.draw);
    }
    // LOCK opening_odds on first valid 1X2 snapshot — never swap fixed_favorite
    if(!state.openingOdds && oddHome!=null && oddAway!=null && Number.isFinite(oddHome) && Number.isFinite(oddAway) && oddHome>=1.01 && oddAway>=1.01){
      state.openingOdds = {home:oddHome, draw:oddDraw, away:oddAway, lockedAt:Date.now()};
      if(oddHome <= oddAway) state.fixedFavorite = "home";
      else state.fixedFavorite = "away";
      // Prefer explicit favorite when opening odd <= 2.10
      if(oddHome <= 2.10 && oddHome < oddAway) state.fixedFavorite = "home";
      else if(oddAway <= 2.10 && oddAway < oddHome) state.fixedFavorite = "away";
      state.openingOddsLockedAt = Date.now();
    }
    const fixed = state.fixedFavorite;
    const open = state.openingOdds || {};
    const result = {
      odd_home: oddHome,
      odd_draw: oddDraw,
      odd_away: oddAway,
      opening_odds: open.home!=null ? {home:open.home, draw:open.draw, away:open.away} : null,
      fixed_favorite: fixed,
      score: {home:scoreH, away:scoreA},
      favorite: fixed,
      favorite_losing: false,
      priority_boost: false
    };
    // Strict rule: fixed_favorite opening odd <= 2.10 AND currently losing
    const openOddFav = fixed==="home" ? open.home : (fixed==="away" ? open.away : null);
    if(fixed==="home" && openOddFav!=null && openOddFav <= 2.10 && scoreH < scoreA){
      result.favorite_losing = true;
      result.priority_boost = true;
    }
    if(fixed==="away" && openOddFav!=null && openOddFav <= 2.10 && scoreA < scoreH){
      result.favorite_losing = true;
      result.priority_boost = true;
    }
    if(scoreH===scoreA && minute!=null && minute>=70) {
      result.late_draw = true;
    }
    return result;
  }
  const favoriteState = detectFavoriteLosing();

  // Mathematical Pressure Formula (score_pressao_canto) — per side
  function computeScorePressaoCanto(side){
    const quality = (function(){
      const list = corners_enriched.filter(c=>c.team===side);
      if(!list.length) return 0;
      return list.reduce((s,c)=>s+c.quality_score,0)/list.length;
    })();
    const hasShotOn10m = corners_enriched.some(c=>c.team===side && c.has_shot_on_10m) ? 1 : 0;
    // Recent 10m shot_on for current pressure (not only historical corners)
    const recentEvents = (state.matchEvents||[]).filter(e=>{
      const m = Number(e.minute)+(Number(e.extraMinute)||0)/100;
      return Number.isFinite(m) && minute!=null && m >= minute-10 && m <= minute && (e.side===side || (side==="home"&&e.side!=="away"));
    });
    const typesRecent = countTypes(recentEvents);
    const hasShotOnLive = (typesRecent.shot_on > 0) ? 1 : 0;
    const appm5 = side==="home" ? (appmHome.dangerous_last_5||0) : (appmAway.dangerous_last_5||0);
    const appmTerm = Math.min(1, appm5 / 2);
    const crit = isCrit ? 1 : 0;
    const favLosing = (favoriteState.favorite_losing && favoriteState.fixed_favorite===side) ? 1 : 0;
    const score = (0.35 * quality) + (0.25 * Math.max(hasShotOn10m, hasShotOnLive)) + (0.20 * appmTerm) + (0.10 * crit) + (0.10 * favLosing);
    return {
      score_pressao_canto: Number(score.toFixed(4)),
      components: {
        quality_score: Number(quality.toFixed(3)),
        has_shot_on_10m: Math.max(hasShotOn10m, hasShotOnLive),
        APPM_dangerous_5m: Number(appm5.toFixed(3)),
        appm_term: Number(appmTerm.toFixed(3)),
        critical_window: crit,
        favorite_losing: favLosing
      }
    };
  }
  const pressureHome = computeScorePressaoCanto("home");
  const pressureAway = computeScorePressaoCanto("away");

  // --- CPI v2.0 (Corner Pressure Index) with exponential decay ---
  // Weights are adjustable via PARAMS.cpiWeights if present.
  function computeCPIv2(side){
    const weights=Object.assign({
      dangerous:0.28, shotsOn:0.18, xg:0.16, corners:0.12, appm:0.14, possession:0.07, favorite:0.05
    }, (PARAMS.cpiWeights&&typeof PARAMS.cpiWeights==="object")?PARAMS.cpiWeights:{});
    // Dynamic late-game weights: after 80' offensive desperation rises
    const minuteNow=Number(minute);
    if(Number.isFinite(minuteNow)&&minuteNow>=80){
      weights.dangerous=Number(weights.dangerous)+0.06;
      weights.appm=Number(weights.appm)+0.04;
      weights.possession=Math.max(0.03,Number(weights.possession)-0.03);
    }
    // Fatigue dampener from substitutions / intensity (if temporal available)
    const fatigueSide=Number(state.temporal?.fatigue?.[side]||0);
    if(fatigueSide>0.55){
      weights.appm=Math.max(0.06,Number(weights.appm)-0.03);
      weights.dangerous=Number(weights.dangerous)+0.02; // more direct plays when tired
    }
    const halfLifeMin=Number(PARAMS.cpiHalfLifeMin||6); // exponential half-life in match minutes
    // Adaptive λ from game intensity + convert to effective half-life awareness
    const lambda= (typeof adaptiveDecayLambda==="function") ? adaptiveDecayLambda() : (Math.log(2)/Math.max(1,halfLifeMin));
    const nowM=Number(minute);
    const hasClock=Number.isFinite(nowM);
    // Time-decayed contribution from recent corner quality & shot_on contexts
    let decayCorner=0, decayShot=0, wSum=0;
    for(const c of corners_enriched){
      if(c.team!==side) continue;
      if(!hasClock) break;
      const age=Math.max(0, nowM - Number(c.minute));
      const w=Math.exp(-lambda*age);
      decayCorner += Number(c.quality_score||0)*w;
      decayShot += (c.has_shot_on_10m?1:0)*w;
      wSum += w;
    }
    const decayQuality=wSum>0?decayCorner/wSum:0;
    const decayShotOn=wSum>0?Math.min(1,decayShot/wSum):0;
    const dang=Number(state.stats?.dangerous?.[side])||0;
    const shotsOn=Number(state.stats?.shotsOn?.[side])||0;
    const xg=Number(state.stats?.xg?.[side])||0;
    const corners=Number(state.stats?.corners?.[side])||0;
    const poss=Number(state.stats?.possession?.[side])||0;
    const appm5=side==="home"?(appmHome.dangerous_last_5||0):(appmAway.dangerous_last_5||0);
    const clock=Math.max(1, hasClock?nowM:1);
    // Normalize rates into 0..1-ish bands
    const nDangerous=Math.max(0,Math.min(1,(dang/clock)/0.9));
    const nShotsOn=Math.max(0,Math.min(1,(shotsOn/clock)/0.35));
    const nXg=Math.max(0,Math.min(1,xg/2.2));
    const nCorners=Math.max(0,Math.min(1,(corners/clock)/0.25));
    const nAppm=Math.max(0,Math.min(1,appm5/2.0));
    const nPoss=Math.max(0,Math.min(1,poss/100));
    const fav=(favoriteState.favorite_losing && favoriteState.fixed_favorite===side)?1:0;
    const blend =
      weights.dangerous*nDangerous +
      weights.shotsOn*(0.55*nShotsOn+0.45*decayShotOn) +
      weights.xg*nXg +
      weights.corners*(0.5*nCorners+0.5*decayQuality) +
      weights.appm*nAppm +
      weights.possession*nPoss +
      weights.favorite*fav;
    const weightTotal=Object.values(weights).reduce((a,b)=>a+Number(b||0),0)||1;
    // Competition + home/away calibration
    const calib=buildCalibrationContext();
    const sideFactor=side==="home"?calib.sideFactors.home:calib.sideFactors.away;
    const situ=(typeof buildSituationalFactors==="function")?buildSituationalFactors():{home:1,away:1};
    const situF=side==="home"?situ.home:situ.away;
    const mom=(typeof momentWeight==="function")?momentWeight(minute):1;
    const atkF=(typeof computeTeamAttackFactor==="function")?computeTeamAttackFactor(side):1;
    const cpi=Number(Math.max(0,Math.min(1,(blend/weightTotal)*Math.min(1.35,sideFactor)*Math.min(1.3,situF)*Math.min(1.4,mom)*Math.min(1.35,atkF))).toFixed(4));
    return {
      cpi,
      halfLifeMin,
      components:{
        dangerous:Number(nDangerous.toFixed(3)),
        shotsOn:Number(nShotsOn.toFixed(3)),
        xg:Number(nXg.toFixed(3)),
        corners:Number(nCorners.toFixed(3)),
        appm5:Number(nAppm.toFixed(3)),
        possession:Number(nPoss.toFixed(3)),
        decayQuality:Number(decayQuality.toFixed(3)),
        decayShotOn:Number(decayShotOn.toFixed(3)),
        favorite_losing:fav
      },
      weights
    };
  }
  const cpiHome=computeCPIv2("home");
  const cpiAway=computeCPIv2("away");

const payload = {
    match_identity: {
      match_id: String(state.fixtureId || "unknown"),
      home_team: String(state.home || "HOME"),
      away_team: String(state.away || "AWAY"),
      timestamp_ms: ts,
      current_minute: minute
    },
    live_score: {
      home: Number(state.score?.home) || 0,
      away: Number(state.score?.away) || 0
    },
    corners_chronology: corners_enriched.map(c=>({
      minute: c.minute,
      team: c.team,
      period: c.period,
      quality_score: c.quality_score,
      has_shot_on_10m: c.has_shot_on_10m,
      time_delta_seconds: c.time_delta_seconds,
      canto_casado: c.canto_casado
    })),
    // BLOCO ENRIQUECIDO PARA A SKILL DE IA
    corners_intelligence: {
      enriched: corners_enriched,
      by_team: {
        home: teamCornerStats("home"),
        away: teamCornerStats("away")
      },
      correlation_signals: {
        home_xg_per_corner: teamCornerStats("home").xg_per_corner,
        away_xg_per_corner: teamCornerStats("away").xg_per_corner,
        home_quality_pct: teamCornerStats("home").pct_quality_corners,
        away_quality_pct: teamCornerStats("away").pct_quality_corners,
        home_corners_with_shot_on: teamCornerStats("home").with_shot_on_context,
        away_corners_with_shot_on: teamCornerStats("away").with_shot_on_context,
        insight: "Escanteio com shot_on nos 10 min anteriores correlaciona melhor com xG do que volume bruto de cantos"
      },
      clusters: cornerClusters,
      active_cluster: cornerClusters.filter(c=>minute!=null&&minute-c.end_minute<=8).slice(-1)[0]||null
    },
    substitutions: {
      home: subPressureImpact("home"),
      away: subPressureImpact("away"),
      events: subEvents
    },
    match_context: {
      favorite: favoriteState.favorite,
      fixed_favorite: favoriteState.fixed_favorite,
      favorite_losing: favoriteState.favorite_losing,
      priority_boost: favoriteState.priority_boost,
      late_draw: !!favoriteState.late_draw,
      opening_odds: favoriteState.opening_odds,
      odds: {home:favoriteState.odd_home, draw:favoriteState.odd_draw, away:favoriteState.odd_away},
      score: favoriteState.score,
      business_rule: favoriteState.favorite_losing
        ? "Favorito perdendo → priorizar cantos + APPM 5m do favorito na janela crítica"
        : (favoriteState.late_draw ? "Empate tardio → elevar peso de próximo canto de qualidade" : "normal")
    },
    score_pressao_canto: {
      home: pressureHome,
      away: pressureAway,
      formula: "0.35*quality_score + 0.25*has_shot_on_10m + 0.20*min(1,APPM_dangerous_5m/2) + 0.10*critical_window + 0.10*favorite_losing"
    },
    cards: {
      home_yellow: Number(state.stats?.yellow?.home) || 0,
      home_red: Number(state.stats?.red?.home) || 0,
      away_yellow: Number(state.stats?.yellow?.away) || 0,
      away_red: Number(state.stats?.red?.away) || 0
    },
    advanced_metrics: {
      APPM: { home: appmHome, away: appmAway },
      delta_APPM: offensive_acceleration.delta,
      offensive_acceleration: {
        home: offensive_acceleration.home,
        away: offensive_acceleration.away
      },
      CPI_v2: {
        home: cpiHome,
        away: cpiAway,
        formula: "weighted(dangerous,shotsOn,xg,corners,appm,possession,favorite) with exp decay halfLife on corner quality/shot_on + late-game/fatigue dynamics"
      },
      temporal: (function(){
        const t=state.temporal||buildTemporalIntelligence();
        if(!t) return null;
        let pred=predictCornerNext2m(null,t.windows,t.peaks,t.sequences,cpiHome.cpi,cpiAway.cpi);
        // Feedback calibration: damp probability if historically overconfident
        const fb=state.feedback?.stats;
        if(fb&&fb.n>=10&&fb.avgPred>fb.hitRate+0.05){
          const damp=Math.max(0.85, 1-(fb.avgPred-fb.hitRate));
          pred={...pred,probability:Number(Math.max(0.02,Math.min(0.85,pred.probability*damp)).toFixed(3)),calibrated:true,damp:Number(damp.toFixed(3))};
        }
        try{recordCornerPrediction(pred);}catch{}
        try{resolveFeedbackAgainstCorners();}catch{}
        return {
          windows:t.windows,
          peaks:t.peaks,
          sequences:t.sequences,
          fatigue:t.fatigue,
          businessRules:t.businessRules,
          prediction_corner_2m:pred,
          feedback:state.feedback?.stats||null,
          calibration:buildCalibrationContext()
        };
      })(),
      FTDD: FTDD,
      total_shots: {
        home_on_target: Number(state.stats?.shotsOn?.home) || 0,
        home_off_target: Number(state.stats?.shotsOff?.home) || 0,
        away_on_target: Number(state.stats?.shotsOn?.away) || 0,
        away_off_target: Number(state.stats?.shotsOff?.away) || 0
      },
      final_third_possession: { home: ftHome, away: ftAway },
      xg: {
        home: Number(state.stats?.xg?.home) || 0,
        away: Number(state.stats?.xg?.away) || 0
      },
      xg_per_corner_scale: xgPerCornerScale,
      containment_collapse: containment_collapse,
      dangerous_attacks: {
        home: Number(state.stats?.dangerous?.home) || 0,
        away: Number(state.stats?.dangerous?.away) || 0
      },
      smart_money_validation: smartMoney.smart_money_validation,
      smart_money_details: smartMoney.details,
      canto_casado_events: corners_enriched.filter(c=>c.canto_casado).map(c=>({
        minute: c.minute,
        team: c.team,
        time_delta_seconds: c.time_delta_seconds
      }))
    },
    _meta: {
      schema: "cornerai-predictive-3",
      version: VERSION,
      critical: isCrit,
      quality: state.quality?.score || 0,
      source: state.lastSnapshotSource || "mixed",
      purpose: "AI Skill — clusters, favorite_losing, subs impact, quality corners, ΔAPPM, FTDD, red-card shock, smart-money, canto_casado"
    }
  };
  return payload;
}

function buildAnalystFeed(){
  const s=state;
  const integrity=buildIntegrity();
  const clockMin=Number(s.minute);
  const hasClock=Number.isFinite(clockMin);
  // pressure bars filtrados
  const rawBars=s.charts?.pressureBars&&typeof s.charts.pressureBars==="object"?s.charts.pressureBars:{};
  const bars={};
  for(const [k,v] of Object.entries(rawBars)){
    if(!v||v.empty) continue;
    const im=String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
    if(!im) continue;
    const start=Number(im[1]);
    if(hasClock&&start>clockMin) continue;
    let h=Number(v.home),a=Number(v.away),pct=Number(v.pct);
    if(Number.isFinite(pct)&&pct>=0&&pct<=100){h=pct;a=Number((100-pct).toFixed(1));}
    else if(Number.isFinite(h)&&Number.isFinite(a)&&h>0&&a>0&&(h>100||a>100||(h<=1.5&&a<=1.5))){
      const sum=h+a;h=Number(((h/sum)*100).toFixed(1));a=Number(((a/sum)*100).toFixed(1));
    }
    if(!Number.isFinite(h)||!Number.isFinite(a)||h===0||a===0) continue;
    bars[im[1]+"-"+im[2]]=[h,a];
  }
  const corners=(s.cornerEvents||[]).map(e=>({
    m:Number(e.minute)||0,
    extra:Number(e.extraMinute)||0,
    period:e.period||null,
    side:e.side||null,
    team:e.team||null
  }));
  const cornerOdds=(s.oddsHistory||[]).filter(r=>r.marketType==="corners").slice(-30).map(r=>({
    line:r.line, selection:r.selection, odds:r.odds, fair:r.fairProbability??null, ts:r.timestamp||0
  }));
  // compact over/under pairs
  const ouMap={};
  for(const r of cornerOdds){
    const line=String(r.line||"");
    if(!line) continue;
    if(!ouMap[line]) ouMap[line]={line,over:null,under:null};
    if(/mais|over/i.test(r.selection||"")) ouMap[line].over=r.odds;
    if(/menos|under/i.test(r.selection||"")) ouMap[line].under=r.odds;
  }
  const oneX=(s.oddsHistory||[]).filter(r=>/resultado final/i.test(r.market||"")&&!/justa/i.test(r.market||"")).slice(-9);
  const pick=(sel)=>{const rows=oneX.filter(r=>String(r.selection||"").toLowerCase().includes(sel)).slice(-1)[0];return rows?rows.odds:null};
  return {
    schema:PARAMS.analystSchema||"cornerai-analyst-1",
    version:VERSION,
    ts:Date.now(),
    fixture:{
      id:s.fixtureId||null,
      league:s.league||s.competition||null,
      home:s.home||null,
      away:s.away||null,
      minute:(()=>{const e=effectiveLiveMinute();return e!=null?e:(s.minute??null);})(),
      extra:s.extraMinute||0,
      period:Number.isFinite(clockMin)?(clockMin>45?2:1):null,
      score:[s.score?.home??null,s.score?.away??null],
      red:[s.stats?.red?.home??null,s.stats?.red?.away??null],
      yellow:[s.stats?.yellow?.home??null,s.stats?.yellow?.away??null],
      status:s.liveStatus||"unknown"
    },
    pressure:{
      dangerous:[s.stats?.dangerous?.home??null,s.stats?.dangerous?.away??null],
      attacks:[s.stats?.attacks?.home??null,s.stats?.attacks?.away??null],
      shotsOn:[s.stats?.shotsOn?.home??null,s.stats?.shotsOn?.away??null],
      shotsOff:[s.stats?.shotsOff?.home??null,s.stats?.shotsOff?.away??null],
      shots:[s.stats?.shots?.home??null,s.stats?.shots?.away??null],
      possession:[s.stats?.possession?.home??null,s.stats?.possession?.away??null],
      xg:[s.stats?.xg?.home??null,s.stats?.xg?.away??null],
      bars,
      momentum:[s.intelligence?.momentum?.home??0,s.intelligence?.momentum?.away??0]
    },
    corners:{
      total:[s.stats?.corners?.home??null,s.stats?.corners?.away??null],
      events:corners,
      count:corners.length
    },
    odds:{
      corners:Object.values(ouMap),
      "1x2":{home:pick("1"),draw:pick("x"),away:pick("2")},
      count:Number(s.oddsHistory?.length||0)
    },
    quality:integrity
  };
}


function analystPublishable(analyst){
  if(!analyst||analyst.schema!==(PARAMS.analystSchema||"cornerai-analyst-1")) return {ok:false,reason:"schema"};
  const f=analyst.fixture||{};
  if(!f.id||!f.home||!f.away) return {ok:false,reason:"fixture"};
  if(f.minute==null||!Number.isFinite(Number(f.minute))) return {ok:false,reason:"clock"};
  const q=analyst.quality||{};
  // Bridge auto: qualidade mínima mais permissiva (30) para não travar envio
  const minQ=Math.min(30, Number(PARAMS.analystMinQuality||50));
  if(Number(q.score||0)<minQ && Number(q.score||0)>0) return {ok:false,reason:"quality"};
  const maxStale=q.window==="critical"?Number(PARAMS.analystMaxStaleCriticalMs||8000):Number(PARAMS.analystMaxStaleMs||45000);
  if(q.staleMs!=null&&Number(q.staleMs)>maxStale) return {ok:false,reason:"stale"};
  if(f.status==="live"){
    const d=analyst.pressure?.dangerous;
    const cnr=analyst.corners?.total;
    const hasPressure=Array.isArray(d)&&(d[0]!=null||d[1]!=null);
    const hasCorners=Array.isArray(cnr)&&(cnr[0]!=null||cnr[1]!=null);
    // permite envio se tiver fixture+clock mesmo sem pressure (bridge decide)
    if(!hasPressure&&!hasCorners&&Number(f.minute||0)<1) return {ok:false,reason:"empty-metrics"};
  }
  if(q.failed&&Array.isArray(q.failed)){
    if(q.failed.includes("no-future-events")) return {ok:false,reason:"future-events"};
    if(q.failed.includes("corners-stats-events")&&q.corners?.inflated) return {ok:false,reason:"corners-inflated"};
  }
  if(q.integrityScore!=null&&Number(q.integrityScore)<25) return {ok:false,reason:"integrity"};
  return {ok:true};
}
const EVENTOS_FLASK_DEFAULT="http://127.0.0.1:5000/api/eventos";
let __eventosFlaskUrl = EVENTOS_FLASK_DEFAULT;
// Endpoint Flask legado/opcional: o fluxo oficial usa Bridge :8080 + Engine :8765.
let __eventosFlaskEnabled = false;
let __eventosLastSentAt = 0;
let __eventosLastOk = null;
let __eventosLastError = null;
let __eventosSent = 0;
let __eventosFailed = 0;
let __eventosLastLatencyMs = 0;
let __eventosLastPayloadSummary = null;
let __eventosHistory = []; // ring buffer last 20 sends
const EVENTOS_TELEMETRY_URL = "http://127.0.0.1:5000/api/telemetry/diag";
const EVENTOS_HISTORY_MAX = 20;

function summarizeEventosPayload(body){
  try{
    const d = body && body.dados ? body.dados : (body || {});
    const stats = d.stats || d.estatisticas || {};
    const corners = stats.corners || stats.escanteios || {};
    const danger = stats.dangerousAttacks || stats.ataquesPerigosos || {};
    return {
      fixtureId: d.fixtureId || d.fixture || null,
      home: d.home || d.mandante || null,
      away: d.away || d.visitante || null,
      minute: d.minute != null ? d.minute : d.minuto,
      score: d.score || d.placar || null,
      corners: { home: Number(corners.home)||0, away: Number(corners.away)||0 },
      dangerous: { home: Number(danger.home)||0, away: Number(danger.away)||0 },
      schema: body && body.schema || null,
      payloadBytes: 0
    };
  }catch(e){
    return { error: String(e && e.message || e) };
  }
}

function recordEventosTelemetry(entry){
  __eventosHistory.push(entry);
  if(__eventosHistory.length > EVENTOS_HISTORY_MAX){
    __eventosHistory = __eventosHistory.slice(-EVENTOS_HISTORY_MAX);
  }
  // fire-and-forget para endpoint de diagnóstico (não bloqueia o pipeline principal)
  try{
    const ctrl = typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(2500) : undefined;
    fetch(EVENTOS_TELEMETRY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CornerAI": VERSION, "X-CornerAI-Schema": "cornerai-telemetry-diag-1" },
      body: JSON.stringify({ schema: "cornerai-telemetry-diag-1", source: "cornerai-extension", entry }),
      signal: ctrl
    }).catch(()=>{});
  }catch{}
}

function getEventosDiagSnapshot(){
  return {
    enabled: !!__eventosFlaskEnabled,
    url: __eventosFlaskUrl || EVENTOS_FLASK_DEFAULT,
    telemetryUrl: EVENTOS_TELEMETRY_URL,
    sent: __eventosSent,
    failed: __eventosFailed,
    lastOk: __eventosLastOk,
    lastError: __eventosLastError,
    lastLatencyMs: __eventosLastLatencyMs,
    lastSentAt: __eventosLastSentAt || null,
    lastPayload: __eventosLastPayloadSummary,
    history: __eventosHistory.slice(-12)
  };
}

function buildEventosPayload(){
  const st = state || {};
  const stats = st.stats || {};
  const pair = (k) => {
    const v = stats[k];
    if (v && typeof v === "object") {
      return { home: Number(v.home) || 0, away: Number(v.away) || 0 };
    }
    return { home: 0, away: 0 };
  };
  let geminiPack = null;
  try {
    if (typeof CornerAIGeminiConnector !== "undefined" && CornerAIGeminiConnector.prepareFromState) {
      geminiPack = CornerAIGeminiConnector.prepareFromState(st);
    }
  } catch (e) {}

  const dangerous = pair("dangerous");
  if (!dangerous.home && !dangerous.away) {
    const d = stats.dangerousAttacks;
    if (d && typeof d === "object") {
      dangerous.home = Number(d.home) || 0;
      dangerous.away = Number(d.away) || 0;
    }
  }

  // Objeto completo da partida (tudo que o dashboard usa)
  const dados = {
    fixtureId: st.fixtureId || null,
    fixture: st.fixtureId || null,
    url: st.url || null,
    mandante: st.home || null,
    visitante: st.away || null,
    home: st.home || null,
    away: st.away || null,
    minuto: st.minute,
    minute: st.minute,
    extraMinute: st.extraMinute || 0,
    clock: st.minute != null
      ? (String(st.minute) + (st.extraMinute ? "+" + st.extraMinute : "") + "'")
      : null,
    liveStatus: st.liveStatus || "inactive",
    dataMode: st.dataMode || null,
    placar: {
      home: Number(st.score && st.score.home) || 0,
      away: Number(st.score && st.score.away) || 0
    },
    score: {
      home: Number(st.score && st.score.home) || 0,
      away: Number(st.score && st.score.away) || 0
    },
    estatisticas: {
      escanteios: pair("corners"),
      ataquesPerigosos: dangerous,
      ataques: pair("attacks"),
      finalizacoes: pair("shots"),
      noAlvo: pair("shotsOn"),
      fora: pair("shotsOff"),
      xG: pair("xg"),
      posse: pair("possession"),
      faltas: pair("fouls"),
      impedimentos: pair("offsides"),
      amarelos: pair("yellow"),
      vermelhos: pair("red"),
      substituicoes: pair("subs"),
      cruzamentos: pair("crosses"),
      defesas: pair("saves"),
      passes: pair("passes"),
      passesErrados: pair("passesFailed")
    },
    stats: {
      corners: pair("corners"),
      dangerousAttacks: dangerous,
      attacks: pair("attacks"),
      shots: pair("shots"),
      shotsOn: pair("shotsOn"),
      shotsOff: pair("shotsOff"),
      xg: pair("xg"),
      possession: pair("possession"),
      fouls: pair("fouls"),
      offsides: pair("offsides"),
      yellow: pair("yellow"),
      red: pair("red"),
      subs: pair("subs"),
      crosses: pair("crosses"),
      saves: pair("saves"),
      passes: pair("passes"),
      passesFailed: pair("passesFailed")
    },
    cantos: {
      stats: pair("corners"),
      eventos: Array.isArray(st.cornerEvents) ? st.cornerEvents.slice(-40) : [],
      count: Number(st.cornerEventCount || (st.cornerEvents && st.cornerEvents.length) || 0)
    },
    cornerEvents: Array.isArray(st.cornerEvents) ? st.cornerEvents.slice(-40) : [],
    matchEvents: Array.isArray(st.matchEvents) ? st.matchEvents.slice(-80) : [],
    eventos: Array.isArray(st.matchEvents) ? st.matchEvents.slice(-80) : [],
    snapshotCount: Number(st.snapshotCount || 0),
    eventCount: Number(st.eventCount || (st.matchEvents && st.matchEvents.length) || 0),
    quality: st.diagnostics && st.diagnostics.qualityScore != null
      ? st.diagnostics.qualityScore
      : (st.qualityScore != null ? st.qualityScore : null),
    readiness: st.diagnostics && st.diagnostics.readinessScore != null
      ? st.diagnostics.readinessScore
      : null,
    integrity: st.integrity || null,
    intelligence: st.intelligence || null,
    momentum: st.momentum || null,
    pressure: st.pressure || (st.charts && st.charts.pressure) || null,
    h2h: st.h2h
      ? {
          captured: !!st.h2h.captured,
          summary: st.h2h.summary || null,
          averages: st.h2h.averages || null
        }
      : null,
    oddsMarkets: st.oddsMarkets || null,
    gemini: geminiPack || null,
    version: st.version || VERSION,
    ts: Date.now()
  };

  // Envelope exigido pelo backend Flask: coluna/chave "dados"
  return {
    dados: dados,
    // espelhos legados (não substitui dados)
    data: dados,
    source: "cornerai-extension",
    schema: "cornerai-eventos-dados-1",
    version: VERSION,
    ts: Date.now()
  };
}

async function postEventosFlask(force){
  if(!__eventosFlaskEnabled) return {ok:false, error:"disabled"};
  const url = __eventosFlaskUrl || EVENTOS_FLASK_DEFAULT;
  const now = Date.now();
  if(!force && now - __eventosLastSentAt < 3000) return {ok:false, error:"rate_limit", skipped:true};
  const body = buildEventosPayload();
  // Segurança: nunca enviar só uma métrica isolada
  if (!body || !body.dados || !body.dados.fixtureId && !body.dados.home && body.dados.minute == null) {
    // ainda envia se houver qualquer stats
    if (!body || !body.dados || !body.dados.stats) {
      return {ok:false, error:"payload_vazio_ou_incompleto"};
    }
  }
  const summary = summarizeEventosPayload(body);
  try{
    const rawBody = JSON.stringify(body);
    summary.payloadBytes = rawBody.length;
  }catch{ summary.payloadBytes = 0; }
  const t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
  try{
    const ctrl = typeof AbortSignal!=="undefined" && AbortSignal.timeout ? AbortSignal.timeout(5000) : undefined;
    let authHeaders = {
      "Content-Type": "application/json",
      "X-CornerAI": VERSION,
      "X-CornerAI-Schema": "cornerai-eventos-dados-1"
    };
    try {
      const sk = await chrome.storage.local.get(["cornerai_durable_api_key","cornerai_gemini","cornerai_eventos_jwt"]);
      // Se CORNERAI_REQUIRE_JWT=1 no server, use token de /api/auth/token salvo em cornerai_eventos_jwt
      if (sk.cornerai_eventos_jwt) authHeaders["Authorization"] = "Bearer " + sk.cornerai_eventos_jwt;
    } catch {}
    const res = await fetch(url, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify(body),
      signal: ctrl
    });
    const t1 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    const latencyMs = Math.round(t1 - t0);
    __eventosLastSentAt = now;
    __eventosLastLatencyMs = latencyMs;
    __eventosLastPayloadSummary = summary;
    if(!res.ok){
      __eventosFailed++;
      __eventosLastError = "HTTP "+res.status;
      __eventosLastOk = false;
      recordEventosTelemetry({
        ts: now, ok: false, latencyMs, status: res.status, error: __eventosLastError,
        url, force: !!force, ...summary
      });
      return {ok:false, error:__eventosLastError, status:res.status, url, latencyMs, payloadSummary: summary};
    }
    __eventosSent++;
    __eventosLastOk = true;
    __eventosLastError = null;
    let data = null;
    try{ data = await res.json(); }catch{}
    recordEventosTelemetry({
      ts: now, ok: true, latencyMs, status: res.status, error: null,
      url, force: !!force, ...summary
    });
    console.log("[CornerAI] POST /api/eventos OK →", url, "fixture=", body.dados && body.dados.fixtureId, "latency=", latencyMs+"ms", "keys=", body.dados && Object.keys(body.dados).length);
    return {ok:true, url, sent:__eventosSent, response:data, payload:body, latencyMs, payloadSummary: summary};
  }catch(e){
    const t1 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    const latencyMs = Math.round(t1 - t0);
    __eventosFailed++;
    __eventosLastOk = false;
    __eventosLastError = e?.message || String(e);
    __eventosLastLatencyMs = latencyMs;
    __eventosLastPayloadSummary = summary;
    recordEventosTelemetry({
      ts: now, ok: false, latencyMs, status: null, error: __eventosLastError,
      url, force: !!force, ...summary
    });
    return {ok:false, error:__eventosLastError, url, latencyMs, payloadSummary: summary};
  }
}

async function loadWebhookConfig(){
  try{
    const BRIDGE_DEFAULT="http://127.0.0.1:8080/api/cornerai/feed";
    state.webhook=state.webhook||{url:null,lastOkAt:0,lastError:null,sent:0,failed:0,dropped:0};
    state.webhook.url=BRIDGE_DEFAULT;
    PARAMS.webhookEnabled=true;
    try{
      await chrome.storage.local.set({
        cornerai_webhook_url:BRIDGE_DEFAULT,
        cornerai_webhook_enabled:true
      });
    }catch{}
  }catch{}
}

function enqueueAnalystOutbox(analyst, reason){
  if(!PARAMS.webhookEnabled) return false;
  const gate=analystPublishable(analyst);
  if(!gate.ok){
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.analystDropped=(state.diagnostics.analystDropped||0)+1;
    state.webhook.dropped=(state.webhook.dropped||0)+1;
    return false;
  }
  const item={
    id:`${analyst.fixture?.id||"x"}-${analyst.ts}-${Math.random().toString(36).slice(2,8)}`,
    reason:reason||"snapshot",
    queuedAt:Date.now(),
    attempts:0,
    payload:analyst
  };
  const box=Array.isArray(state.outbox)?state.outbox:[];
  box.push(item);
  state.outbox=box.slice(-Number(PARAMS.outboxMax||200));
  // fire-and-forget flush
  Promise.resolve().then(()=>flushAnalystOutbox()).catch(()=>{});
  return true;
}
let __flushingOutbox=false;
async function flushAnalystOutbox(){
  if(__flushingOutbox) return {ok:false,busy:true};
  await loadWebhookConfig();
  const url=state.webhook?.url;
  if(!url||!PARAMS.webhookEnabled) return {ok:false,reason:"no-webhook"};
  __flushingOutbox=true;
  let sent=0, failed=0;
  let bridgeOffline=false;
  const wasOffline=!!state.webhook?.bridgeOffline;
  const offlineStartedAt=Number(state.webhook?.offlineSince||0);
  try{
    const box=Array.isArray(state.outbox)?[...state.outbox]:[];
    const remain=[];
    for(const item of box){
      if(!item?.payload) continue;
      try{
        const ctrl=typeof AbortSignal!=="undefined"&&AbortSignal.timeout?AbortSignal.timeout(Number(PARAMS.webhookTimeoutMs||4000)):undefined;
        const res=await fetch(url,{
          method:"POST",
          headers:{"Content-Type":"application/json","X-CornerAI-Schema":item.payload.schema||"cornerai-analyst-1","X-CornerAI-Version":VERSION},
          body:JSON.stringify(item.payload),
          signal:ctrl
        });
        if(!res.ok) throw new Error("HTTP "+res.status);
        sent++;
        state.webhook.sent=(state.webhook.sent||0)+1;
        state.webhook.lastOkAt=Date.now();
        state.webhook.lastError=null;
        bridgeOffline=false;
      }catch(e){
        failed++;
        item.attempts=(item.attempts||0)+1;
        state.webhook.failed=(state.webhook.failed||0)+1;
        const msg=String(e?.message||e).slice(0,200);
        // Classify network/bridge-offline errors more clearly
        const isNet = /Failed to fetch|NetworkError|AbortError|timeout|ECONNREFUSED|fetch failed/i.test(msg);
        if(isNet){
          bridgeOffline=true;
          state.webhook.lastError="BRIDGE_OFFLINE: "+msg;
        } else {
          state.webhook.lastError=msg;
        }
        // Keep items longer when bridge is offline (up to 12 attempts)
        const maxAttempts = isNet ? 12 : 5;
        if(item.attempts < maxAttempts) remain.push(item);
      }
    }
    state.outbox=remain.slice(-Number(PARAMS.outboxMax||200));
    state.webhook.bridgeOffline=!!bridgeOffline;
    state.webhook.pending=state.outbox.length;
    if(bridgeOffline && !wasOffline){
      state.webhook.offlineSince=Date.now();
      try{await notifyHeadless("bridge_offline","CornerAI · Bridge Offline",`Bridge local indisponível. ${state.outbox.length} item(ns) preservado(s) no outbox.`,{priority:2,requireInteraction:true});}catch{}
    } else if(!bridgeOffline && wasOffline){
      state.webhook.lastRecoveryAt=Date.now();
      state.webhook.offlineSince=0;
      try{await notifyHeadless("bridge_recovered","CornerAI · Bridge recuperado",`Bridge online novamente. ${sent} item(ns) sincronizado(s).`,{priority:1});}catch{}
    } else if(bridgeOffline && offlineStartedAt){
      state.webhook.offlineSince=offlineStartedAt;
    }
    if(sent||failed||bridgeOffline!==wasOffline) awaitPersist();
    return {ok:true,sent,failed,pending:state.outbox.length,bridgeOffline,offlineSince:Number(state.webhook.offlineSince||0),lastRecoveryAt:Number(state.webhook.lastRecoveryAt||0)};
  }finally{
    __flushingOutbox=false;
  }
}


function compactTimeline(){
 const h={home:[],away:[]};
 for(const p of (state.statTimeline||[])){ for(const side of ['home','away']) h[side].push({fixtureId:p.fixtureId,period:p.period,minute:p.minute,extraMinute:p.extraMinute||0,timestamp:p.timestamp,score:p.score?.[side]??0,stats:Object.fromEntries(STAT_KEYS.map(k=>[k,p.stats?.[k]?.[side]??null]))}) }
 return h;
}
function normalizeIndicatorPair(key,v){if(!v||typeof v!=="object")return null;let h=finite(v.home)?Number(v.home):null,a=finite(v.away)?Number(v.away):null;if(key==="xg"){if(h!=null&&(h<0||h>PARAMS.maxXGPerTeam))return null;if(a!=null&&(a<0||a>PARAMS.maxXGPerTeam))return null;}return{home:h,away:a};}
function recordCornerIndicatorSnapshot(indicator, minute, extraMinute=0, periodHint=null, source="dom"){
 if(!indicator||typeof indicator!=="object")return false;
 const clock=normalizeClock(minute,extraMinute); if(!clock)return false;
 const key=`${periodHint===1||periodHint===2?periodHint:(clock.minute>45?2:1)}|${clock.minute}|${clock.extraMinute}`;
 const period=periodHint===1||periodHint===2?periodHint:(clock.minute>45?2:1);
 const point={fixtureId:state.fixtureId,minute:clock.minute,extraMinute:clock.extraMinute,period,timestamp:Number(indicator.timestamp)||Date.now(),source,attacks:normalizeIndicatorPair("attacks",indicator.attacks),dangerous:normalizeIndicatorPair("dangerous",indicator.dangerous),shotsOn:normalizeIndicatorPair("shotsOn",indicator.shotsOn),shotsOff:normalizeIndicatorPair("shotsOff",indicator.shotsOff),xg:normalizeIndicatorPair("xg",indicator.xg),possession:normalizeIndicatorPair("possession",indicator.possession),appm:indicator.appm||{},pressure:indicator.pressure||{},performancePoints:Array.isArray(indicator.performancePoints)?indicator.performancePoints.filter(p=>p&&Number.isFinite(Number(p.minute))&&Number(p.minute)>=0&&Number(p.minute)<=130&&Number.isFinite(Number(p.value??p.homeValue??0))).slice(0,PARAMS.performancePointMax):[]};
 if(point.xg&&finite(point.xg.home)&&finite(point.xg.away)){
   const conf=source==="network"?.98:source==="hook"?.94:.84;
   const cur=state.xgProvenance;
   const incomingZero=Number(point.xg.home)===0&&Number(point.xg.away)===0;
   const curNonZero=cur&&(Number(cur.home)>0||Number(cur.away)>0);
   // Never let a zero indicator wipe a previously confirmed non-zero xG.
   if(incomingZero&&curNonZero){
     state.diagnostics.rejectedStats=(state.diagnostics.rejectedStats||0)+1;
   } else {
     const age=Date.now()-Number(cur?.updatedAt||0);
     const betterConf=conf>Number(cur?.confidence||0)+0.05;
     const sameOrBetterSource=!cur || conf>=Number(cur.confidence||0);
     const stale=age>30000;
     // Only overwrite when: no current, strictly better confidence, or truly stale AND non-zero incoming.
     if(!cur || betterConf || (stale&&!incomingZero&&sameOrBetterSource)){
       state.xgProvenance={home:point.xg.home,away:point.xg.away,source,confidence:conf,method:"indicator",candidateCount:0,updatedAt:Date.now()};
       if(state.stats.xg?.home==null||state.stats.xg?.away==null){state.stats.xg={home:point.xg.home,away:point.xg.away};}
     }
   }
 }
 const arr=Array.isArray(state.cornerIndicatorTimeline)?state.cornerIndicatorTimeline:[]; const idx=arr.findIndex(x=>`${x.period}|${x.minute}|${x.extraMinute||0}`===key);
 if(idx>=0){const priority={hook:3,network:3,dom:2}[source]||1,oldPriority={hook:3,network:3,dom:2}[arr[idx].source]||1;if(priority>=oldPriority||point.timestamp>=arr[idx].timestamp)arr[idx]=point;else return false;}else arr.push(point);
 arr.sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||(a.extraMinute-b.extraMinute)); state.cornerIndicatorTimeline=arr.slice(-1500); rebuildChartData(); return true;
}
function snapshotCompleteness(point){let n=0;for(const k of STAT_KEYS){const v=point?.stats?.[k];if(v&&Number.isFinite(Number(v.home))&&Number.isFinite(Number(v.away)))n++}return n;}
function mergeSnapshotPoint(oldPoint,newPoint){if(!oldPoint)return newPoint;const out=clone(oldPoint),priority={hook:3,network:3,dom:2,"dom-text":1},np=priority[newPoint.source]||1,op=priority[oldPoint.source]||1;if(np>op){out.source=newPoint.source;out.timestamp=newPoint.timestamp;state.capture.sourcePriorityWins++;}for(const k of STAT_KEYS){const nv=newPoint.stats?.[k],ov=out.stats?.[k];if(!nv)continue;const h=Number.isFinite(Number(nv.home)),a=Number.isFinite(Number(nv.away));if(!h&&!a)continue;if(!out.stats)out.stats={};out.stats[k]={home:h?Number(nv.home):(ov?.home??null),away:a?Number(nv.away):(ov?.away??null)};}if(newPoint.score&&validScore(newPoint.score))out.score=clone(newPoint.score);
 const oldExt=out.extendedStats&&typeof out.extendedStats==="object"?out.extendedStats:{};
 const newExt=newPoint.extendedStats&&typeof newPoint.extendedStats==="object"?newPoint.extendedStats:{};
 out.extendedStats={...oldExt,...newExt};
 return out;}
function recordStatSnapshot(minute,source,extraMinute=0,periodHint=null){const clock=normalizeClock(minute,extraMinute);if(!clock)return false;const m=clock.minute,extra=clock.extraMinute,period=periodHint===1||periodHint===2?periodHint:(m>45?2:1);const point={fixtureId:state.fixtureId,minute:m,extraMinute:extra,period,timestamp:Date.now(),source,score:clone(state.score),stats:clone(state.stats),extendedStats:clone(state.extendedStats),isSnapshot:true,isDerived:false,observedAt:Date.now(),schemaVersion:VERSION};const arr=Array.isArray(state.statTimeline)?state.statTimeline:[],key=`${period}|${m}|${extra}`,idx=arr.findIndex(x=>`${x.period}|${x.minute}|${x.extraMinute||0}`===key);let changed=false;if(idx>=0){const before=JSON.stringify(arr[idx]);const merged=mergeSnapshotPoint(arr[idx],point);if(JSON.stringify(merged)!==before){arr[idx]=merged;changed=true}else state.capture.duplicateSnapshots++;}else{arr.push(point);state.capture.acceptedSnapshots++;changed=true;}arr.sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||(a.timestamp-b.timestamp));state.statTimeline=arr.slice(-PARAMS.maxMinuteSnapshots);state.capture.minuteKeys=[...new Set(state.statTimeline.map(x=>`${x.period}|${x.minute}|${x.extraMinute||0}`))].slice(-PARAMS.maxMinuteSnapshots);state.statChangeEvents=buildStatChangeEvents(state.statTimeline);rebuildMetricEvents();state.teamHistory=compactTimeline();rebuildChartData();rebuildQuality();state.aiFeed=buildAIFeed();state.analyst=buildAnalystFeed();
  try{
    const pred=buildPredictivePayload();
    state.predictivePayload=pred;
    // Prioridade máxima: enfileira payload limpo para o banco preditivo
    if(PARAMS.webhookEnabled && state.webhook?.url){
      const entry={id:`pred-${pred.match_identity.match_id}-${pred.match_identity.timestamp_ms}`,type:"predictive",payload:pred,attempts:0,created_at:Date.now()};
      state.outbox=Array.isArray(state.outbox)?state.outbox:[];
      state.outbox.push(entry);
      if(state.outbox.length>PARAMS.outboxMax) state.outbox=state.outbox.slice(-PARAMS.outboxMax);
    }
  }catch(e){addError("predictive-build:"+e.message)}
  enqueueAnalystOutbox(state.analyst,"state-update");return changed;}

function buildStatChangeEvents(history){
 const out=[];let prev=null;
 const sorted=(history||[]).slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||(a.timestamp-b.timestamp));
 for(const p of sorted){
   for(const k of STAT_KEYS){
     const h=Number(p.stats?.[k]?.home??0),a=Number(p.stats?.[k]?.away??0);
     const ph=Number(prev?.stats?.[k]?.home??h),pa=Number(prev?.stats?.[k]?.away??a);
     const dh=h-ph,da=a-pa;
     if(dh!==0)out.push({fixtureId:p.fixtureId,period:p.period,minute:p.minute,extraMinute:p.extraMinute||0,side:"home",team:state.home,metric:k,from:ph,to:h,delta:dh,source:p.source,timestamp:p.timestamp,eventId:`${p.fixtureId||"unknown"}|metric|${p.period}|${p.minute}|${p.extraMinute||0}|home|${k}|${h}`});
     if(da!==0)out.push({fixtureId:p.fixtureId,period:p.period,minute:p.minute,extraMinute:p.extraMinute||0,side:"away",team:state.away,metric:k,from:pa,to:a,delta:da,source:p.source,timestamp:p.timestamp,eventId:`${p.fixtureId||"unknown"}|metric|${p.period}|${p.minute}|${p.extraMinute||0}|away|${k}|${a}`});
   }
   prev=p;
 }
 return out.slice(-5000);
}


function effectiveLiveMinute(){
  const raw=Number(state.minute);
  const clock=Number.isFinite(raw)?raw:null;
  const events=Array.isArray(state.matchEvents)?state.matchEvents:[];
  const eventMins=events.map(e=>Number(e.minute)).filter(m=>Number.isFinite(m)&&m>=0&&m<=130);
  const maxEvent=eventMins.length?Math.max(...eventMins):null;
  const obs=(state.capture?.observedMinutes||[]).map(Number).filter(Number.isFinite);
  const maxObs=obs.length?Math.max(...obs):null;
  const floor=Math.max(maxEvent||0, maxObs||0);

  if(String(state.liveStatus||"")!=="live"){
    return clock??maxEvent??maxObs??null;
  }

  state.diagnostics=state.diagnostics||{};

  // DOM sem relógio ou 0' com jogo já em andamento
  if(clock==null||clock===0){
    if(floor>=5){
      state.diagnostics.clockStale=true;
      state.diagnostics.clockCorrectedFrom=clock;
      state.diagnostics.clockCorrectedTo=floor;
      return floor;
    }
    return clock;
  }

  // Relógio atrasado vs eventos/observed
  if(floor>clock+5){
    const ahead=eventMins.filter(m=>m>clock+5);
    if(ahead.length>=2||(maxObs!=null&&maxObs>clock+5)){
      state.diagnostics.clockStale=true;
      state.diagnostics.clockCorrectedFrom=clock;
      state.diagnostics.clockCorrectedTo=floor;
      return floor;
    }
  }

  state.diagnostics.clockStale=false;
  return clock;
}
function eventWithinClock(e){
  if(typeof CornerAILib!=="undefined"&&CornerAILib.eventWithinClock){
    return CornerAILib.eventWithinClock(e, state.liveStatus, effectiveLiveMinute());
  }
  if(String(state.liveStatus||"")!=="live") return true;
  const clock=effectiveLiveMinute();
  if(!Number.isFinite(clock)) return true;
  const m=Number(e.minute);
  if(!Number.isFinite(m)) return true;
  if(m > clock + 2) return false;
  if(m > 130) return false;
  return true;
}

function pruneFutureEvents(){
  if(String(state.liveStatus||"")!=="live") return 0;
  const before=state.matchEvents?.length||0;
  state.matchEvents=(state.matchEvents||[]).filter(eventWithinClock);
  state.cornerEvents=(state.cornerEvents||[]).filter(e=>eventWithinClock({...e,type:"corner"}));
  return before-(state.matchEvents?.length||0);
}
const __eventDebounce=new Map(); // signature -> lastTs

function reconcileCornerEvents(){
  // Alinha eventos de canto aos stats oficiais — evita inflação / contaminação entre jogos
  // MAXIMIZE: tolera lag de 1-2 eventos (comum quando stats atualizam antes do feed de eventos)
  const sh=Number(state.stats?.corners?.home);
  const sa=Number(state.stats?.corners?.away);
  if(!Number.isFinite(sh)||!Number.isFinite(sa)) return;
  let events=Array.isArray(state.cornerEvents)?[...state.cornerEvents]:[];
  // Re-hidratação agressiva a partir de matchEvents + unifiedTimeline
  if(events.length < (sh+sa) && (sh>0||sa>0)){
    const fromMatch=(state.matchEvents||[]).filter(e=>{
      const t=String(e.type||"").toLowerCase();
      return t==="corner"||t==="escanteio"||t.includes("corner")||t.includes("escanteio");
    }).map(e=>({
      side: e.side||null,
      minute: e.minute,
      extraMinute: e.extraMinute||0,
      period: e.period||(e.minute>=46?2:1),
      teamName: e.teamName||e.team||"",
      eventId: e.eventId||`${e.side}|${e.minute}|${e.extraMinute||0}`,
      source: e.source||"rehydrated",
      confidence: e.confidence||0.6
    }));
    const fromUnified=(state.unifiedTimeline||[]).filter(e=>{
      const t=String(e.type||e.kind||"").toLowerCase();
      return t==="corner"||t==="escanteio"||t.includes("corner");
    }).map(e=>({
      side: e.side||null,
      minute: e.minute,
      extraMinute: e.extraMinute||0,
      period: e.period||(e.minute>=46?2:1),
      teamName: e.teamName||e.team||"",
      eventId: e.eventId||`${e.side}|${e.minute}|${e.extraMinute||0}`,
      source: e.source||"unified-rehydrated",
      confidence: 0.55
    }));
    const combined=[...events,...fromMatch,...fromUnified];
    if(combined.length) events=combined;
  }
  // descarta times que não são home/away atuais
  const home=String(state.home||"").toLowerCase();
  const away=String(state.away||"").toLowerCase();
  if(home&&away){
    events=events.filter(e=>{
      const t=String(e.teamName||e.team||"").toLowerCase();
      if(!t) return true;
      return t===home||t===away||t.includes(home.slice(0,8))||t.includes(away.slice(0,8));
    });
  }
  // dedupe minuto+extra+side
  const seen=new Set();
  events=events.filter(e=>{
    const k=`${e.side||"?"}|${e.minute}|${e.extraMinute||0}`;
    if(seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  events.sort((a,b)=>(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||String(a.side).localeCompare(String(b.side)));
  const bySide={home:events.filter(e=>e.side==="home"),away:events.filter(e=>e.side==="away"),unk:events.filter(e=>e.side!=="home"&&e.side!=="away")};
  // se inflado, mantém os primeiros N por lado (cronológicos) = stats
  // MAXIMIZE: permite lag de até +1 evento (stats podem liderar por 1)
  const lagTol=1;
  const trim=(arr,n)=>arr.length>n+lagTol?arr.slice(0,n+lagTol):arr;
  let homeE=trim(bySide.home,sh);
  let awayE=trim(bySide.away,sa);
  // se ainda faltam eventos e temos unk, tenta alocar por proximidade de minuto
  if(bySide.unk.length && (homeE.length<sh || awayE.length<sa)){
    for(const u of bySide.unk){
      if(homeE.length<sh){ homeE.push({...u,side:"home"}); continue; }
      if(awayE.length<sa){ awayE.push({...u,side:"away"}); }
    }
    homeE=trim(homeE,sh);
    awayE=trim(awayE,sa);
  }
  const merged=[...homeE,...awayE].sort((a,b)=>(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0)));
  const before=state.cornerEvents?.length||0;
  state.cornerEvents=merged;
  state.cornerEventCount=merged.length;
  // remove corners inflados do matchEvents
  const keep=new Set(merged.map(e=>e.eventId||`${e.side}|${e.minute}|${e.extraMinute||0}`));
  state.matchEvents=(state.matchEvents||[]).filter(e=>{
    if(e.type!=="corner"&&e.type!=="escanteio") return true;
    const id=e.eventId||`${e.side}|${e.minute}|${e.extraMinute||0}`;
    return keep.has(id)||keep.has(`${e.side}|${e.minute}|${e.extraMinute||0}`);
  });
  if(before!==merged.length){
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.cornersReconciled=(state.diagnostics.cornersReconciled||0)+1;
    state.diagnostics.cornersPruned=before-merged.length;
  }
}

function mergeEvents(events,source){
 if(!Array.isArray(events))return 0;let added=0;
 const now=Date.now();
 for(const raw of events){
   const e=normalizeMatchEvent(raw,source);
   if(!e){state.diagnostics.rejectedEvents++;continue}
   if(e.fixtureId&&state.fixtureId&&String(e.fixtureId)!==String(state.fixtureId)){state.diagnostics.rejectedEvents++;continue}
   if(!eventWithinClock(e)){state.diagnostics.rejectedEvents++;state.diagnostics.futureEventsRejected=(state.diagnostics.futureEventsRejected||0)+1;continue}
   // debounce 1.2s por assinatura (evita rajadas DOM)
   const sig=String(e.eventId||e.signature||`${e.type}|${e.minute}|${e.side}|${e.label||""}`);
   const prev=__eventDebounce.get(sig);
   if(prev&&now-prev<1200){state.diagnostics.debouncedEvents=(state.diagnostics.debouncedEvents||0)+1;continue}
   __eventDebounce.set(sig,now);
   if(__eventDebounce.size>500){
     const cut=now-60000;
     for(const [k,ts] of __eventDebounce){if(ts<cut)__eventDebounce.delete(k)}
   }
   // re-hidratação: resolve side por nome do time se ausente
   if(!e.side&&e.teamName){
     const tn=String(e.teamName).toLowerCase();
     if(state.home&&tn===String(state.home).toLowerCase()) e.side="home";
     else if(state.away&&tn===String(state.away).toLowerCase()) e.side="away";
   }
   if(!e.side&&e.label){
     const lb=String(e.label).toLowerCase();
     const h=state.home?String(state.home).toLowerCase():"";
     const a=state.away?String(state.away).toLowerCase():"";
     if(h&&lb.includes(h)) e.side="home";
     else if(a&&lb.includes(a)) e.side="away";
   }
   // contaminação: label cita time que não é desta partida
   if(e.teamName){
     const tn=String(e.teamName).toLowerCase();
     const h=state.home?String(state.home).toLowerCase():"";
     const a=state.away?String(state.away).toLowerCase():"";
     if(h&&a&&tn&&tn!==h&&tn!==a&&!h.includes(tn.slice(0,6))&&!a.includes(tn.slice(0,6))&&!tn.includes(h.slice(0,6))&&!tn.includes(a.slice(0,6))){
       state.diagnostics.rejectedEvents++;
       state.diagnostics.crossFixtureRejects=(state.diagnostics.crossFixtureRejects||0)+1;
       continue;
     }
   }
   const dupIdx=state.matchEvents.findIndex(x=>x.eventId===e.eventId||x.signature===e.signature);
   if(dupIdx>=0){
   state.diagnostics.duplicateEventDetections++;
   state.capture=state.capture||{};
   state.capture.duplicateSignatureCounts=state.capture.duplicateSignatureCounts||{};
   const dk=String(e.eventId||e.signature||"unknown");
   state.capture.duplicateSignatureCounts[dk]=Number(state.capture.duplicateSignatureCounts[dk]||0)+1;
   if(state.capture.duplicateSignatureCounts[dk]===1) state.diagnostics.duplicateEvents++;
   // Precedência: se a nova observação tem fonte maior, atualiza source/confidence (imuta identidade)
   const prev=state.matchEvents[dupIdx];
   if(sourcePriority(source)>sourcePriority(prev.source||"dom-text")){
     state.matchEvents[dupIdx]={...prev, source, confidence:Math.max(Number(prev.confidence)||0, Number(e.confidence)||0), timestamp:e.timestamp||prev.timestamp};
     if(e.playerName && !prev.playerName) state.matchEvents[dupIdx].playerName=e.playerName;
     if(e.playerId && !prev.playerId) state.matchEvents[dupIdx].playerId=e.playerId;
     state.capture.sourcePriorityWins=(state.capture.sourcePriorityWins||0)+1;
   }
   continue
}
   stampEventAbsolute(e);state.matchEvents.push(e); added++;
   if(e.type==='corner') stampEventAbsolute(e);state.cornerEvents.push(e);
   state.diagnostics.lastEventAt=Date.now();
 }
 if(added){
   state.matchEvents.sort(eventOrder);
   state.cornerEvents=state.matchEvents.filter(e=>e.type==='corner').sort(eventOrder);
   state.cornerEventCount=state.cornerEvents.length;
   try{mergePlayersFromState();}catch{}

   state.eventCount=state.matchEvents.length;
   rebuildUnifiedTimeline();
 }
 rebuildTeamData();
 return added;
}
function rebuildUnifiedTimeline(){
 const events=(state.matchEvents||[]).slice().sort(eventOrder);
 const timeline=[];
 for(const e of events) timeline.push({kind:'event',eventId:e.eventId,fixtureId:e.fixtureId,period:e.period,minute:e.minute,extraMinute:e.extraMinute||0,side:e.side,team:e.team,type:e.type,label:e.label||'',source:e.source,confidence:e.confidence,timestamp:e.timestamp});
 for(const e of (state.metricEvents||[])) timeline.push({kind:'metric',eventId:e.eventId,fixtureId:e.fixtureId,period:e.period,minute:e.minute,extraMinute:e.extraMinute||0,side:e.side,team:e.team,type:'metric',metric:e.metric,from:e.from,to:e.to,delta:e.delta,source:e.source,confidence:1,timestamp:e.timestamp});
 timeline.sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||((a.kind==='metric'?1:0)-(b.kind==='metric'?1:0))||((a.timestamp||0)-(b.timestamp||0)));
 state.unifiedTimeline=timeline.slice(-10000);
 const pressure={home:{},away:{}};
 const byType={home:{},away:{}};
 for(const e of state.unifiedTimeline){if(e.kind!=='event')continue;const side=e.side==='away'?'away':'home';byType[side][e.type]=(byType[side][e.type]||0)+1}
 const corners=events.filter(e=>e.type==='corner');
 const contexts=corners.map(c=>{const base=(state.unifiedTimeline||[]).filter(x=>x.kind==='event'&&x.eventId!==c.eventId&&x.period===c.period);const prior=base.filter(x=>eventOrder(x,c)<=0&&((c.minute-x.minute)*60+(c.extraMinute||0)-(x.extraMinute||0))<=600);const metricBefore=(state.statTimeline||[]).filter(p=>p.period===c.period&&((p.minute<c.minute)|| (p.minute===c.minute&&(p.extraMinute||0)<=(c.extraMinute||0)))).slice(-1)[0]||null;const counts={};for(const e of prior){const k=e.type;counts[k]=(counts[k]||0)+1}return{cornerEventId:c.eventId,minute:c.minute,extraMinute:c.extraMinute||0,period:c.period,side:c.side,team:c.team,prior10m:counts,precedingEvents:prior.slice(-20),nearestSnapshot:metricBefore?{minute:metricBefore.minute,extraMinute:metricBefore.extraMinute||0,stats:metricBefore.stats}:null}});
 state.cornerContexts=contexts;
 state.eventSummary={byTeam:{home:{team:state.home,counts:byType.home},away:{team:state.away,counts:byType.away}},total:state.unifiedTimeline.length};
 state.chartData=state.chartData||{};state.chartData.cornerContexts=contexts;state.chartData.unifiedTimeline=state.unifiedTimeline;state.chartData.eventSummary=state.eventSummary;
}


const UI_NOISE_RE=/jogador da partida|melhores desempenhos|classifica[cç][aã]o|ver tabela|oddsao vivo|play with responsibility|fora do jogo|informa[cç][oõ]es do tempo|canais de tv|menor probabilidade|maior probabilidade/i;
const HIST_ODDS_RE=/\b\d{1,3}(?:\+\d{1,2})?['′]\s*(?:\d+(?:[.,]\d+)?[=|]?\s*){2,}/i;
function cleanField(v,max=180){return String(v??"").replace(/\s+/g," ").trim().slice(0,max)}
function isContaminatedOddsText(market,selection){const blob=`${market} ${selection}`;if(UI_NOISE_RE.test(blob))return true;if(HIST_ODDS_RE.test(blob))return true;const decimals=(blob.match(/\d+(?:[.,]\d+)?/g)||[]);if(decimals.length>4)return true;return /(?:\d+[=|]){3,}/.test(blob)}
function confidenceForQuote(q,source,market,selection){let c=source==="network"?.98:source==="hook"?.94:.82;if(market&&selection)c+=.03;if(UI_NOISE_RE.test(`${market} ${selection}`))c-=.8;return Math.max(0,Math.min(1,c))}
function normalizeOddsQuote(q,source,clock){
 if(!q||typeof q!=="object")return null;
 const rawOdd=q.odds??q.odd??q.price??q.quota??q.cotacao;
 const odd=Number(String(rawOdd??"").replace(/,/g,".")); if(!Number.isFinite(odd)||odd<PARAMS.minOdds||odd>PARAMS.maxOdds)return null;
 const minute=normalizeMinute(q.minute??clock?.minute??state.minute); if(minute==null)return null;
 const extra=Math.max(0,Number(q.extraMinute??clock?.extraMinute??0)||0), period=normalizePeriod(q.period,minute,extra);
 const clean=v=>String(v??"").replace(/\s+/g," ").trim();
 const market=cleanField(q.market??q.marketName??"");
 const selection=cleanField(q.selection??q.outcome??q.label??"",120);
 const bookmaker=cleanField(q.bookmaker??q.provider??"",100)||"Mercado";
 // Reject corrupted text captures such as "48'1.40=4=9.50=" and other
 // concatenated historical quote strings. A valid market/selection may contain
 // one line value, but not a chain of minute markers and multiple decimal prices.
 const corrupt=isContaminatedOddsText(market,selection);
 if(corrupt){return null;}
 if(market.length>180||selection.length>120||bookmaker.length>100)return null;
 const marketType=String(q.marketType||(/escante|corner|canto/i.test(market+" "+selection)?"corners":"other")).toLowerCase();
 // Unknown market/selection is raw telemetry, never a valid AI-feed quote.
 if(!market || !selection || /^mercado não identificado$/i.test(market) || /^seleção não identificada$/i.test(selection))return null;
 if(marketType==="other" && !market)return null;
 // Lixo: "Menos de ?", "Mais de ?", linha ausente, mercado genérico vazio
 if(/^(mais|menos)\s*de\s*\??$/i.test(selection)) return null;
 if(/\?/.test(selection)) return null;
 if(/^mercado$/i.test(market) && !/escante|corner|gol|resultado|1x2|total/i.test(selection)) return null;
 const line=q.line==null?null:clean(q.line).replace(",",".");
 if(line!==null && line!=="" && !/^[-+]?\d+(?:\.\d+)?$/.test(line))return null;
 // Escanteios: rejeita odds absurdas (minuto 87/89, linha colada 9.50, linha de gols 2.5)
 if(marketType==="corners"){
   if(odd<1.15||odd>6.5) return null;
   if(line){
     const ln=Number(line);
     if(Number.isFinite(ln)&&(ln<6||ln>14)) return null;
     if(Number.isFinite(ln)&&Math.abs(odd-ln)<0.08) return null;
   }
 }
 let selectionSide=null; const st=selection.toLowerCase(); if(state.home&&st===state.home.toLowerCase())selectionSide="home"; else if(state.away&&st===state.away.toLowerCase())selectionSide="away";
 const implied=1/odd;
 const quoteKey=`${state.fixtureId||q.fixtureId||"unknown"}|${market.toLowerCase()}|${line||""}|${selection.toLowerCase()}|${bookmaker.toLowerCase()}`;
 const recordKey=`${quoteKey}|${period}|${minute}|${extra}|${odd}`;
 const confidence=confidenceForQuote(q,source,market,selection);
 if(confidence<PARAMS.criticalDataConfidence){state.diagnostics.lowConfidence++;return null;}
 return {quoteId:String(q.quoteId||recordKey),quoteKey,recordKey,fixtureId:q.fixtureId?String(q.fixtureId):state.fixtureId,minute,extraMinute:extra,period,matchMinute:minute,market:market||"Mercado não identificado",marketType,selection:selection||"Seleção não identificada",line:line||null,selectionSide,bookmaker,odds:odd,impliedProbability:implied,isLive:true,source,confidence,timestamp:Number(q.timestamp)||Date.now()};
}
function rebuildOddsAnalytics(){
 const rows=Array.isArray(state.oddsHistory)?state.oddsHistory:[];
 const groups=new Map();
 // Agrupa por mercado + linha + bookmaker + fonte (book ≠ fair) + minuto
 for(const r of rows){
   const src=String(r.source||"");
   const isFair=/fair|justa/i.test(r.market||"")||/fair/i.test(src)||/Fair/i.test(r.bookmaker||"");
   const g=`${r.period}|${r.minute}|${r.extraMinute||0}|${r.marketType}|${String(r.market||"").toLowerCase()}|${r.line||""}|${String(r.bookmaker||"").toLowerCase()}|${isFair?"fair":"book"}`;
   (groups.get(g)||groups.set(g,[]).get(g)).push(r);
 }
 for(const list of groups.values()){
   // dedupe por selection: mantém odd mais recente
   const bySel=new Map();
   for(const r of list){
     const k=String(r.selection||"").toLowerCase();
     const prev=bySel.get(k);
     if(!prev||Number(r.timestamp||0)>=Number(prev.timestamp||0)) bySel.set(k,r);
   }
   const unique=[...bySel.values()];
   const sum=unique.reduce((a,r)=>a+(1/Number(r.odds||1)),0);
   // overround só faz sentido em mercados fechados (2–3 seleções)
   const coherent=unique.length>=2&&unique.length<=4&&sum>=0.95&&sum<=1.45;
   const overround=coherent?sum:1;
   for(const r of list){
     r.marketOverround=overround;
     r.fairProbability=coherent?(1/r.odds)/overround:(1/r.odds);
     r.marketProbability=r.fairProbability;
   }
 }
 const markets={}; for(const r of rows){const key=`${r.marketType}|${r.market}|${r.line||""}|${r.bookmaker}`;if(!markets[key])markets[key]={marketType:r.marketType,market:r.market,line:r.line,bookmaker:r.bookmaker,quotes:[],firstMinute:r.minute,lastMinute:r.minute};markets[key].quotes.push({minute:r.minute,extraMinute:r.extraMinute||0,period:r.period,selection:r.selection,selectionSide:r.selectionSide,odds:r.odds,impliedProbability:r.impliedProbability,fairProbability:r.fairProbability??null,marketOverround:r.marketOverround??null,timestamp:r.timestamp}) ;markets[key].lastMinute=r.minute}
 state.oddsMarkets=markets;
 const corners=rows.filter(r=>r.marketType==="corners");
 state.marketExpectations=corners.slice(-3000).map(r=>({minute:r.minute,extraMinute:r.extraMinute||0,period:r.period,market:r.market,line:r.line,selection:r.selection,selectionSide:r.selectionSide,odds:r.odds,rawProbability:r.impliedProbability,fairProbability:r.fairProbability??null,overround:r.marketOverround??null,bookmaker:r.bookmaker,source:r.source,timestamp:r.timestamp}));
 state.chartData=state.chartData||{};state.chartData.oddsHistory=rows.slice(-5000);state.chartData.cornerOdds=state.marketExpectations;
}
function recordOdds(quotes,source,clock){
 if(!Array.isArray(quotes)||!quotes.length)return 0;let added=0;
 for(const q of quotes){const n=normalizeOddsQuote(q,source,clock);if(!n){state.diagnostics.oddsRejected++;continue}
   const existing=state.oddsHistory.find(r=>r.quoteKey===n.quoteKey&&r.minute===n.minute&&r.extraMinute===n.extraMinute&&r.odds===n.odds);
   if(existing){state.diagnostics.oddsDuplicates++;continue}
   const prev=state.oddsHistory.filter(r=>r.quoteKey===n.quoteKey).slice(-1)[0];
   if(prev&&prev.odds!==n.odds)state.oddsChanges.push({quoteKey:n.quoteKey,minute:n.minute,extraMinute:n.extraMinute,period:n.period,market:n.market,marketType:n.marketType,line:n.line,selection:n.selection,selectionSide:n.selectionSide,bookmaker:n.bookmaker,from:prev.odds,to:n.odds,delta:n.odds-prev.odds,fromImpliedProbability:1/prev.odds,toImpliedProbability:1/n.odds,timestamp:n.timestamp});
   state.oddsHistory.push(n);added++;
 }
 if(added){state.oddsHistory.sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0))||((a.timestamp||0)-(b.timestamp||0)));state.oddsChanges=state.oddsChanges.slice(-5000);state.diagnostics.oddsQuotes=state.oddsHistory.length;state.diagnostics.oddsChanges=state.oddsChanges.length;state.oddsCount=state.oddsHistory.length;rebuildOddsAnalytics()}
 return added;
}


let __visibleCaptureAt=0;
let __visibleCapturePromise=null;
const VISIBLE_CAPTURE_MIN_INTERVAL=1200;
async function captureVisibleTabThrottled(winId){
  const now=Date.now();
  const wait=VISIBLE_CAPTURE_MIN_INTERVAL-(now-__visibleCaptureAt);
  if(wait>0) await new Promise(r=>setTimeout(r,wait));
  if(__visibleCapturePromise) return __visibleCapturePromise;
  __visibleCaptureAt=Date.now();
  __visibleCapturePromise=(async()=>{
    try{return await chrome.tabs.captureVisibleTab(winId,{format:"jpeg",quality:55});}
    finally{__visibleCapturePromise=null;}
  })();
  return __visibleCapturePromise;
}
const SOURCE_PRIORITY={network:3,hook:3,dom:2,"dom-text":1,selftest:0};
const SOURCE_BASE_CONFIDENCE={network:0.98,hook:0.94,dom:0.84,"dom-text":0.72,selftest:0.5};

function sourcePriority(source){return SOURCE_PRIORITY[source]||1}
function sourceBaseConfidence(source){return SOURCE_BASE_CONFIDENCE[source]||0.75}
function statTolerance(k){
  if(k==="xg") return 0.12;
  if(k==="possession") return 2;
  return 0;
}
function ensureStatProvenance(k){
  if(!state.provenance) state.provenance={stats:{},conflicts:[],sourceCounts:{dom:0,network:0,hook:0,"dom-text":0}};
  if(!state.provenance.stats[k]){
    state.provenance.stats[k]={home:null,away:null};
  }
  return state.provenance.stats[k];
}
function chooseStatValue(k,side,candidate,source,observedAt){
  if(!finite(candidate)) return {accepted:false,value:null};
  const prov=ensureStatProvenance(k);
  const current=prov[side];
  const priority=sourcePriority(source);
  const base=sourceBaseConfidence(source);
  const now=Date.now();
  const candidateConfidence=Math.min(1,base+Math.min(0.05,Math.max(0,(now-observedAt)<=3000?0.05:0)));
  if(!current){
    prov[side]={value:Number(candidate),source,confidence:candidateConfidence,observedAt,updates:1,conflicts:0};
    state.provenance.sourceCounts[source]=(state.provenance.sourceCounts[source]||0)+1;
    return {accepted:true,value:Number(candidate),upgraded:false,conflict:false};
  }

  const oldValue=Number(current.value);
  const delta=Math.abs(oldValue-Number(candidate));
  const conflict=delta>statTolerance(k);
  if(conflict){
    state.diagnostics.statConflicts++;
    current.conflicts=(current.conflicts||0)+1;
    state.provenance.conflicts.unshift({
      metric:k,side,previous:oldValue,incoming:Number(candidate),
      previousSource:current.source,incomingSource:source,
      previousConfidence:current.confidence,incomingConfidence:candidateConfidence,
      delta,at:now
    });
    state.provenance.conflicts=state.provenance.conflicts.slice(0,200);
  }

  const age=now-Number(current.observedAt||0);
  const better = priority>sourcePriority(current.source)
    || (priority===sourcePriority(current.source) && candidateConfidence>=Number(current.confidence||0))
    || age>8000;

  if(!better){
    return {accepted:false,value:oldValue,upgraded:false,conflict};
  }

  const upgraded=sourcePriority(source)>sourcePriority(current.source);
  if(upgraded) state.diagnostics.statSourceUpgrades++;
  prov[side]={value:Number(candidate),source,confidence:candidateConfidence,observedAt,updates:Number(current.updates||0)+1,conflicts:Number(current.conflicts||0)};
  return {accepted:true,value:Number(candidate),upgraded,conflict};
}
function mergeCanonicalStat(k,normalized,source,observedAt){
  if(!normalized) return false;
  const cur=state.stats[k]||emptyPair();
  let changed=false;
  // Guard: both-side zero xG from weak sources must not erase confirmed non-zero xG.
  if(k==="xg"){
    const bothZero=(Number(normalized.home)===0||normalized.home===0)&&(Number(normalized.away)===0||normalized.away===0);
    const curNonZero=(cur.home!=null&&Number(cur.home)>0)||(cur.away!=null&&Number(cur.away)>0);
    if(bothZero&&curNonZero&&source!=="network"&&source!=="hook"){
      state.diagnostics.rejectedStats=(state.diagnostics.rejectedStats||0)+1;
      return false;
    }
  }
  for(const side of ["home","away"]){
    const incoming=normalized[side];
    if(incoming==null) continue;
    const selected=chooseStatValue(k,side,incoming,source,observedAt);
    if(!selected.accepted) continue;
    if(CUMULATIVE.has(k) && cur[side]!=null && Number(incoming)<Number(cur[side])){
      state.diagnostics.staleSnapshots++;
      continue;
    }
    cur[side]=Number(selected.value);
    changed=true;
  }
  state.stats[k]=cur;
  return changed;
}

function metricPairDelta(newer,older,k,side){
  const n=Number(newer?.stats?.[k]?.[side]),o=Number(older?.stats?.[k]?.[side]);
  if(!Number.isFinite(n)||!Number.isFinite(o)) return null;
  return n-o;
}
function pointMinuteValue(p){
  return Number(p?.period||1)*1000+Number(p?.minute||0)+Number(p?.extraMinute||0)/100;
}



// ===== High-precision engine: clock sync, stats validation, situational (v6.5) =====
const PRECISION = {
  clockRegressionThreshold: 2,
  outOfOrderMarginSec: 60,
  stagnationMinutes: 10,
  watermark: 0
};

function nextWatermark(){
  PRECISION.watermark = (PRECISION.watermark||0) + 1;
  return PRECISION.watermark;
}

function stampEventAbsolute(e){
  if(!e||typeof e!=="object") return e;
  if(!e.capturedAt) e.capturedAt = Date.now();
  if(e.perfNow==null){
    try{e.perfNow = (typeof performance!=="undefined" && performance.now)?performance.now():null;}catch{e.perfNow=null;}
  }
  e.wm = e.wm || nextWatermark();
  return e;
}

function detectClockRegression(prevMinute, nextMinute){
  if(!Number.isFinite(prevMinute) || !Number.isFinite(nextMinute)) return null;
  const delta = nextMinute - prevMinute;
  if(delta <= -PRECISION.clockRegressionThreshold){
    return {type:"regression", from:prevMinute, to:nextMinute, delta};
  }
  return null;
}

function reconcileClockRegression(info){
  try{
    state.diagnostics.clockRegressions = (state.diagnostics.clockRegressions||0)+1;
    state.diagnostics.lastClockRegression = {...info, at:Date.now()};
    // Drop future-dated events relative to corrected minute
    const cut = Number(info.to);
    const beforeE = (state.matchEvents||[]).length;
    state.matchEvents = (state.matchEvents||[]).filter(e => eventMinuteValue(e) <= cut + 0.5);
    state.cornerEvents = (state.cornerEvents||[]).filter(e => eventMinuteValue(e) <= cut + 0.5);
    state.diagnostics.clockRegressionDropped = (state.diagnostics.clockRegressionDropped||0) + (beforeE - (state.matchEvents||[]).length);
    // Trim timeline snapshots beyond cut
    if(Array.isArray(state.statTimeline)){
      state.statTimeline = state.statTimeline.filter(p => Number(p.minute||0) <= cut + 1);
    }
    state.minute = cut;
    try{rebuildMetricEvents();}catch{}
    try{rebuildTeamData();}catch{}
    try{state.intelligence=buildIntelligenceFeatures();}catch{}
  }catch(e){try{addError("clock-reconcile: "+(e?.message||e));}catch{}}
}

function reorderOutOfOrderEvents(){
  try{
    const events = Array.isArray(state.matchEvents)?state.matchEvents.slice():[];
    if(events.length<2) return 0;
    // Sort by match minute, then capturedAt
    events.sort((a,b)=>{
      const da=eventMinuteValue(a)-eventMinuteValue(b);
      if(Math.abs(da)>1e-6) return da;
      return Number(a.capturedAt||0)-Number(b.capturedAt||0);
    });
    let anomalies=0;
    const lastSeen = {minute:null, at:null};
    for(const e of events){
      stampEventAbsolute(e);
      const m=eventMinuteValue(e);
      if(lastSeen.minute!=null && m < lastSeen.minute - 0.05){
        const gapSec = lastSeen.at!=null ? Math.abs((e.capturedAt||0)-(lastSeen.at||0))/1000 : 999;
        if(gapSec > PRECISION.outOfOrderMarginSec){
          e.anomaly="out_of_order";
          anomalies++;
        }
      }
      lastSeen.minute=m;
      lastSeen.at=e.capturedAt||Date.now();
    }
    state.matchEvents=events;
    state.diagnostics.outOfOrderAnomalies=(state.diagnostics.outOfOrderAnomalies||0)+anomalies;
    return anomalies;
  }catch{return 0;}
}

// --- Statistical validation ---
function emaUpdate(prev, value, alpha){
  if(!Number.isFinite(value)) return prev;
  if(!Number.isFinite(prev)) return value;
  return alpha*value + (1-alpha)*prev;
}
function iqrClip(series, value){
  const arr=(series||[]).filter(Number.isFinite).slice(-10).sort((a,b)=>a-b);
  if(arr.length<4 || !Number.isFinite(value)) return {value, outlier:false};
  const q1=arr[Math.floor(arr.length*0.25)];
  const q3=arr[Math.floor(arr.length*0.75)];
  const iqr=Math.max(0,q3-q1);
  const lo=q1-1.5*iqr, hi=q3+1.5*iqr;
  if(value<lo || value>hi){
    const med=arr[Math.floor(arr.length/2)];
    return {value:med, outlier:true, lo, hi, median:med};
  }
  return {value, outlier:false};
}
function enforceAttackChain(stats){
  // attacks >= dangerous >= shots >= shotsOn (soft clamp)
  const out=stats&&typeof stats==="object"?{...stats}:{};
  for(const side of ["home","away"]){
    let attacks=Number(out.attacks?.[side]);
    let dangerous=Number(out.dangerous?.[side]);
    let shots=Number(out.shots?.[side]);
    let shotsOn=Number(out.shotsOn?.[side]);
    let shotsOff=Number(out.shotsOff?.[side]);
    if(Number.isFinite(dangerous)&&Number.isFinite(attacks)&&dangerous>attacks) attacks=dangerous;
    if(Number.isFinite(shots)&&Number.isFinite(dangerous)&&shots>dangerous) dangerous=shots;
    if(Number.isFinite(shotsOn)&&Number.isFinite(shots)&&shotsOn>shots) shots=shotsOn;
    if(Number.isFinite(shotsOn)&&Number.isFinite(shotsOff)&&Number.isFinite(shots) && shotsOn+shotsOff>shots+1){
      shots = shotsOn+shotsOff;
    }
    if(Number.isFinite(attacks)) out.attacks={...(out.attacks||{}),[side]:attacks};
    if(Number.isFinite(dangerous)) out.dangerous={...(out.dangerous||{}),[side]:dangerous};
    if(Number.isFinite(shots)) out.shots={...(out.shots||{}),[side]:shots};
    if(Number.isFinite(shotsOn)) out.shotsOn={...(out.shotsOn||{}),[side]:shotsOn};
  }
  // possession normalize if near 100
  const pH=Number(out.possession?.home), pA=Number(out.possession?.away);
  if(Number.isFinite(pH)&&Number.isFinite(pA)){
    const sum=pH+pA;
    if(sum>=98 && sum<=102 && Math.abs(sum-100)>0.05){
      out.possession={home:Number(((pH/sum)*100).toFixed(1)), away:Number(((pA/sum)*100).toFixed(1)), normalized:true};
    }
  }
  return out;
}
function detectStagnation(){
  try{
    const minute=Number(state.minute);
    if(!Number.isFinite(minute) || state.liveStatus!=="live") return null;
    const cornersH=Number(state.stats?.corners?.home);
    const cornersA=Number(state.stats?.corners?.away);
    const lastChange=Number(state.capture?.lastChangedAt||state.lastUpdate||0);
    const ageMin=(Date.now()-lastChange)/60000;
    if(ageMin >= PRECISION.stagnationMinutes && Number.isFinite(cornersH)){
      state.diagnostics.stagnationFlags=(state.diagnostics.stagnationFlags||0)+1;
      return {metric:"corners", ageMin:Number(ageMin.toFixed(2)), suggest:"network-fallback"};
    }
    return null;
  }catch{return null;}
}
function pearson(xs, ys){
  const n=Math.min(xs.length,ys.length);
  if(n<4) return null;
  let sx=0,sy=0,sxx=0,syy=0,sxy=0,c=0;
  for(let i=0;i<n;i++){
    const x=Number(xs[i]), y=Number(ys[i]);
    if(!Number.isFinite(x)||!Number.isFinite(y)) continue;
    sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y; c++;
  }
  if(c<4) return null;
  const num=c*sxy-sx*sy;
  const den=Math.sqrt(Math.max(0,(c*sxx-sx*sx)*(c*syy-sy*sy)));
  if(den<=1e-9) return null;
  return Number((num/den).toFixed(3));
}
function correlationDangerousCorners(){
  try{
    const tl=(state.statTimeline||[]).slice(-12);
    const d=[], c=[];
    for(const p of tl){
      const dh=Number(p.stats?.dangerous?.home), da=Number(p.stats?.dangerous?.away);
      const ch=Number(p.stats?.corners?.home), ca=Number(p.stats?.corners?.away);
      if(Number.isFinite(dh)&&Number.isFinite(da)&&Number.isFinite(ch)&&Number.isFinite(ca)){
        d.push(dh+da); c.push(ch+ca);
      }
    }
    // use deltas
    const dd=[], cc=[];
    for(let i=1;i<d.length;i++){ dd.push(d[i]-d[i-1]); cc.push(c[i]-c[i-1]); }
    return pearson(dd,cc);
  }catch{return null;}
}

// --- Situational context factors ---
function buildSituationalFactors(){
  const scoreH=Number(state.score?.home)||0;
  const scoreA=Number(state.score?.away)||0;
  const minute=Number(state.minute)||0;
  const redH=Number(state.stats?.red?.home)||0;
  const redA=Number(state.stats?.red?.away)||0;
  const foulsH=Number(state.stats?.fouls?.home)||0;
  const foulsA=Number(state.stats?.fouls?.away)||0;
  const diffH=scoreH-scoreA;
  const diffA=scoreA-scoreH;

  function despair(diff){
    if(diff <= -2) return 1.20;
    if(diff === -1) return 1.10;
    if(diff >= 2) return 0.85;
    if(diff === 1) return 0.92;
    return 1.0;
  }
  let home=despair(diffH);
  let away=despair(diffA);

  // late game losing boost / winning dampen
  if(minute >= 80){
    if(diffH < 0) home *= 1.15;
    if(diffH > 0) home *= 0.85;
    if(diffA < 0) away *= 1.15;
    if(diffA > 0) away *= 0.85;
  }

  // red card impact
  if(redH > redA){ home *= 0.80; away *= 1.15; }
  if(redA > redH){ away *= 0.80; home *= 1.15; }

  // stoppage-heavy games (many fouls) slightly fewer corners expected
  const foulRate=((foulsH+foulsA)/Math.max(1,minute));
  const stoppage = foulRate > 0.45 ? 0.90 : 1.0;
  home *= stoppage; away *= stoppage;

  // goal momentum: corner/goal events in last 5 minutes
  const recent=(state.matchEvents||[]).filter(e=>{
    const m=eventMinuteValue(e);
    return m >= minute-5 && m <= minute+0.05 && (normalizeEventType(e.type)==="goal");
  });
  if(recent.some(e=>e.side==="home")) home *= 1.20;
  if(recent.some(e=>e.side==="away")) away *= 1.20;

  // Finer offensive substitution boost (decays over 5 minutes; stronger when losing / late)
  const subBoost={home:1,away:1,details:[]};
  const subs=(state.matchEvents||[]).filter(e=>normalizeEventType(e.type)==="substitution");
  for(const s of subs){
    const m=eventMinuteValue(s);
    const age=minute-m;
    if(age<0 || age>5) continue;
    const side=s.side==="away"?"away":(s.side==="home"?"home":null);
    if(!side) continue;
    // linear decay 1.0 → 0 over 5 minutes
    const decay=Math.max(0, 1 - age/5);
    // base offensive intent
    let boost=0.08; // +8% peak
    const sideDiff = side==="home" ? diffH : diffA;
    if(sideDiff < 0) boost += 0.05;          // losing side more likely offensive sub
    if(minute >= 60) boost += 0.03;          // late-game changes
    if(minute >= 75) boost += 0.03;
    // stacked subs in short window amplify slightly
    const recentSubsSame=subs.filter(x=>x.side===side && Math.abs(eventMinuteValue(x)-m)<=2).length;
    if(recentSubsSame >= 2) boost += 0.04;
    const factor=1 + boost*decay;
    if(side==="home") subBoost.home *= factor;
    else subBoost.away *= factor;
    subBoost.details.push({side, minute:Number(m.toFixed(2)), age:Number(age.toFixed(2)), factor:Number(factor.toFixed(3)), boost:Number(boost.toFixed(3))});
  }
  // cap cumulative sub boost
  subBoost.home=Math.min(1.22, subBoost.home);
  subBoost.away=Math.min(1.22, subBoost.away);
  home *= subBoost.home;
  away *= subBoost.away;

  // Recent form factor (exponential 0.9 per game) from team cache
  const formF={home:1,away:1};
  try{
    if(typeof computeTeamFormFactor==="function"){
      formF.home=computeTeamFormFactor("home");
      formF.away=computeTeamFormFactor("away");
      home *= formF.home;
      away *= formF.away;
    }
  }catch{}

  return {
    home:Number(home.toFixed(3)),
    away:Number(away.toFixed(3)),
    components:{
      scoreDiff:{home:diffH, away:diffA},
      red:{home:redH, away:redA},
      stoppageFactor:stoppage,
      lateGame:minute>=80,
      recentGoals:recent.length,
      subBoost:{home:Number(subBoost.home.toFixed(3)), away:Number(subBoost.away.toFixed(3)), details:subBoost.details.slice(-6)},
      formFactor:formF
    }
  };
}

function adaptiveDecayLambda(){
  // Higher event intensity → higher lambda (more weight on recent)
  const minute=Number(state.minute)||1;
  const fouls=(Number(state.stats?.fouls?.home)||0)+(Number(state.stats?.fouls?.away)||0);
  const shots=(Number(state.stats?.shots?.home)||0)+(Number(state.stats?.shots?.away)||0);
  const rate=(fouls+shots)/Math.max(1,minute);
  // map rate ~0.2..1.0 → lambda scale 0.7..1.4
  const scale=Math.max(0.7, Math.min(1.4, 0.7 + rate));
  return Number((Math.log(2)/Math.max(1, Number(PARAMS.cpiHalfLifeMin||6)) * scale).toFixed(4));
}

function momentWeight(minute){
  const m=Number(minute)||0;
  if(m < 15) return 0.8;
  if(m < 75) return 1.0;
  return 1.4; // final stretch
}

function applyPrecisionToStats(stats){
  let s=enforceAttackChain(stats||state.stats);
  // IQR protection on per-minute rates using timeline
  const tl=(state.statTimeline||[]).slice(-12);
  for(const key of ["attacks","dangerous","corners"]){
    for(const side of ["home","away"]){
      const series=tl.map(p=>Number(p.stats?.[key]?.[side])).filter(Number.isFinite);
      const cur=Number(s?.[key]?.[side]);
      if(!Number.isFinite(cur)) continue;
      const clipped=iqrClip(series, cur);
      if(clipped.outlier){
        s[key]={...(s[key]||{}),[side]:clipped.value};
        state.diagnostics.iqrClips=(state.diagnostics.iqrClips||0)+1;
      }
    }
  }
  return s;
}

function buildPrecisionReport(){
  const stagnation=detectStagnation();
  const corr=correlationDangerousCorners();
  const situational=buildSituationalFactors();
  const lambda=adaptiveDecayLambda();
  const mw=momentWeight(state.minute);
  return {
    schema:"cornerai-precision-1",
    watermark:PRECISION.watermark,
    stagnation,
    correlationDangerousCorners:corr,
    situational,
    adaptiveLambda:lambda,
    momentWeight:mw,
    clock:{
      minute:state.minute,
      extra:state.extraMinute||0,
      regressions:Number(state.diagnostics?.clockRegressions||0),
      lastRegression:state.diagnostics?.lastClockRegression||null
    },
    derivedAt:Date.now()
  };
}


// ===== Competition calibration + home factor + feedback + IndexedDB (v6.4) =====
const COMPETITION_FACTORS = {
  // relative corner intensity multipliers vs baseline 1.0
  "libertadores": 1.12,
  "copa libertadores": 1.12,
  "sudamericana": 1.10,
  "brasileirao": 1.06,
  "brasileirão": 1.06,
  "serie a": 1.05,
  "série a": 1.05,
  "premier league": 1.00,
  "la liga": 0.98,
  "bundesliga": 1.04,
  "serie a italiana": 0.97,
  "ligue 1": 0.96,
  "champions league": 1.08,
  "europa league": 1.05,
  "mls": 1.03,
  "liga mx": 1.07,
  "default": 1.00
};
function detectCompetition(raw){
  const s=String(raw||state.matchInfo?.competition||state.competition||state.menuCapture?.current?.title||"").toLowerCase();
  for(const key of Object.keys(COMPETITION_FACTORS)){
    if(key!=="default" && s.includes(key)) return key;
  }
  // weak heuristics from page text fragments
  if(/libertadores/.test(s)) return "libertadores";
  if(/brasileir|serie a|série a/.test(s)) return "brasileirao";
  if(/premier/.test(s)) return "premier league";
  if(/champions/.test(s)) return "champions league";
  return "default";
}
function competitionFactor(name){
  const key=detectCompetition(name);
  return {key, factor:Number(COMPETITION_FACTORS[key]??1)};
}
function homeAdvantageMultiplier(){
  // Home side pressure bias (corners/attacks typically higher at home)
  return Number(PARAMS.homeAdvantageFactor||1.08);
}
function buildCalibrationContext(){
  const comp=competitionFactor(state.competition||state.matchInfo?.competition||"");
  const homeAdv=homeAdvantageMultiplier();
  return {
    competition:comp.key,
    competitionFactor:comp.factor,
    homeAdvantage:homeAdv,
    // effective multipliers applied to side-level pressure features
    sideFactors:{
      home:Number((comp.factor*homeAdv).toFixed(4)),
      away:Number((comp.factor*1.0).toFixed(4))
    }
  };
}

// --- Prediction feedback loop ---
const __feedbackMem={pending:[], lastRecordAt:0};
function recordCornerPrediction(pred){
  try{
    if(!pred||!state.fixtureId) return;
    const now=Date.now();
    if(now-__feedbackMem.lastRecordAt<20000) return; // throttle
    __feedbackMem.lastRecordAt=now;
    const entry={
      id:`${state.fixtureId}:${state.minute}:${now}`,
      fixtureId:String(state.fixtureId),
      minute:Number(state.minute)||0,
      predictedAt:now,
      probability:Number(pred.probability)||0,
      preferredSide:pred.preferredSide||null,
      horizonMin:Number(pred.horizonMin||2),
      resolved:false,
      hit:null,
      actualCorners:null
    };
    __feedbackMem.pending.push(entry);
    __feedbackMem.pending=__feedbackMem.pending.slice(-80);
    state.feedback=state.feedback||{pending:[], resolved:[], stats:{n:0,hits:0,brier:0}};
    state.feedback.pending=__feedbackMem.pending.filter(x=>!x.resolved).slice(-40);
  }catch{}
}
function resolveFeedbackAgainstCorners(){
  try{
    const corners=Array.isArray(state.cornerEvents)?state.cornerEvents:[];
    const nowM=Number(state.minute);
    if(!Number.isFinite(nowM)) return;
    state.feedback=state.feedback||{pending:[], resolved:[], stats:{n:0,hits:0,brier:0}};
    const pending=__feedbackMem.pending.length?__feedbackMem.pending:(state.feedback.pending||[]);
    let changed=false;
    for(const p of pending){
      if(p.resolved) continue;
      if(nowM < p.minute + p.horizonMin) continue;
      // did a corner occur in (predictedMinute, predictedMinute+horizon]?
      const hits=corners.filter(c=>{
        const m=Number(c.minute)+(Number(c.extraMinute)||0)/100;
        return m>p.minute && m<=p.minute+p.horizonMin;
      });
      p.resolved=true;
      p.actualCorners=hits.length;
      p.hit=hits.length>0;
      // side accuracy if preferredSide set
      if(p.preferredSide && hits.length){
        p.sideHit=hits.some(c=>(c.side||c.team)===p.preferredSide);
      }
      // Brier component
      const y=p.hit?1:0;
      p.brier=Number(Math.pow((p.probability||0)-y,2).toFixed(4));
      changed=true;
      state.feedback.resolved.push(p);
    }
    if(changed){
      state.feedback.resolved=state.feedback.resolved.slice(-200);
      state.feedback.pending=pending.filter(x=>!x.resolved).slice(-40);
      __feedbackMem.pending=state.feedback.pending.slice();
      const res=state.feedback.resolved;
      const n=res.length;
      const hits=res.filter(x=>x.hit).length;
      const brier=n?res.reduce((s,x)=>s+(x.brier||0),0)/n:0;
      // simple online calibration: if overconfident, damp future probabilities slightly via PARAMS
      const avgPred=n?res.reduce((s,x)=>s+(x.probability||0),0)/n:0;
      const hitRate=n?hits/n:0;
      state.feedback.stats={n,hits,hitRate:Number(hitRate.toFixed(3)),brier:Number(brier.toFixed(4)),avgPred:Number(avgPred.toFixed(3)),updatedAt:Date.now()};
      // Adjust CPI favorite weight lightly based on calibration error (very conservative)
      if(n>=15 && PARAMS.cpiWeights){
        const err=avgPred-hitRate; // positive = overconfident
        if(Math.abs(err)>0.08){
          const adj=err>0?-0.01:0.01;
          PARAMS.cpiWeights.favorite=Math.max(0.02,Math.min(0.10,(Number(PARAMS.cpiWeights.favorite)||0.05)+adj));
        }
      }
      void persistFeedbackStore();
      void idbPutFeedback(state.feedback.stats, state.feedback.resolved.slice(-30));
    }
  }catch{}
}
async function persistFeedbackStore(){
  try{
    await chrome.storage.local.set({cornerai_feedback:{stats:state.feedback?.stats||{}, resolved:(state.feedback?.resolved||[]).slice(-100), updatedAt:Date.now()}});
  }catch{}
}
async function loadFeedbackStore(){
  try{
    const r=await chrome.storage.local.get(["cornerai_feedback"]);
    if(r.cornerai_feedback){
      state.feedback=state.feedback||{pending:[],resolved:[],stats:{n:0,hits:0,brier:0}};
      state.feedback.resolved=Array.isArray(r.cornerai_feedback.resolved)?r.cornerai_feedback.resolved:[];
      state.feedback.stats=r.cornerai_feedback.stats||state.feedback.stats;
    }
  }catch{}
}

// --- IndexedDB match history ---
let __idb=null;
function idbOpen(){
  return new Promise((resolve,reject)=>{
    if(__idb){resolve(__idb);return;}
    if(typeof indexedDB==="undefined"){reject(new Error("no idb"));return;}
    const req=indexedDB.open("cornerai_history_v1",1);
    req.onupgradeneeded=()=>{
      const db=req.result;
      if(!db.objectStoreNames.contains("matches")){
        const st=db.createObjectStore("matches",{keyPath:"fixtureId"});
        st.createIndex("byFinishedAt","finishedAt",{unique:false});
        st.createIndex("byHome","home",{unique:false});
        st.createIndex("byAway","away",{unique:false});
      }
      if(!db.objectStoreNames.contains("feedback")){
        db.createObjectStore("feedback",{keyPath:"id"});
      }
    };
    req.onsuccess=()=>{__idb=req.result;resolve(__idb);};
    req.onerror=()=>reject(req.error||new Error("idb open failed"));
  });
}
async function idbPutMatch(summary){
  try{
    if(PARAMS.idbEnabled===false) return;
    const db=await idbOpen();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction("matches","readwrite");
      tx.objectStore("matches").put(summary);
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(tx.error);
    });
    state.diagnostics.idbMatchWrites=(state.diagnostics.idbMatchWrites||0)+1;
  }catch(e){state.diagnostics.idbErrors=(state.diagnostics.idbErrors||0)+1;}
}
async function idbPutFeedback(stats, recent){
  try{
    if(PARAMS.idbEnabled===false) return;
    const db=await idbOpen();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction("feedback","readwrite");
      tx.objectStore("feedback").put({id:"latest",stats,recent,updatedAt:Date.now()});
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(tx.error);
    });
  }catch{}
}
async function idbListMatches(limit=30){
  try{
    const db=await idbOpen();
    return await new Promise((resolve,reject)=>{
      const tx=db.transaction("matches","readonly");
      const req=tx.objectStore("matches").getAll();
      req.onsuccess=()=>{
        const rows=(req.result||[]).sort((a,b)=>(b.finishedAt||0)-(a.finishedAt||0)).slice(0,limit);
        resolve(rows);
      };
      req.onerror=()=>reject(req.error);
    });
  }catch{return [];}
}
async function idbPruneOld(days){
  try{
    const db=await idbOpen();
    const cutoff=Date.now()-Math.max(1,days)*86400000;
    const all=await idbListMatches(500);
    const toDelete=all.filter(m=>(m.finishedAt||0)<cutoff);
    if(!toDelete.length) return 0;
    await new Promise((resolve,reject)=>{
      const tx=db.transaction("matches","readwrite");
      const st=tx.objectStore("matches");
      for(const m of toDelete) st.delete(m.fixtureId);
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(tx.error);
    });
    return toDelete.length;
  }catch{return 0;}
}
function buildMatchHistorySummary(){
  return {
    fixtureId:String(state.fixtureId||""),
    home:state.home||"",
    away:state.away||"",
    score:{home:state.score?.home??null,away:state.score?.away??null},
    competition:state.competition||detectCompetition(""),
    corners:{home:state.stats?.corners?.home??null,away:state.stats?.corners?.away??null},
    xg:{home:state.stats?.xg?.home??null,away:state.stats?.xg?.away??null},
    events:Number(state.eventCount||0),
    cornerEvents:Number(state.cornerEventCount||0),
    quality:Number(state.quality?.score||0),
    feedback:state.feedback?.stats||null,
    calibration:buildCalibrationContext(),
    finishedAt:Date.now(),
    version:VERSION
  };
}
async function archiveFinishedMatchIfNeeded(){
  try{
    if(!state.fixtureId) return;
    if(!(state.liveStatus==="finished"||state.dataMode==="historical")) return;
    if(state._archivedFixtureId===state.fixtureId) return;
    const summary=buildMatchHistorySummary();
    // attach enriched H2H snapshot if any
    summary.h2hEnrichment = {
      averages: state.h2h?.averages||null,
      cornersResultCorr: state.h2h?.averages?.cornersResultCorr??null,
      drawRate: state.h2h?.averages?.drawRate??null
    };
    summary.attackFactors = {
      home: (typeof computeTeamAttackFactor==="function")?computeTeamAttackFactor("home"):null,
      away: (typeof computeTeamAttackFactor==="function")?computeTeamAttackFactor("away"):null
    };
    await idbPutMatch(summary);
    try{await updateTeamAttackFactorsFromResult();}catch{}
    state._archivedFixtureId=state.fixtureId;
    await idbPruneOld(Number(PARAMS.historyRetentionDays||30));
  }catch{}
}

// Alert preferences (user-configurable)
const DEFAULT_ALERT_PREFS={
  enabled:true,
  favorite_losing:true,
  cpi_high:true,
  cpiThreshold:0.72,
  appm_accel:true,
  corner_prediction:true,
  cornerPredThreshold:0.55,
  goals:false,
  red_cards:true
};
async function loadAlertPrefs(){
  try{
    const r=await chrome.storage.local.get(["cornerai_alert_prefs"]);
    state.alertPrefs={...DEFAULT_ALERT_PREFS,...(r.cornerai_alert_prefs||{})};
  }catch{state.alertPrefs={...DEFAULT_ALERT_PREFS};}
}
async function saveAlertPrefs(prefs){
  state.alertPrefs={...DEFAULT_ALERT_PREFS,...(prefs||{})};
  await chrome.storage.local.set({cornerai_alert_prefs:state.alertPrefs});
  return state.alertPrefs;
}


// ===== Semantic events + temporal patterns + consistency (v6.3) =====
const EVENT_TYPE_MAP={
  goal:["goal","gol","golo","scored"],
  corner:["corner","escanteio","escanteios","canto","cantos"],
  yellow:["yellow","yellow_card","card_yellow","amarelo","cartao_amarelo","cartão_amarelo"],
  red:["red","red_card","card_red","vermelho","cartao_vermelho","cartão_vermelho","second_yellow"],
  substitution:["substitution","subs","substituicao","substituição","troca"],
  shot_on:["shot_on","shot_on_target","chute_a_gol","finalizacao_no_alvo","on_target"],
  shot_off:["shot_off","shot_off_target","chute_fora","off_target"],
  foul:["foul","falta","faltas"],
  offside:["offside","impedimento","impedimentos"],
  save:["save","defesa","defesas"],
  cross:["cross","cruzamento","cruzamentos"]
};
const EVENT_IMPORTANCE={goal:10,red:8,penalty:7,substitution:4,yellow:4,shot_on:4,corner:3,shot_off:2,foul:2,offside:1,save:2,cross:2,other:1};
function normalizeEventType(raw){
  const s=String(raw||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9_]+/g,"_");
  for(const [canon,aliases] of Object.entries(EVENT_TYPE_MAP)){
    if(s===canon) return canon;
    if(aliases.some(a=>s===a||s.includes(a))) return canon;
  }
  if(/corner|escante|canto/.test(s)) return "corner";
  if(/goal|gol/.test(s)) return "goal";
  if(/yellow|amarelo/.test(s)) return "yellow";
  if(/red|vermelho/.test(s)) return "red";
  if(/substit/.test(s)) return "substitution";
  if(/shot.*on|chute.*gol|on_target/.test(s)) return "shot_on";
  if(/shot|chute|finaliza/.test(s)) return "shot_off";
  if(/foul|falta/.test(s)) return "foul";
  if(/offside|imped/.test(s)) return "offside";
  return s||"other";
}
function eventMinuteValue(e){
  return Number(e?.minute||0)+(Number(e?.extraMinute||0)/100);
}
function buildSemanticEvents(limit=400){
  const raw=(state.matchEvents||[]).slice(-limit);
  return raw.map(e=>{
    const type=normalizeEventType(e.type||e.label||e.eventType);
    return {
      minute:Number(e.minute)||0,
      extraMinute:Number(e.extraMinute)||0,
      t:eventMinuteValue(e),
      side:e.side==="away"?"away":(e.side==="home"?"home":null),
      type,
      importance:EVENT_IMPORTANCE[type]??EVENT_IMPORTANCE.other,
      source:e.source||null,
      team:e.team||null
    };
  }).sort((a,b)=>a.t-b.t);
}
function buildEventEpisodes(events,gapMinutes=0.75){
  // Group nearby events into episodes to avoid double counting foul+card etc.
  const eps=[];
  let cur=null;
  for(const e of events){
    if(!cur || (e.t-cur.end)>gapMinutes || (e.side&&cur.side&&e.side!==cur.side)){
      cur={start:e.t,end:e.t,side:e.side,types:[e.type],importance:e.importance,count:1,events:[e]};
      eps.push(cur);
    }else{
      cur.end=e.t;
      cur.types.push(e.type);
      cur.importance=Math.max(cur.importance,e.importance);
      cur.count++;
      cur.events.push(e);
      if(e.side) cur.side=e.side;
    }
  }
  return eps.map(ep=>({
    start:Number(ep.start.toFixed(2)),
    end:Number(ep.end.toFixed(2)),
    side:ep.side,
    types:[...new Set(ep.types)],
    importance:ep.importance,
    count:ep.count,
    primary:ep.types.slice().sort((a,b)=>(EVENT_IMPORTANCE[b]||0)-(EVENT_IMPORTANCE[a]||0))[0]||"other"
  }));
}
function slidingWindowMetrics(events,nowMinute,windows=[5,10,15]){
  const out={};
  for(const w of windows){
    const from=nowMinute-w;
    const slice=events.filter(e=>e.t>=from && e.t<=nowMinute);
    const byType={};
    const bySide={home:{},away:{}};
    for(const e of slice){
      byType[e.type]=(byType[e.type]||0)+1;
      if(e.side==="home"||e.side==="away"){
        bySide[e.side][e.type]=(bySide[e.side][e.type]||0)+1;
      }
    }
    out[String(w)+"m"]={
      total:slice.length,
      byType,
      home:bySide.home,
      away:bySide.away,
      importanceSum:slice.reduce((s,e)=>s+(e.importance||0),0),
      corners:(byType.corner||0),
      shot_on:(byType.shot_on||0),
      attacksProxy:(byType.shot_on||0)+(byType.shot_off||0)+(byType.corner||0)+(byType.cross||0)
    };
  }
  return out;
}
function detectPressurePeaks(events,nowMinute){
  // High intensity: >=3 attack-like events in 2 minutes
  const peaks=[];
  const kinds=new Set(["shot_on","shot_off","corner","cross","goal"]);
  const relevant=events.filter(e=>kinds.has(e.type) && e.t>=nowMinute-12 && e.t<=nowMinute+0.01);
  for(let i=0;i<relevant.length;i++){
    const start=relevant[i].t;
    let j=i, count=0, sides={home:0,away:0};
    while(j<relevant.length && relevant[j].t-start<=2.0){
      count++;
      if(relevant[j].side==="home") sides.home++;
      if(relevant[j].side==="away") sides.away++;
      j++;
    }
    if(count>=3){
      peaks.push({
        start:Number(start.toFixed(2)),
        end:Number(relevant[j-1].t.toFixed(2)),
        count,
        side:sides.home>=sides.away?"home":"away",
        label:"pressao_alta"
      });
      i=j-1;
    }
  }
  // merge overlapping
  const merged=[];
  for(const p of peaks){
    const last=merged[merged.length-1];
    if(last && p.start<=last.end+0.5 && p.side===last.side){
      last.end=Math.max(last.end,p.end);
      last.count=Math.max(last.count,p.count);
    }else merged.push({...p});
  }
  return merged.slice(-12);
}
function detectEventSequences(events,nowMinute){
  // Patterns: corner -> shot_* -> corner within 3 minutes
  const seqs=[];
  const recent=events.filter(e=>e.t>=nowMinute-20 && e.t<=nowMinute+0.01);
  for(let i=0;i<recent.length;i++){
    if(recent[i].type!=="corner") continue;
    const side=recent[i].side;
    let shot=null, corner2=null;
    for(let j=i+1;j<recent.length;j++){
      if(recent[j].t-recent[i].t>3.0) break;
      if(side && recent[j].side && recent[j].side!==side) continue;
      if(!shot && (recent[j].type==="shot_on"||recent[j].type==="shot_off"||recent[j].type==="goal")){
        shot=recent[j]; continue;
      }
      if(shot && recent[j].type==="corner"){ corner2=recent[j]; break; }
    }
    if(shot && corner2){
      seqs.push({
        pattern:"corner_shot_corner",
        side:side||shot.side||corner2.side,
        start:Number(recent[i].t.toFixed(2)),
        end:Number(corner2.t.toFixed(2)),
        goalBoost: shot.type==="shot_on"||shot.type==="goal"
      });
    }
  }
  return seqs.slice(-20);
}
function perMinuteRates(stats,minute){
  const m=Math.max(1,Number(minute)||1);
  const out={};
  for(const k of STAT_KEYS){
    const h=Number(stats?.[k]?.home), a=Number(stats?.[k]?.away);
    out[k]={
      home:Number.isFinite(h)?Number((h/m).toFixed(4)):null,
      away:Number.isFinite(a)?Number((a/m).toFixed(4)):null
    };
  }
  return out;
}
function businessRuleChecks(){
  const issues=[];
  const yH=Number(state.stats?.yellow?.home), yA=Number(state.stats?.yellow?.away);
  const fH=Number(state.stats?.fouls?.home), fA=Number(state.stats?.fouls?.away);
  const sH=Number(state.stats?.subs?.home), sA=Number(state.stats?.subs?.away);
  const rH=Number(state.stats?.red?.home), rA=Number(state.stats?.red?.away);
  const cH=Number(state.stats?.corners?.home), cA=Number(state.stats?.corners?.away);
  const minute=Number(state.minute)||0;
  if(Number.isFinite(fH)&&Number.isFinite(yH)&&fH<yH) issues.push({rule:"fouls_gte_yellow",side:"home",fouls:fH,yellow:yH});
  if(Number.isFinite(fA)&&Number.isFinite(yA)&&fA<yA) issues.push({rule:"fouls_gte_yellow",side:"away",fouls:fA,yellow:yA});
  // modern competitions allow up to 5 (sometimes 6 with concussion) — flag only absurd
  if(Number.isFinite(sH)&&sH>6) issues.push({rule:"subs_cap",side:"home",subs:sH});
  if(Number.isFinite(sA)&&sA>6) issues.push({rule:"subs_cap",side:"away",subs:sA});
  if(Number.isFinite(rH)&&rH>3) issues.push({rule:"red_cap",side:"home",red:rH});
  if(Number.isFinite(rA)&&rA>3) issues.push({rule:"red_cap",side:"away",red:rA});
  // anomaly: >1.2 corners/min sustained
  if(minute>=10){
    if(Number.isFinite(cH)&&cH/minute>1.2) issues.push({rule:"corner_rate_anomaly",side:"home",rate:Number((cH/minute).toFixed(3))});
    if(Number.isFinite(cA)&&cA/minute>1.2) issues.push({rule:"corner_rate_anomaly",side:"away",rate:Number((cA/minute).toFixed(3))});
  }
  const pH=Number(state.stats?.possession?.home), pA=Number(state.stats?.possession?.away);
  if(Number.isFinite(pH)&&Number.isFinite(pA)&&Math.abs(pH+pA-100)>2.5) issues.push({rule:"possession_sum",home:pH,away:pA});
  return issues;
}
function predictCornerNext2m(semantic, windows, peaks, sequences, cpiHome, cpiAway){
  // Lightweight calibrated heuristic (not a trained neural net)
  const w5=windows?.["5m"]||{};
  const base=0.12;
  const cornerDensity=Math.min(1,(Number(w5.corners||0)/3));
  const attackDensity=Math.min(1,(Number(w5.attacksProxy||0)/6));
  const peakBoost=peaks?.length?Math.min(0.25,peaks.slice(-1)[0].count*0.05):0;
  const seqBoost=sequences?.some(s=>s.pattern==="corner_shot_corner")?0.12:0;
  const cpi=Math.max(Number(cpiHome||0),Number(cpiAway||0));
  const cpiTerm=Math.min(0.3,cpi*0.3);
  const minute=Number(state.minute)||0;
  const late=minute>=80?0.08:0;
  const p=Math.max(0.02,Math.min(0.85, base + 0.18*cornerDensity + 0.16*attackDensity + peakBoost + seqBoost + cpiTerm + late));
  const side = (Number(cpiHome||0)>=Number(cpiAway||0))?"home":"away";
  return {
    horizonMin:2,
    probability:Number(p.toFixed(3)),
    preferredSide:side,
    drivers:{cornerDensity,attackDensity,peakBoost,seqBoost,cpiTerm,late},
    model:"corner-next-2m-heuristic-v1"
  };
}
function buildTemporalIntelligence(){
  const now=Number(state.minute);
  if(!Number.isFinite(now)) return null;
  const semantic=buildSemanticEvents();
  const episodes=buildEventEpisodes(semantic);
  const windows=slidingWindowMetrics(semantic,now,[5,10,15]);
  const peaks=detectPressurePeaks(semantic,now);
  const sequences=detectEventSequences(semantic,now);
  const rates=perMinuteRates(state.stats,now);
  const rules=businessRuleChecks();
  // fatigue proxy from subs + event intensity
  const subsH=Number(state.stats?.subs?.home)||0, subsA=Number(state.stats?.subs?.away)||0;
  const intensity=(windows["10m"]?.importanceSum||0)/40;
  const fatigue={
    home:Number(Math.max(0,Math.min(1,(subsH/5)*0.6 + intensity*0.4)).toFixed(3)),
    away:Number(Math.max(0,Math.min(1,(subsA/5)*0.6 + intensity*0.4)).toFixed(3))
  };
  return {
    schema:"cornerai-temporal-1",
    asOf:now,
    semanticCounts:semantic.reduce((acc,e)=>{acc[e.type]=(acc[e.type]||0)+1;return acc;},{}),
    episodes:episodes.slice(-40),
    windows,
    peaks,
    sequences,
    ratesPerMinute:rates,
    businessRules:{ok:rules.length===0,issues:rules.slice(0,20)},
    fatigue,
    derivedAt:Date.now()
  };
}


function buildIntelligenceFeatures(){
  const timeline=(state.statTimeline||[]).slice().sort((a,b)=>pointMinuteValue(a)-pointMinuteValue(b));
  const latest=timeline[timeline.length-1]||null;
  const recent=timeline.slice(-12);
  const features={},trends={};
  const anomalies=[];
  const keys=STAT_KEYS;

  for(const k of keys){
    const v=latest?.stats?.[k]||{};
    const row={home:v.home??null,away:v.away??null,deltaHome:null,deltaAway:null,rateHome:null,rateAway:null};
    const prev=timeline.length>1?timeline[timeline.length-2]:null;
    row.deltaHome=metricPairDelta(latest,prev,k,"home");
    row.deltaAway=metricPairDelta(latest,prev,k,"away");
    const first=recent[0];
    const elapsed=Math.max(1,pointMinuteValue(latest||{})-pointMinuteValue(first||{}));
    row.rateHome=row.deltaHome==null?null:Number((row.deltaHome/elapsed).toFixed(4));
    row.rateAway=row.deltaAway==null?null:Number((row.deltaAway/elapsed).toFixed(4));
    features[k]=row;

    const samples=recent.map(p=>p.stats?.[k]).filter(x=>Number.isFinite(Number(x?.home))&&Number.isFinite(Number(x?.away)));
    if(samples.length>=2){
      const dh=Number(samples[samples.length-1].home)-Number(samples[0].home);
      const da=Number(samples[samples.length-1].away)-Number(samples[0].away);
      trends[k]={homeDelta:dh,awayDelta:da,samples:samples.length};
    }else trends[k]={homeDelta:null,awayDelta:null,samples:samples.length};
  }

  // Provider consistency checks: flag contradictions without fabricating corrections.
  const s=latest?.stats||{};
  for(const side of ["home","away"]){
    const attacks=Number(s.attacks?.[side]),dangerous=Number(s.dangerous?.[side]);
    const shots=Number(s.shots?.[side]),on=Number(s.shotsOn?.[side]),off=Number(s.shotsOff?.[side]);
    const poss=Number(s.possession?.[side]);
    const xg=Number(s.xg?.[side]);
    if(Number.isFinite(dangerous)&&Number.isFinite(attacks)&&dangerous>attacks)
      anomalies.push({type:"dangerous_gt_attacks",side,values:{dangerous,attacks}});
    if(Number.isFinite(on)&&Number.isFinite(shots)&&on>shots)
      anomalies.push({type:"shots_on_gt_shots",side,values:{shots,on}});
    if(Number.isFinite(off)&&Number.isFinite(shots)&&off>shots)
      anomalies.push({type:"shots_off_gt_shots",side,values:{shots,off}});
    if(Number.isFinite(xg)&&xg>PARAMS.maxXGPerTeam)
      anomalies.push({type:"xg_out_of_range",side,value:xg});
    if(Number.isFinite(poss)&& (poss<0||poss>100))
      anomalies.push({type:"possession_out_of_range",side,value:poss});
  }
  const ph=Number(s.possession?.home),pa=Number(s.possession?.away);
  if(Number.isFinite(ph)&&Number.isFinite(pa)&&Math.abs(ph+pa-100)>1.5)
    anomalies.push({type:"possession_sum_invalid",values:{home:ph,away:pa}});

  // Momentum is deliberately a feature, not a prediction. It combines recent
  // changes from independent pressure indicators and gives the downstream AI
  // a stable, normalized signal.
  // Momentum multi-fonte: trends de stats + pressão (barras/intervalos) + APPM
  const weights={dangerous:0.28,shotsOn:0.18,xg:0.18,corners:0.12};
  const momentum={home:0,away:0};
  for(const side of ["home","away"]){
    let total=0,weightSum=0;
    for(const [k,w] of Object.entries(weights)){
      const t=trends[k];
      if(!t) continue;
      const d=Number(t[side+"Delta"]);
      if(!Number.isFinite(d)) continue;
      const scale=k==="xg"?1:(k==="dangerous"?8:(k==="shotsOn"?4:3));
      total += Math.max(-1,Math.min(1,d/scale))*w;
      weightSum += w;
    }
    // Pressão por intervalos (último snapshot charts-pressure)
    const inds=(state.cornerIndicatorTimeline||[]).slice().filter(p=>p&&p.pressure&&typeof p.pressure==="object");
    const lastInd=inds.length?inds[inds.length-1]:null;
    if(lastInd){
      const intervals=Object.entries(lastInd.pressure).filter(([k,v])=>/^\d{1,2}-\d{1,2}$/.test(k)&&v&&Number.isFinite(Number(v.home))&&Number.isFinite(Number(v.away)));
      if(intervals.length){
        // peso maior no intervalo mais recente
        let pSum=0,pW=0;
        intervals.forEach(([k,v],i)=>{
          const w=0.5+0.5*(i/(intervals.length-1||1));
          const val=Number(v[side]);
          if(!Number.isFinite(val)) return;
          // normaliza 0-100 → -1..1 centrado em 50
          pSum += Math.max(-1,Math.min(1,(val-50)/50))*w;
          pW += w;
        });
        if(pW>0){ total += (pSum/pW)*0.22; weightSum += 0.22; }
      }
      // APPM 5m / 10m
      const appm=lastInd.appm||{};
      for(const win of ["5m","10m","3m","1m"]){
        const pair=appm[win];
        if(!pair) continue;
        const val=Number(pair[side]);
        if(!Number.isFinite(val)) continue;
        const scale=win==="1m"?3:(win==="3m"?2:(win==="5m"?1.5:1));
        total += Math.max(-1,Math.min(1,val/scale))*0.12;
        weightSum += 0.12;
        break;
      }
    }
    // Fallback: dangerous rate por minuto atual
    const clock=Math.max(1,Number(state.minute)||1);
    const dang=Number(state.stats?.dangerous?.[side]);
    if(Number.isFinite(dang)&&dang>=0){
      const rate=dang/clock;
      total += Math.max(-1,Math.min(1,(rate-0.4)/0.6))*0.1;
      weightSum += 0.1;
    }
    momentum[side]=weightSum?Number((total/weightSum).toFixed(4)):0;
  }

  const canonicalAvailable=STAT_KEYS.filter(k=>latest?.stats?.[k]?.home!=null&&latest?.stats?.[k]?.away!=null).length;
  const sourceSamples=Object.values(state.sources||{}).reduce((n,x)=>n+Number(x?.count||0),0);
  const conflicts=Number(state.diagnostics?.statConflicts||0);
  const conflictPenalty=Math.min(0.25,conflicts/Math.max(20,sourceSamples)*0.25);
  const completeness=canonicalAvailable/STAT_KEYS.length;
  const sourceQuality=Math.min(1,(Object.keys(state.provenance?.sourceCounts||{}).filter(k=>Number(state.provenance.sourceCounts[k]||0)>0).length)/3);
  const consistencyPenalty=Math.min(0.25,anomalies.length*0.04);
  const confidence=Math.max(0,Math.min(1,completeness*0.55+sourceQuality*0.25+(timeline.length?0.20:0)-conflictPenalty-consistencyPenalty));
  const readiness=Math.max(0,Math.min(100,Math.round(confidence*100)));

  state.diagnostics.statAnomalies=anomalies.length;
  // AI feature construction is controlled by the caller, where payload is in scope.
  state.diagnostics.aiFeatureBuilds++;
  const temporal=buildTemporalIntelligence();
  // Persist lightweight temporal snapshot on state for AI feed / notifications
  state.temporal=temporal;
  return {
    schema:"cornerai-intelligence-2",
    readiness,confidence:Number(confidence.toFixed(4)),
    asOf:latest?{period:latest.period,minute:latest.minute,extraMinute:latest.extraMinute||0}:null,
    features,trends,momentum,anomalies:anomalies.slice(0,100),
    temporal:temporal?{
      windows:temporal.windows,
      peaks:temporal.peaks,
      sequences:temporal.sequences,
      fatigue:temporal.fatigue,
      businessRules:temporal.businessRules,
      semanticCounts:temporal.semanticCounts
    }:null,
    precision:(typeof buildPrecisionReport==="function")?buildPrecisionReport():null,
    predictive:(typeof buildAdvancedPredictiveFeatures==="function")?buildAdvancedPredictiveFeatures():null,
    explain:(typeof buildExplainabilityBundle==="function")?buildExplainabilityBundle():null,
    drift:state.drift||null,
    sourceConsensus:{
      score:Number(Math.max(0,1-conflictPenalty).toFixed(4)),
      conflicts,samples:sourceSamples,
      activeSources:Object.entries(state.provenance?.sourceCounts||{}).filter(([,v])=>Number(v||0)>0).map(([k])=>k)
    },
    derivedAt:Date.now()
  };
}


function isHistoricalEndpoint(url){
  // Endpoints auxiliares (preodds/x7/grafic/stats) existem em LIVE e histórico.
  // NÃO usar esta lista para forçar status finished — só para ingestão de odds/charts.
  const u=String(url||"").toLowerCase();
  return /\/preodds\b|\/x7\b|\/grafic\b|\/projecao\b|\/history\b|\/histor|\/season\/|\/timeline\b|\/events\b|\/incidents\b|\/stats\b|\/form\b|\/h2h\b|site-storage:\/\//.test(u);
}
/** Endpoints que realmente indicam partida ENCERRADA (não usados em live). */
function isPostMatchOnlyEndpoint(url){
  const u=String(url||"").toLowerCase();
  return /\/history\/|\/historico|\/finished\b|\/result\b|\/archive\b|\/past-match/.test(u);
}
function lockOpeningOddsFromPayload(payload,source){
  if(state.openingOdds)return false;
  const odds=Array.isArray(payload?.odds)?payload.odds:[];
  let home=null,away=null,draw=null;
  for(const q of odds){
    const n=Number(q?.odds??q?.odd??q?.price);
    if(!Number.isFinite(n)||n<1.01)continue;
    const sel=String(q?.selection??q?.outcome??q?.label??"").toLowerCase();
    const mkt=String(q?.market??q?.marketType??"").toLowerCase();
    const is1x2=/1x2|match result|resultado|moneyline|vencedor/.test(mkt)||(!mkt&&/home|away|draw|empate|casa|fora/.test(sel));
    if(!is1x2&&!/home|away|draw|empate|1|x|2/.test(sel))continue;
    if(/home|casa|mandante|^1$/.test(sel))home=home??n;
    else if(/away|fora|visitante|^2$/.test(sel))away=away??n;
    else if(/draw|empate|^x$/.test(sel))draw=draw??n;
  }
  // Also accept pair shapes
  if(payload?.openingOdds&&typeof payload.openingOdds==="object"){
    home=home??Number(payload.openingOdds.home);
    away=away??Number(payload.openingOdds.away);
    draw=draw??Number(payload.openingOdds.draw);
  }
  if(Number.isFinite(home)&&Number.isFinite(away)&&home>=1.01&&away>=1.01){
    state.openingOdds={home,draw:Number.isFinite(draw)?draw:null,away,source:String(source||"historical"),lockedAt:Date.now()};
    state.fixedFavorite=home<=away?"home":"away";
    if(home<=2.10&&home<away)state.fixedFavorite="home";
    else if(away<=2.10&&away<home)state.fixedFavorite="away";
    state.openingOddsLockedAt=Date.now();
    state.diagnostics.openingOddsLocked=(state.diagnostics.openingOddsLocked||0)+1;
    return true;
  }
  return false;
}
function rebuildHistoricalCoverage(){
  const events=Array.isArray(state.matchEvents)?state.matchEvents:[];
  const corners=events.filter(e=>e&&e.type==="corner");
  const minutes=new Set();
  for(const e of events){
    const m=Number(e?.minute);
    if(Number.isFinite(m)&&m>=0&&m<=130)minutes.add(Math.floor(m));
  }
  for(const s of (state.statTimeline||[])){
    const m=Number(s?.minute??s?.m);
    if(Number.isFinite(m)&&m>=0&&m<=130)minutes.add(Math.floor(m));
  }
  const sorted=[...minutes].sort((a,b)=>a-b);
  // canto_casado density: consecutive corners < 90s within 5-min window (approx by minute delta <=1)
  let casado=0;
  const bySide={home:[],away:[]};
  for(const c of corners){
    const side=c.side==="away"?"away":"home";
    bySide[side].push(Number(c.minute)||0);
  }
  for(const side of ["home","away"]){
    const arr=bySide[side].sort((a,b)=>a-b);
    for(let i=1;i<arr.length;i++){
      if(arr[i]-arr[i-1]<=1)casado++;
    }
  }
  state.historical={
    schema:"cornerai-historical-1",
    updatedAt:Date.now(),
    eventCount:events.length,
    cornerCount:corners.length,
    minuteCoverage:sorted.length,
    minutesObserved:sorted.slice(0,130),
    missingMinutes:(()=>{const miss=[];for(let i=0;i<=Math.min(90,sorted[sorted.length-1]||0);i++){if(!minutes.has(i))miss.push(i)}return miss.slice(0,40)})(),
    cantoCasadoClusters:casado,
    openingOdds:state.openingOdds||null,
    fixedFavorite:state.fixedFavorite||null,
    dataMode:state.dataMode||"unknown"
  };
  state.diagnostics.historicalRebuilds=(state.diagnostics.historicalRebuilds||0)+1;
  return state.historical;
}
function ingestHistoricalEndpoint(url,payload,source){
  try{const id=extractFixtureIdFromString(url); if(id&&!state.fixtureId){state.fixtureId=String(id);state.diagnostics.fixtureRecovered=(state.diagnostics.fixtureRecovered||0)+1;}}catch{}

  if(!isHistoricalEndpoint(url)&&state.dataMode!=="historical"&&state.liveStatus!=="finished")return false;
  state.diagnostics.historicalIngests=(state.diagnostics.historicalIngests||0)+1;
  state.diagnostics.lastHistoricalEndpoint=String(url||"").slice(0,400);
  state.diagnostics.lastHistoricalAt=Date.now();
  let changed=false;
  if(lockOpeningOddsFromPayload(payload,source||"hook"))changed=true;
  // [FIX v6.9.9.83] NUNCA forçar finished só porque chegou /preodds|/x7|/grafic (usados em LIVE).
  // Só promove finished se:
  //  - já está finished (mantém sticky), OU
  //  - endpoint é claramente pós-jogo, OU
  //  - payload declara liveStatus=finished explicitamente
  const payloadStatus=String(payload?.liveStatus||payload?.status||"").toLowerCase();
  const explicitFinishedPayload=payloadStatus==="finished"||payloadStatus==="ft"||payloadStatus==="fulltime";
  if(state.liveStatus==="finished"){
    // mantém sticky, sem reaplicar
  } else if(isPostMatchOnlyEndpoint(url) || explicitFinishedPayload){
    // Só aplica finished se NÃO houver evidência viva recente no estado
    const recentLive=state.liveStatus==="live" && state.lastUpdate && (Date.now()-Number(state.lastUpdate))<120000;
    if(!recentLive){
      if(applyMatchStatus("finished",source||"historical"))changed=true;
    }
  }
  rebuildHistoricalCoverage();
  return changed;
}

function classifyDataMode(status){
  if(status==="live")return"live";
  if(status==="finished")return"historical";
  if(status==="not_started"||status==="scheduled")return"scheduled";
  return state.dataMode==="historical"?"historical":"unknown";
}
function applyMatchStatus(status,source){
  if(!status)return false;
  const next=String(status).toLowerCase();
  if(!["live","finished","not_started","scheduled","cancelled","unknown"].includes(next))return false;
  const prev=state.liveStatus;
  // [FIX v6.9.9.83] finished→live PERMITIDO quando a fonte DOM/hook traz evidência viva.
  // O lock antigo impedia recuperação após falso-positivo de finished (preodds/FT em sidebar).
  if(prev==="finished" && next==="live"){
    const src=String(source||"");
    // Só aceita upgrade se vier de captura DOM (relógio real) ou force explícito
    if(src!=="dom" && src!=="force" && src!=="manual"){
      state.diagnostics.blockedFinishedToLive=(state.diagnostics.blockedFinishedToLive||0)+1;
      return false;
    }
    state.diagnostics.recoveredLiveFromFinished=(state.diagnostics.recoveredLiveFromFinished||0)+1;
  }
  // Não degrada live→finished a partir de fontes fracas (network/historical sem declaração explícita)
  if(prev==="live" && next==="finished"){
    const src=String(source||"");
    if(src==="historical"||src==="network"){
      state.diagnostics.blockedLiveToFinished=(state.diagnostics.blockedLiveToFinished||0)+1;
      return false;
    }
  }
  if(prev!==next){
    if(prev && prev!=="inactive" && next!=="unknown") state.diagnostics.statusCorrections++;
    state.liveStatus=next;
  }
  const mode=classifyDataMode(next);
  if(mode!==state.dataMode) state.dataMode=mode;
  if(mode==="historical" && prev!=="finished") state.diagnostics.historicalSessions++;
  return prev!==next;
}
// AURA_QUANT_X MAXFIX: serialize snapshot merges to prevent concurrent state mutation.
let __mergeQueue = Promise.resolve();
let __mergeSeq = 0;
function enqueueMergeSnapshot(task) {
  const seq = ++__mergeSeq;
  const run = async () => {
    try {
      return await task(seq);
    } catch (error) {
      console.error("[AURA][MERGE]", { seq, error });
      throw error;
    }
  };
  const result = __mergeQueue.then(run, run);
  __mergeQueue = result.catch(() => {});
  return result;
}

function mergeSnapshot(payload,source){
 if(!payload||typeof payload!=="object")return false;
 const now=Date.now();const fid=payload.fixtureId?String(payload.fixtureId):null;
 if(fid&&!state.fixtureId)state.fixtureId=fid;
 if(fid&&state.fixtureId&&fid!==String(state.fixtureId)){addError(`snapshot rejeitado: fixture ${fid} != ${state.fixtureId}`);return false}
 if(!fid&&state.fixtureId&&payload.home&&payload.away&&state.home&&state.away){
   const ph=String(payload.home).trim().toLowerCase(), pa=String(payload.away).trim().toLowerCase();
   if(ph!==state.home.toLowerCase() || pa!==state.away.toLowerCase()){state.diagnostics.staleSnapshots++;return false}
 }
 if(payload.url)state.url=String(payload.url);
 const teamsChanged=mergeTeams(payload);let changed=teamsChanged;
 if(payload.players){try{mergePlayersPayload(payload.players,source);changed=true;}catch{}}
 if(finite(payload.minute)){const c=normalizeClock(payload.minute,payload.extraMinute||0);if(c){const oldM=state.minute??-1,oldExtra=state.extraMinute||0;if(state.minute!=null&&(c.minute<oldM-3||(c.minute===oldM&&c.extraMinute<oldExtra-2))){state.diagnostics.staleSnapshots++;}else if(c.minute!==oldM||c.extraMinute!==oldExtra){state.minute=c.minute;state.extraMinute=c.extraMinute;changed=true;}}}
 // Preserve FT display metadata for finished matches (last live minute may be 83' freeze)
 if(payload.clockDisplay){state.clockDisplay=String(payload.clockDisplay);}
 if(payload.lastLiveMinute!=null&&Number.isFinite(Number(payload.lastLiveMinute))){state.lastLiveMinute=Number(payload.lastLiveMinute);state.lastLiveExtra=Number(payload.lastLiveExtra||0)||0;}
 if(state.liveStatus==="finished"||state.dataMode==="historical"){state.clockDisplay=state.clockDisplay||"FT";}
 if(validScore(payload.score)){const sc={home:Number(payload.score.home),away:Number(payload.score.away)};if(JSON.stringify(state.score)!==JSON.stringify(sc)){state.score=sc;changed=true}}
 for(const k of STAT_KEYS){
  if(!Object.prototype.hasOwnProperty.call(payload,k)||payload[k]==null)continue;
  const normalized=normalizeSemanticPair(k,payload[k]);
  if(!normalized)continue;
  const h=normalized.home,a=normalized.away;
  if(h==null&&a==null)continue;
  if((h!=null&&h<0)||(a!=null&&a<0)){state.diagnostics.rejectedStats++;continue;}
  if(k==="xg"&&((h!=null&&h>PARAMS.maxXGPerTeam)||(a!=null&&a>PARAMS.maxXGPerTeam))){state.diagnostics.rejectedStats++;continue;}
  if((k==="attacks"||k==="dangerous")&&state.minute>0){
    const peak=Math.max(h??0,a??0),cap=k==="attacks"?PARAMS.maxAttacksPerMinute:PARAMS.maxDangerousPerMinute;
    if(peak/state.minute>cap){state.diagnostics.rejectedStats++;continue;}
  }
  if(mergeCanonicalStat(k,normalized,source,now))changed=true;
}
 // Explicit stat classification from content (UNKNOWN/ZERO/MISSING/RECOVERED/CONFIRMED)
 if(payload.charts&&typeof payload.charts==="object"){
  const c=payload.charts;
  const prev=state.charts&&typeof state.charts==="object"?state.charts:{schema:"cornerai-charts-1",tabs:[],series:[],pressureBars:{},history:[],lastCaptureAt:0};
  const tabs=Array.isArray(c.tabs)?c.tabs.slice(0,20):prev.tabs||[];
  const inSeries=Array.isArray(c.series)?c.series:[];
  const prevSeries=Array.isArray(prev.series)?prev.series:[];
  const series=(inSeries.length>=prevSeries.length?inSeries:prevSeries).slice(0,400);
  const inPress=c.pressureBars&&typeof c.pressureBars==="object"?c.pressureBars:{};
  const prevPress=prev.pressureBars&&typeof prev.pressureBars==="object"?prev.pressureBars:{};
  const pressureBars=Object.keys(inPress).length>=Object.keys(prevPress).length?inPress:prevPress;
  const pressureIntervals=Math.max(
    Object.keys(pressureBars||{}).length,
    Number(c.pressureIntervals||0)||0,
    Number(prev.pressureIntervals||0)||0,
    (Array.isArray(series)?series:[]).filter(s=>s&&s.series==="pressure").length
  );
  const activeId=c.activeId||prev.activeId||null;
  const histEntry={activeId,seriesCount:Math.max(series.length,pressureIntervals),pressureIntervals,tabs:tabs.map(t=>t.id||t),at:Date.now()};
  const history=[...(Array.isArray(prev.history)?prev.history:[]),histEntry].slice(-40);
  const netUrls=Array.isArray(c.networkUrls)?c.networkUrls:(prev.networkUrls||[]);
  state.charts={schema:"cornerai-charts-1",activeId,activeLabel:c.activeLabel||prev.activeLabel||null,tabs,series,seriesCount:Math.max(series.length,pressureIntervals),pressureIntervals,pressureBars,networkUrls:netUrls,signals:c.signals||prev.signals||{},history,lastCaptureAt:Date.now()};
  try{recoverFixtureFromCharts();}catch{}
  // Alimenta timeline de pressão para velas a partir de pressureBars
  try{
    const pressMap={};
    const clockMin=Number(state.minute);
    const hasClock=Number.isFinite(clockMin)&&clockMin>=0;
    for(const [k,v] of Object.entries(pressureBars||{})){
      if(!v||v.empty) continue;
      const im=String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
      if(!im) continue;
      const start=Number(im[1]), end=Number(im[2]);
      // Intervalos futuros (ainda não jogados)
      if(hasClock&&start>clockMin) continue;
      let h=Number(v.home),a=Number(v.away),pct=Number(v.pct);
      // Preferir pct oficial; nunca derivar ratio se um lado for 0 (residual DOM)
      if(Number.isFinite(pct)&&pct>=0&&pct<=100){
        h=pct;
        a=Number((100-pct).toFixed(1));
      } else if(Number.isFinite(h)&&Number.isFinite(a)&&h>0&&a>0&&(h>100||a>100||(h<=1.5&&a<=1.5))){
        const ssum=h+a; h=Number(((h/ssum)*100).toFixed(1)); a=Number(((a/ssum)*100).toFixed(1));
      }
      if(!Number.isFinite(h)||!Number.isFinite(a)) continue;
      if(h===0&&a===0) continue;
      // Qualquer lado zero = residual inválido (ex.: 72%×0%)
      if((h===0&&a>0)||(a===0&&h>0)) continue;
      // Intervalos futuros
      if(hasClock&&start>clockMin) continue;
      pressMap[im[1]+"-"+im[2]]={home:h,away:a};
    }
    if(Object.keys(pressMap).length){
      const minute=Number(state.minute)||0;
      const period=minute<=45?1:2;
      const point={
        fixtureId:state.fixtureId,period,minute,extraMinute:Number(state.extraMinute)||0,
        timestamp:Date.now(),source:"charts-pressure",pressure:pressMap
      };
      const arr=Array.isArray(state.cornerIndicatorTimeline)?state.cornerIndicatorTimeline:[];
      const key=`${period}|${minute}|${point.extraMinute}|charts-pressure`;
      const idx=arr.findIndex(x=>`${x.period}|${x.minute}|${x.extraMinute||0}|${x.source||""}`===key);
      if(idx>=0) arr[idx]=point; else arr.push(point);
      state.cornerIndicatorTimeline=arr.slice(-1500);
      rebuildChartData();
    }
    if(netUrls.some(u=>/m[24]\.sokkerpro|\/x7\b|wss:\/\//i.test(String(u||"")))){
      state.diagnostics.networkResponses=(state.diagnostics.networkResponses||0)+1;
      state.sources.network={lastUpdate:Date.now(),count:(state.sources.network?.count||0)+1};
    }
  }catch{}
 }
 if(payload.statMeta&&typeof payload.statMeta==="object"){
   const nextStatus=state.statStatus&&typeof state.statStatus==="object"?{...state.statStatus}:{};
   const rank={UNKNOWN:0,MISSING:1,ZERO:2,RECOVERED:3,CONFIRMED:4};
   for(const [k,meta] of Object.entries(payload.statMeta)){
     if(!meta||typeof meta!=="object")continue;
     const status=String(meta.status||"UNKNOWN").toUpperCase();
     if(!["UNKNOWN","ZERO","MISSING","RECOVERED","CONFIRMED"].includes(status))continue;
     const prev=nextStatus[k];
     const prevRank=rank[String(prev?.status||"UNKNOWN").toUpperCase()]||0;
     const nextRank=rank[status]||0;
     // Never downgrade CONFIRMED/RECOVERED to MISSING/UNKNOWN from a empty/partial DOM pass.
     // Keep last good values and mark as RECOVERED when the live DOM no longer exposes them.
     if(prev&&prevRank>=3&&nextRank<=1){
       nextStatus[k]={
         ...prev,
         status:"RECOVERED",
         confidence:Math.min(Number(prev.confidence)||0.7,0.75),
         method:String(prev.method||"")+"|stale-dom",
         lastMissingAt:now,
         updatedAt:prev.updatedAt||now
       };
       state.diagnostics.unknownStatsRecovered=(state.diagnostics.unknownStatsRecovered||0)+1;
       continue;
     }
     // Prefer non-null values over null when ranks are equal-ish.
     const incomingNull=(meta.home==null&&meta.away==null);
     if(prev && incomingNull && (prev.home!=null || prev.away!=null) && nextRank<=prevRank){
       continue;
     }
     nextStatus[k]={
       status,
       home:meta.home??null,
       away:meta.away??null,
       confidence:Number(meta.confidence)||0,
       source:String(meta.source||source),
       method:String(meta.method||""),
       conflict:meta.conflict||null,
       updatedAt:now
     };
     if(status==="RECOVERED") state.diagnostics.unknownStatsRecovered=(state.diagnostics.unknownStatsRecovered||0)+1;
     if(status==="MISSING"||status==="UNKNOWN") state.capture.unknownStatCache[k]=(state.capture.unknownStatCache[k]||0)+1;
   }
   state.statStatus=nextStatus;
 }
 if(payload.xgMeta&&typeof payload.xgMeta==="object") {
   const xh=Number(payload.xgMeta.home), xa=Number(payload.xgMeta.away);
   if(Number.isFinite(xh)&&Number.isFinite(xa)&&xh>=0&&xa>=0&&xh<=PARAMS.maxXGPerTeam&&xa<=PARAMS.maxXGPerTeam){
     const conf=Number(payload.xgMeta.confidence);
     const prev=state.xgProvenance;
     const incomingZero=xh===0&&xa===0;
     const prevNonZero=prev&&(Number(prev.home)>0||Number(prev.away)>0);
     const method=String(payload.xgMeta.method||"unknown");
     // Reject zero xG from weak indicator paths when a stronger non-zero value exists.
     if(incomingZero&&prevNonZero&&/indicator/i.test(method)){
       state.diagnostics.rejectedStats=(state.diagnostics.rejectedStats||0)+1;
     } else if(incomingZero&&prevNonZero&&Number.isFinite(conf)&&conf<Number(prev.confidence||0)){
       state.diagnostics.rejectedStats=(state.diagnostics.rejectedStats||0)+1;
     } else {
       state.xgProvenance={
         home:xh,away:xa,
         source:String(payload.xgMeta.source||source),
         confidence:Number.isFinite(conf)?Math.max(0,Math.min(1,conf)):sourceBaseConfidence(source),
         method:method,
         candidateCount:Number(payload.xgMeta.candidateCount||0),
         candidates:Array.isArray(payload.xgMeta.candidates)?payload.xgMeta.candidates.slice(0,5):[],
         conflict:payload.xgMeta.conflict||null,
         rawHome:payload.xgMeta.rawHome??payload.xgMeta.raw?.home??xh,
         rawAway:payload.xgMeta.rawAway??payload.xgMeta.raw?.away??xa,
         previous:prev?{home:prev.home,away:prev.away,method:prev.method,confidence:prev.confidence}:null,
         updatedAt:now
       };
       if(payload.xgMeta.conflict) state.diagnostics.sourceConflicts=(state.diagnostics.sourceConflicts||0)+1;
     }
   }
 }
 if(payload.extendedStats&&typeof payload.extendedStats==="object"){
  const next={...state.extendedStats};
  for(const [key,val] of Object.entries(payload.extendedStats).slice(0,EXTENDED_STAT_LIMIT)){
    if(!val||typeof val!=="object")continue;
    const label=String(val.label||key).replace(/\s+/g," ").trim();
    const semanticKey=key+" "+label;
    const normalized=normalizeSemanticPair(/xg|expected.?goals/i.test(semanticKey)?"xg":key,val);
    const h=normalized?.home??null,a=normalized?.away??null;
    if(h==null&&a==null)continue;
    if(/^\d+(?:\+\d+)?['′]?$/.test(label)||/odds|odd|cot[aã]ção|quota|1x2|play with responsibility|responsibility|mercado/i.test(label))continue;
    if(/[=|]{2,}/.test(label))continue;
    if(!state.extendedStats[key])state.diagnostics.unknownStatsRecovered++;
    next[key]={label:label.slice(0,100),home:h,away:a,source:String(val.source||source),timestamp:Number(val.timestamp)||Date.now()};
  }
  state.extendedStats=next;state.diagnostics.extendedStats=Object.keys(next).length;
  changed=true;
}
// Promote an explicitly labelled extended row into the canonical schema when the
// fixed extractor missed it. This preserves every provider-published parameter.
for(const [ek,ev] of Object.entries(state.extendedStats||{})){
  const label=String(ev.label||ek).toLowerCase();
  const aliases={offsides:/impedimento|offside/,red:/cart[aã]o vermelho|vermelho|red card/,subs:/substitui[cç][aã]o|substitution|substituicoes/,passesFailed:/passes errados|passes falhados|passes incompletos|inaccurate passes|failed passes|misplaced passes/};
  for(const [canon,rx] of Object.entries(aliases)) if(rx.test(label) && state.stats[canon]?.home==null && state.stats[canon]?.away==null){state.stats[canon]={home:ev.home,away:ev.away};state.diagnostics.canonicalRecovered++;changed=true;}
}
const derived=Array.isArray(payload.matchEvents)?payload.matchEvents:(Array.isArray(payload.cornerEvents)?payload.cornerEvents:[]);const added=mergeEvents(derived,source);if(added)changed=true; if(Array.isArray(payload.historicalTextEvents)&&payload.historicalTextEvents.length){state.historicalTextEvents=payload.historicalTextEvents.slice(-1000);changed=true;} if(payload.cornerIndicators&&finite(payload.minute)){if(recordCornerIndicatorSnapshot(payload.cornerIndicators,payload.minute,payload.extraMinute||0,payload.period,source))changed=true;}
 const clock=normalizeClock(payload.minute,payload.extraMinute||0); const oddsAdded=recordOdds(payload.odds,source,clock); if(oddsAdded)changed=true;
 state.sources[source].lastUpdate=now;state.sources[source].count++;state.lastUpdate=now;state.snapshotCount++;state.capture.acceptedSnapshots=Number(state.capture.acceptedSnapshots||0)+1;state.lastSnapshotSource=source;state.capture.lastPayloadAt=now;if(changed)state.capture.lastChangedAt=now;
 if(payload.liveStatus)applyMatchStatus(payload.liveStatus,source); else if(!state.liveStatus||state.liveStatus==="inactive") applyMatchStatus("unknown",source);
 // [FIX v6.9.9.83] Promote unknown→finished ONLY with explicit DOM evidence (não dataMode residual)
 // Se o payload traz minuto vivo + liveStatus live, nunca promove finished.
 const payloadIsLive = String(payload.liveStatus||"")==="live" || (Number.isFinite(Number(payload.minute)) && Number(payload.minute)>=0 && Number(payload.minute)<=130 && payload.liveStatus!=="finished");
 if(payloadIsLive && payload.liveStatus==="live"){
   applyMatchStatus("live",source);
 } else if((state.liveStatus==="unknown"||state.liveStatus==="inactive")&&payload.liveStatus==="finished"&&source==="dom"){
   applyMatchStatus("finished",source);
 }
 // dataMode residual NÃO força finished se o payload atual diz live
 if(state.dataMode==="historical"&&payload.liveStatus==="live"){
   applyMatchStatus("live",source);
 } else if(state.dataMode==="historical"&&payload.liveStatus!=="live"&&state.liveStatus!=="finished"&&state.liveStatus!=="live"&&source==="dom"&&payload.clockDisplay==="FT"){
   applyMatchStatus("finished",source);
 }
 state.dataMode=classifyDataMode(state.liveStatus); if(state.dataMode==="historical") state.diagnostics.historicalSnapshots++;
 const snapshotMinute=clock?.minute??(Array.isArray(payload.matchEvents)&&payload.matchEvents.length?Math.max(...payload.matchEvents.map(e=>Number(e.minute)||0)):null); if(snapshotMinute!=null) recordStatSnapshot(snapshotMinute,source,clock?.extraMinute||0,payload.period||(state.liveStatus==="finished"?2:null)); else if(state.liveStatus==="finished" && Object.values(state.stats||{}).some(v=>v?.home!=null||v?.away!=null)) recordStatSnapshot(90,source,0,2);
 // MAXIMIZE: recover MISSING cumulative stats from matchEvents when DOM hides zero-rows
try{ recoverMissingStatsFromEvents(); }catch{}
const buildAI=__cornerShouldBuildAI(payload);if(buildAI){state.intelligence=buildIntelligenceFeatures();state.aiFeed=buildAIFeed();state.analyst=buildAnalystFeed();enqueueAnalystOutbox(state.analyst,"state-update");state.diagnostics.aiFeatureBuilds=Number(state.diagnostics.aiFeatureBuilds||0)+1;}rebuildQuality();if(changed){awaitPersist()}else{broadcast()}return changed
}

function recoverMissingStatsFromEvents(){
  const events=Array.isArray(state.matchEvents)?state.matchEvents:[];
  const counts={offsides:{home:0,away:0},red:{home:0,away:0},subs:{home:0,away:0},yellow:{home:0,away:0}};
  for(const e of events){
    const t=String(e.type||e.kind||"").toLowerCase();
    const label=String(e.label||e.name||"").toLowerCase();
    const side=e.side==="away"?"away":(e.side==="home"?"home":null);
    if(!side) continue;
    if(t.includes("offside")||t.includes("impedimento")||/impedimento|offside/.test(label)) counts.offsides[side]++;
    else if(t.includes("red")||t.includes("vermelho")||t.includes("expuls")||/vermelho|red card|expuls/.test(label)) counts.red[side]++;
    else if(t.includes("sub")||t.includes("substit")||t.includes("troca")||/substitui|substitution/.test(label)) counts.subs[side]++;
    else if(t.includes("yellow")||t.includes("amarelo")||/amarelo|yellow/.test(label)) counts.yellow[side]++;
  }
  const status=state.statStatus&&typeof state.statStatus==="object"?{...state.statStatus}:{};
  let recovered=0;
  const mark=(key,home,away,method,confidence=0.72)=>{
    if(!state.stats) state.stats={};
    const cur=state.stats[key];
    const st=String(status[key]?.status||"").toUpperCase();
    if(st==="CONFIRMED") return;
    const hasDom=Number.isFinite(Number(cur?.home))||Number.isFinite(Number(cur?.away));
    if(hasDom && st==="CONFIRMED") return;
    const nextHome=hasDom && Number.isFinite(Number(cur?.home)) ? Math.max(Number(cur.home), home) : home;
    const nextAway=hasDom && Number.isFinite(Number(cur?.away)) ? Math.max(Number(cur.away), away) : away;
    if(state.stats[key]?.home===nextHome && state.stats[key]?.away===nextAway && st==="RECOVERED") return;
    state.stats[key]={home:nextHome,away:nextAway};
    status[key]={status:"RECOVERED",home:nextHome,away:nextAway,confidence,source:"derived",method,updatedAt:Date.now()};
    recovered++;
  };
  for(const key of Object.keys(counts)){
    const c=counts[key];
    const cur=state.stats?.[key];
    const hasDom=Number.isFinite(Number(cur?.home))||Number.isFinite(Number(cur?.away));
    const st=String(status[key]?.status||"").toUpperCase();
    if(hasDom && st==="CONFIRMED") continue;
    if(c.home===0 && c.away===0 && hasDom) continue;
    if(c.home>0 || c.away>0 || !hasDom){
      mark(key, c.home, c.away, "matchEvents-count", 0.72);
    }
  }
  // [v6.9.9.83] shots = shotsOn + shotsOff quando total está MISSING
  try{
    const on=state.stats?.shotsOn, off=state.stats?.shotsOff;
    const shots=state.stats?.shots;
    const shotsSt=String(status.shots?.status||"").toUpperCase();
    if((!shots || shotsSt==="MISSING" || shotsSt==="UNKNOWN") && on && off){
      const onH=Number(on.home), onA=Number(on.away), offH=Number(off.home), offA=Number(off.away);
      if([onH,onA,offH,offA].every(Number.isFinite)){
        mark("shots", onH+offH, onA+offA, "shotsOn+shotsOff", 0.85);
      }
    }
  }catch{}
  // extendedStats → canonical aliases
  try{
    const aliases={
      offsides:/impedimento|offside/,
      subs:/substitui|substitution|trocas/,
      crosses:/cruzamento|crosses?/,
      passes:/passes?\s*(certos?|completos?)|accurate\s*passes|completed\s*passes/,
      passesFailed:/passes?\s*(errados?|falhados?|incompletos?)|inaccurate|failed\s*passes/,
      shots:/total\s*(de\s*)?(chutes?|finaliza)|total\s*shots/,
      saves:/defesas?|saves?/
    };
    for(const [ek,ev] of Object.entries(state.extendedStats||{})){
      const label=String(ev.label||ek).toLowerCase();
      for(const [canon,rx] of Object.entries(aliases)){
        if(!rx.test(label)) continue;
        const st=String(status[canon]?.status||"").toUpperCase();
        if(st==="CONFIRMED"||st==="RECOVERED") continue;
        if(ev.home==null&&ev.away==null) continue;
        mark(canon, Number(ev.home)||0, Number(ev.away)||0, "extendedStats-alias", 0.7);
      }
    }
  }catch{}
  if(recovered){
    state.statStatus=status;
    state.diagnostics.unknownStatsRecovered=(state.diagnostics.unknownStatsRecovered||0)+recovered;
    state.diagnostics.canonicalRecovered=(state.diagnostics.canonicalRecovered||0)+recovered;
  }
}

function normalizeMenuPayload(p){
 if(!p||typeof p!=="object"||!p.url)return null;
 let u;try{u=new URL(String(p.url),state.url||"https://sokkerpro.com/");}catch{return null}
 if(!/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(u.href))return null;
 const menuId=String(p.menuId||"unknown").slice(0,60), pageKey=String(p.pageKey||u.pathname+u.search).slice(0,300);
 const text=String(p.text||"").slice(0,PARAMS.menuMaxText);
 const tables=Array.isArray(p.tables)?p.tables.slice(0,80).map(t=>({...t,rows:Array.isArray(t.rows)?t.rows.slice(0,PARAMS.menuMaxTableRows):[]})):[];
 const odds=Array.isArray(p.odds)?p.odds.slice(0,PARAMS.menuMaxOdds):[];
 return {version:String(p.version||VERSION),fixtureId:p.fixtureId?String(p.fixtureId):state.fixtureId,url:u.href,title:String(p.title||"").slice(0,300),timestamp:Number(p.timestamp)||Date.now(),menuId,menuLabel:String(p.menuLabel||"").slice(0,120),pageKey,activeMenu:p.activeMenu||null,menus:Array.isArray(p.menus)?p.menus.slice(0,120):[],headings:Array.isArray(p.headings)?p.headings.slice(0,300):[],text,textLength:text.length,tables,charts:Array.isArray(p.charts)?p.charts.slice(0,120):[],cards:Array.isArray(p.cards)?p.cards.slice(0,500):[],links:Array.isArray(p.links)?p.links.slice(0,120):[],buttons:Array.isArray(p.buttons)?p.buttons.slice(0,500):[],aria:Array.isArray(p.aria)?p.aria.slice(0,800):[],odds,jsonLd:Array.isArray(p.jsonLd)?p.jsonLd.slice(0,20):[]};
}
function mergeMenuSnapshot(payload,sender){
 const p=normalizeMenuPayload(payload);if(!p)return false;
 if(sender?.tab?.id!=null && !state.capture.activeTabId)state.capture.activeTabId=sender.tab.id;
 if(p.fixtureId&&state.fixtureId&&String(p.fixtureId)!==String(state.fixtureId)){state.diagnostics.foreignFixturePayloads++;return false;}
 const key=`${p.menuId}|${p.pageKey}`;const raw=JSON.stringify(p);const h=hashString(raw);
 if(h===state.menuCapture.lastHash){state.diagnostics.menuDuplicates++;return false;}
 state.menuCapture.lastHash=h;state.menuCapture.lastCaptureAt=Date.now();state.menuCapture.current=p;state.menuCapture.dataPoints=Number(state.menuCapture.dataPoints||0)+p.text.length+p.tables.reduce((n,t)=>n+(t.rows?.length||0),0)+p.odds.length;
 state.menuCapture.menus[key]=p;state.menuCapture.history=[...(state.menuCapture.history||[]),{key,menuId:p.menuId,label:p.menuLabel,url:p.url,timestamp:p.timestamp,textLength:p.text.length,tables:p.tables.length,odds:p.odds.length}].slice(-200);
 state.menuCapture.uniqueMenus=Object.keys(state.menuCapture.menus).length;state.diagnostics.menuSnapshots++;state.diagnostics.menuBytes+=raw.length;
 if(Array.isArray(p.menus)){const existing=new Map((state.menuCapture.discovered||[]).map(x=>[`${x.id}|${x.href}`,x]));for(const m of p.menus)if(m?.href)existing.set(`${m.id}|${m.href}`,m);state.menuCapture.discovered=[...existing.values()].slice(0,500);state.diagnostics.menuDiscoveries=state.menuCapture.discovered.length;}
 // Odds capturadas no menu ODDS/PRÉ-ODDS → histórico de precificação
 if(Array.isArray(p.odds)&&p.odds.length){
   const clock={minute:Number(state.minute)||null,extraMinute:Number(state.extraMinute)||0};
   const quotes=p.odds.map(o=>({
     market:o.market||o.marketName||"Mercado",
     marketType:o.marketType||null,
     selection:o.selection||o.outcome||"",
     line:o.line??null,
     bookmaker:o.bookmaker||"SokkerPRO",
     odds:Number(o.odds??o.odd??o.price),
     minute:clock.minute,
     extraMinute:clock.extraMinute,
     period:clock.minute!=null&&clock.minute>45?2:1,
     source:"menu"
   })).filter(q=>Number.isFinite(q.odds)&&q.odds>=1.01);
   if(quotes.length) recordOdds(quotes,"menu",clock);
 }
 return true;
}
function hashString(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16)}

let persistQueue=Promise.resolve();
let persistTimer=null;
let persistWaiters=[];
let persistInFlight=false;

function compactStateForStorage(reason){
  try{
    const st = state || {};
    const caps = {
      statTimeline: 240,
      statChangeEvents: 240,
      metricEvents: 400,
      unifiedTimeline: 400,
      cornerContexts: 120,
      cornerIndicatorTimeline: 120,
      oddsHistory: 180,
      oddsChanges: 180,
      marketExpectations: 80,
      historicalTextEvents: 80,
      diagTimeline: 80,
      healthSamples: 40,
      integrityHistory: 40,
      outbox: Number(PARAMS.outboxMax||120),
      menuHistory: 20,
      chartsHistory: 8,
      teamHistoryHome: 30,
      teamHistoryAway: 30,
      cornerEvents: 80,
      matchEvents: 120
    };
    const trimArr = (arr, n) => Array.isArray(arr) ? arr.slice(-n) : arr;
    st.statTimeline = trimArr(st.statTimeline, caps.statTimeline);
    st.statChangeEvents = trimArr(st.statChangeEvents, caps.statChangeEvents);
    st.metricEvents = trimArr(st.metricEvents, caps.metricEvents);
    st.unifiedTimeline = trimArr(st.unifiedTimeline, caps.unifiedTimeline);
    st.cornerContexts = trimArr(st.cornerContexts, caps.cornerContexts);
    st.cornerIndicatorTimeline = trimArr(st.cornerIndicatorTimeline, caps.cornerIndicatorTimeline);
    st.oddsHistory = trimArr(st.oddsHistory, caps.oddsHistory);
    st.oddsChanges = trimArr(st.oddsChanges, caps.oddsChanges);
    st.marketExpectations = trimArr(st.marketExpectations, caps.marketExpectations);
    st.historicalTextEvents = trimArr(st.historicalTextEvents, caps.historicalTextEvents);
    st.diagTimeline = trimArr(st.diagTimeline, caps.diagTimeline);
    st.healthSamples = trimArr(st.healthSamples, caps.healthSamples);
    st.integrityHistory = trimArr(st.integrityHistory, caps.integrityHistory);
    st.outbox = trimArr(st.outbox, caps.outbox);
    st.cornerEvents = trimArr(st.cornerEvents, caps.cornerEvents);
    st.matchEvents = trimArr(st.matchEvents, caps.matchEvents);
    if(st.menuCapture && typeof st.menuCapture === "object"){
      st.menuCapture.history = trimArr(st.menuCapture.history, caps.menuHistory);
      // menu text blobs are huge — keep only current + discovered ids
      if(st.menuCapture.menus && typeof st.menuCapture.menus === "object"){
        const keep = {};
        const ids = Object.keys(st.menuCapture.menus).slice(-12);
        for(const id of ids){
          const m = st.menuCapture.menus[id];
          if(!m || typeof m !== "object") continue;
          keep[id] = {
            id: m.id || id,
            title: m.title || null,
            capturedAt: m.capturedAt || null,
            dataPoints: m.dataPoints || 0,
            // drop heavy text/html tables from storage
            textLength: typeof m.text === "string" ? m.text.length : (m.textLength||0),
            tables: Array.isArray(m.tables) ? m.tables.length : (m.tableCount||0)
          };
        }
        st.menuCapture.menus = keep;
      }
    }
    if(st.charts && typeof st.charts === "object"){
      st.charts.history = trimArr(st.charts.history, caps.chartsHistory);
      // series arrays can be large — keep summary only if too big
      if(Array.isArray(st.charts.series) && st.charts.series.length > 40){
        st.charts.seriesCount = st.charts.series.length;
        st.charts.series = st.charts.series.slice(-40);
      }
    }
    if(st.teamHistory && typeof st.teamHistory === "object"){
      st.teamHistory.home = trimArr(st.teamHistory.home, caps.teamHistoryHome);
      st.teamHistory.away = trimArr(st.teamHistory.away, caps.teamHistoryAway);
    }
    if(st.aiFeed && typeof st.aiFeed === "object"){
      if(Array.isArray(st.aiFeed.events)) st.aiFeed.events = st.aiFeed.events.slice(-Number(PARAMS.aiFeedMaxEvents||800));
      if(Array.isArray(st.aiFeed.indicators)) st.aiFeed.indicators = st.aiFeed.indicators.slice(-Number(PARAMS.aiFeedMaxIndicators||400));
    }
    if(st.capture && typeof st.capture === "object"){
      st.capture.minuteKeys = trimArr(st.capture.minuteKeys, 180);
      st.capture.observedMinutes = trimArr(st.capture.observedMinutes, 120);
      st.capture.missingMinutes = trimArr(st.capture.missingMinutes, 60);
    }
    st.diagnostics = st.diagnostics || {};
    st.diagnostics.lastCompactAt = Date.now();
    st.diagnostics.lastCompactReason = reason || "manual";
    st.diagnostics.compactCount = (st.diagnostics.compactCount||0) + 1;
    return true;
  }catch(e){
    try{ addError("compact: "+(e?.message||e)); }catch{}
    return false;
  }
}

async function emergencyStoragePrune(){
  try{
    compactStateForStorage("STORAGE_NEAR_QUOTA");
    // Drop heavy non-essential keys in local storage besides cornerai_state
    const keys = await chrome.storage.local.get(null);
    const drop = [];
    for(const k of Object.keys(keys||{})){
      if(/^cornerai_ai_handoff$|^cornerai_gemini_v10_results$|^cornerai_skill_monitor$/.test(k)) drop.push(k);
      if(/^cd:|^cornerai_team_context$/.test(k)) {
        // keep team context but will be rewritten smaller
      }
    }
    if(drop.length) await chrome.storage.local.remove(drop);
    // Force immediate persist of compacted state
    await chrome.storage.local.set({cornerai_state: state});
    let bytes = null;
    try{ if(chrome.storage?.local?.getBytesInUse) bytes = await chrome.storage.local.getBytesInUse(null); }catch{}
    state.diagnostics = state.diagnostics || {};
    state.diagnostics.lastPruneBytes = bytes;
    state.diagnostics.lastPruneAt = Date.now();
    try{ logSW("WARNING","STORAGE_PRUNED","Storage compactado por cota",{bytes, reason:"STORAGE_NEAR_QUOTA"}); }catch{}
    return {ok:true, bytes};
  }catch(e){
    return {ok:false, error:e?.message||String(e)};
  }
}

function awaitPersist(options={}){
  const immediate=!!options.immediate;
  const delay=immediate?0:Math.max(40,Number(PARAMS.persistDebounceMs||250));
  return new Promise(resolve=>{
    persistWaiters.push(resolve);
    if(persistTimer)clearTimeout(persistTimer);
    persistTimer=setTimeout(()=>{
      persistTimer=null;
      if(persistInFlight)return;
      persistInFlight=true;
      const waiters=persistWaiters.splice(0);
      persistQueue=persistQueue.then(async()=>{
        try{
          // compactação leve contínua para evitar estouro de cota
          try{ compactStateForStorage("persist"); }catch{}
          await chrome.storage.local.set({cornerai_state:state});
          try{state.capture.persistQueueDepth=persistWaiters.length}catch{}
        }catch(e){
          state.diagnostics.persistErrors=(state.diagnostics.persistErrors||0)+1;
          addError("storage: "+(e?.message||e));
          // se falhou por quota, força prune agressivo e tenta 1x
          try{
            await emergencyStoragePrune();
            await chrome.storage.local.set({cornerai_state:state});
          }catch(e2){
            addError("storage-retry: "+(e2?.message||e2));
          }
        }
        try{await broadcast()}catch{}
      }).finally(()=>{
        persistInFlight=false;
        for(const done of waiters)try{done()}catch{}
        if(persistWaiters.length&&!persistTimer)persistTimer=setTimeout(()=>awaitPersist({}),Math.max(40,Number(PARAMS.persistDebounceMs||250)));
      });
    },delay);
  });
}
function broadcast(){
  // [FIX v6.9.9.75] Incrementa stateVersion em toda emissão de estado estável
  // para permitir que consumidores detectem snapshots obsoletos.
  state.stateVersion = (Number(state.stateVersion)||0) + 1;
  // Gemini WS: push rate-limited se socket aberto
  try{
    if(typeof CornerAIGeminiConnector!=="undefined" && CornerAIGeminiConnector.wsStatus){
      const st=CornerAIGeminiConnector.wsStatus();
      if(st && st.state==="open") CornerAIGeminiConnector.pushState(state, false);
      try{ postEventosFlask(false); }catch{}
    }
  }catch{}
  return new Promise(resolve=>{
    try{
      chrome.runtime.sendMessage({type:"STATE_UPDATE",state:clone(state)},()=>{
        void chrome.runtime.lastError;
        resolve();
      });
    }catch(e){ resolve(); }
  });
}
async function load(){try{const r=await chrome.storage.local.get("cornerai_state");if(r.cornerai_state){const old=r.cornerai_state,d=defaultState();if(String(old.version||"")!==VERSION){state=d;}else state={...d,...old,stats:{...d.stats,...old.stats},sources:{...d.sources,...old.sources},diagnostics:{...d.diagnostics,...old.diagnostics},provenance:old.provenance&&typeof old.provenance==="object"?old.provenance:d.provenance,intelligence:old.intelligence&&typeof old.intelligence==="object"?old.intelligence:d.intelligence,dataMode:old.dataMode||d.dataMode,captureMode:old.captureMode||d.captureMode,cornerEvents:Array.isArray(old.cornerEvents)?old.cornerEvents:[],matchEvents:Array.isArray(old.matchEvents)?old.matchEvents:[]};state.cornerEventCount=state.cornerEvents.length;state.eventCount=state.matchEvents.length;state.snapshotCount=Number(old.snapshotCount||0);state.statTimeline=Array.isArray(old.statTimeline)?old.statTimeline:[];state.statChangeEvents=Array.isArray(old.statChangeEvents)?old.statChangeEvents:buildStatChangeEvents(state.statTimeline);state.metricEvents=Array.isArray(old.metricEvents)?old.metricEvents:[];state.unifiedTimeline=Array.isArray(old.unifiedTimeline)?old.unifiedTimeline:[];state.eventSummary=old.eventSummary||d.eventSummary;state.cornerContexts=Array.isArray(old.cornerContexts)?old.cornerContexts:[];state.cornerIndicatorTimeline=Array.isArray(old.cornerIndicatorTimeline)?old.cornerIndicatorTimeline:[];state.oddsHistory=Array.isArray(old.oddsHistory)?old.oddsHistory:[];state.oddsChanges=Array.isArray(old.oddsChanges)?old.oddsChanges:[];state.oddsMarkets=old.oddsMarkets&&typeof old.oddsMarkets==="object"?old.oddsMarkets:{};state.marketExpectations=Array.isArray(old.marketExpectations)?old.marketExpectations:[];state.historicalTextEvents=Array.isArray(old.historicalTextEvents)?old.historicalTextEvents:[];state.extendedStats=old.extendedStats&&typeof old.extendedStats==="object"?old.extendedStats:{};state.oddsCount=state.oddsHistory.length;state.quality=old.quality||d.quality;state.teamHistory=old.teamHistory&&typeof old.teamHistory==="object"?old.teamHistory:{home:[],away:[]};state.menuCapture=old.menuCapture&&typeof old.menuCapture==="object"?old.menuCapture:d.menuCapture;state.menuCapture.menus=state.menuCapture.menus&&typeof state.menuCapture.menus==="object"?state.menuCapture.menus:{};state.menuCapture.discovered=Array.isArray(state.menuCapture.discovered)?state.menuCapture.discovered:[];state.menuCapture.history=Array.isArray(state.menuCapture.history)?state.menuCapture.history:[];rebuildTeamData(); rebuildMetricEvents(); rebuildOddsAnalytics(); rebuildQuality(); state.intelligence=buildIntelligenceFeatures(); state.aiFeed=buildAIFeed();state.analyst=buildAnalystFeed();enqueueAnalystOutbox(state.analyst,"state-update");state.captureHealth=buildCaptureHealth()}}catch(e){addError("load: "+e.message)}}
function endpointBelongsToFixture(url,fid){
 if(!url||!fid)return true;
 try{
   const u=new URL(String(url),state.url||"https://sokkerpro.com/");
   const wanted=String(fid);
   const path=decodeURIComponent(u.pathname||"");
   const full=path+(u.search||"");
   // [FIX v6.9.9.77] Rejeita livescores / team / season / competition sem fixture do jogo atual
   if(/livescores|\/ws\/livescores|\/team\/|\/season|\/competition\b|\/league\b/i.test(full) && !new RegExp("/(?:fixture|match|partida|game)/"+wanted+"(?:/|$)", "i").test(path)){
     state.diagnostics.foreignFixturePayloads=(state.diagnostics.foreignFixturePayloads||0)+1;
     return false;
   }
   for(const key of ["fixture","fixtureId","match","matchId","gameId"]){
     const value=u.searchParams.get(key);
     if(value!=null) return String(value)===wanted;
   }
   const m=path.match(/\/(?:fixture|match|partida|game)\/(\d+)(?:\/|$)/i);
   if(m) return String(m[1])===wanted;
   state.diagnostics.unknownEndpointMessages=(state.diagnostics.unknownEndpointMessages||0)+1;
   return true;
 }catch{
   return true;
 }
}

function computeH2HAverages(tables,text,seed={}){
  const out={...(seed&&typeof seed==="object"?seed:{})};
  const nums=s=>(String(s||"").match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(String(x).replace(",","."))).filter(Number.isFinite);
  const summarize=(arr)=>{
    const samples=arr.slice(-40).filter(Number.isFinite);
    if(!samples.length) return null;
    const n=samples.length;
    const avg=samples.reduce((a,b)=>a+b,0)/n;
    const variance=samples.reduce((a,b)=>a+Math.pow(b-avg,2),0)/n;
    const std=Math.sqrt(variance);
    // population-ish percentiles
    const sorted=samples.slice().sort((a,b)=>a-b);
    const q=(p)=>sorted[Math.min(n-1,Math.max(0,Math.floor(p*(n-1))))];
    return {
      avg:Number(avg.toFixed(3)),
      variance:Number(variance.toFixed(3)),
      std:Number(std.toFixed(3)),
      samples:n,
      min:Math.min(...samples),
      max:Math.max(...samples),
      p25:Number(q(0.25).toFixed(3)),
      p75:Number(q(0.75).toFixed(3))
    };
  };
  const push=(key,vals)=>{
    if(!vals||!vals.length)return;
    const prev=out[key]&&Array.isArray(out[key]._raw)?out[key]._raw:[];
    const arr=prev.concat(vals).slice(-40);
    const stats=summarize(arr);
    if(stats) out[key]={...stats,_raw:arr};
  };
  // Scan table rows for corner / goal related averages commonly shown in H2H panels.
  for(const t of (Array.isArray(tables)?tables:[])){
    const rows=Array.isArray(t.rows)?t.rows:[];
    for(const row of rows){
      const label=String(row[0]||"").toLowerCase();
      const values=nums(Array.isArray(row)?row.slice(1).join(" "):row);
      if(!values.length)continue;
      if(/escante|corner/.test(label)) push("corners",values);
      else if(/gol|goal|gols/.test(label)&&!/x\s*g|expected/.test(label)) push("goals",values);
      else if(/chute|shot|finaliz/.test(label)) push("shots",values);
      else if(/posse|possession/.test(label)) push("possession",values);
      else if(/ataque|attack/.test(label)) push("attacks",values);
      else if(/cart[aã]o|card|amarelo|yellow/.test(label)) push("cards",values);
      else if(/xg|expected/.test(label)) push("xg",values);
    }
  }
  // Lightweight text heuristics for "média de escanteios" style lines.
  const blob=String(text||"");
  const patterns=[
    [/m[eé]dia[^\n]{0,40}escante[^\n]{0,20}?(-?\d+(?:[.,]\d+)?)/ig,"corners"],
    [/m[eé]dia[^\n]{0,40}gol[^\n]{0,20}?(-?\d+(?:[.,]\d+)?)/ig,"goals"],
    [/avg[^\n]{0,20}corner[^\n]{0,20}?(-?\d+(?:[.,]\d+)?)/ig,"corners"]
  ];
  for(const [re,key] of patterns){
    let m; const found=[];
    while((m=re.exec(blob))){ const n=Number(String(m[1]).replace(",",".")); if(Number.isFinite(n)) found.push(n); }
    if(found.length) push(key,found);
  }
  // Enrich from structured H2H matches when present on state
  try{
    const matches=Array.isArray(state.h2h?.matches)?state.h2h.matches:(Array.isArray(state.h2h?.rows)?state.h2h.rows:[]);
    if(matches.length){
      const cH=[],cA=[],gH=[],gA=[],totalC=[],results=[];
      for(const m of matches.slice(0,30)){
        const a=Number(m.cornersHome??m.homeCorners??m.corners_home);
        const b=Number(m.cornersAway??m.awayCorners??m.corners_away);
        const gh=Number(m.homeGoals??m.homeScore??m.goalsHome);
        const ga=Number(m.awayGoals??m.awayScore??m.goalsAway);
        if(Number.isFinite(a)) cH.push(a);
        if(Number.isFinite(b)) cA.push(b);
        if(Number.isFinite(a)&&Number.isFinite(b)) totalC.push(a+b);
        if(Number.isFinite(gh)) gH.push(gh);
        if(Number.isFinite(ga)) gA.push(ga);
        if(Number.isFinite(gh)&&Number.isFinite(ga)) results.push(gh===ga?0:(gh>ga?1:-1));
      }
      if(cH.length) { const s=summarize(cH); if(s) out.cornersHome=s; }
      if(cA.length) { const s=summarize(cA); if(s) out.cornersAway=s; }
      if(totalC.length){ const s=summarize(totalC); if(s) out.cornersTotal=s; }
      if(gH.length){ const s=summarize(gH); if(s) out.goalsHome=s; }
      if(gA.length){ const s=summarize(gA); if(s) out.goalsAway=s; }
      // correlation: total corners vs result margin proxy (home goals - away goals)
      if(totalC.length>=4 && results.length>=4){
        const n=Math.min(totalC.length, results.length);
        const xs=totalC.slice(0,n), ys=results.slice(0,n);
        let sx=0,sy=0,sxx=0,syy=0,sxy=0;
        for(let i=0;i<n;i++){ sx+=xs[i]; sy+=ys[i]; sxx+=xs[i]*xs[i]; syy+=ys[i]*ys[i]; sxy+=xs[i]*ys[i]; }
        const den=Math.sqrt(Math.max(0,(n*sxx-sx*sx)*(n*syy-sy*sy)));
        const corr=den>1e-9?(n*sxy-sx*sy)/den:null;
        out.cornersResultCorr=corr==null?null:Number(corr.toFixed(3));
        // draw-heavy series tend to fewer corners — flag low mean when many draws
        const draws=ys.filter(v=>v===0).length;
        out.drawRate=Number((draws/n).toFixed(3));
        out.lowCornerDrawBias = (out.drawRate>=0.4 && (out.cornersTotal?.avg||0)<9) ? true : false;
      }
    }
  }catch{}
  // strip internal raw buffers from public averages (keep stats only)
  for(const k of Object.keys(out)){
    if(out[k]&&typeof out[k]==="object"&&out[k]._raw){
      const {_raw,...rest}=out[k];
      out[k]=rest;
    }
  }
  return out;
}


function computeTeamFormFactor(side){
  // Exponential form: weight 0.9^k on k-th previous game corner output vs baseline
  const cache=state.teamContextCache||{};
  const entry=side==="home"?cache.home:cache.away;
  const baseline=5.0;
  const series=Array.isArray(entry?.formCorners)?entry.formCorners.slice(-10):[];
  if(series.length>=2){
    let wsum=0, vsum=0, w=1;
    // most recent first
    for(let i=series.length-1;i>=0;i--){
      const v=Number(series[i]);
      if(!Number.isFinite(v)) continue;
      vsum += (v/baseline)*w;
      wsum += w;
      w *= 0.9;
    }
    if(wsum>0){
      const f=vsum/wsum;
      return Number(Math.max(0.85, Math.min(1.2, f)).toFixed(3));
    }
  }
  // fallback: attackFactor proximity to 1
  if(entry&&Number.isFinite(Number(entry.attackFactor))){
    const af=Number(entry.attackFactor);
    return Number(Math.max(0.85, Math.min(1.2, 0.5+0.5*af)).toFixed(3));
  }
  return 1.0;
}

function computeTeamAttackFactor(side){
  // Persistent prior from team cache + live rate vs league baseline (~5 corners/team game ~ 0.055/min)
  const name=side==="home"?state.home:state.away;
  const cache=state.teamContextCache||{};
  const entry=side==="home"?cache.home:cache.away;
  const baselineCorners=5.0;
  let factor=1.0;
  if(entry&&Number.isFinite(Number(entry.avgCorners))&&Number(entry.samples||0)>=3){
    factor = Number(entry.avgCorners)/baselineCorners;
  }
  if(entry&&Number.isFinite(Number(entry.attackFactor))){
    // blend stored attack factor (EMA history) with H2H-derived
    factor = 0.55*Number(entry.attackFactor) + 0.45*factor;
  }
  // live adjustment: corners per minute vs expected
  const minute=Math.max(1,Number(state.minute)||1);
  const corners=Number(state.stats?.corners?.[side]);
  if(Number.isFinite(corners)&&minute>=20){
    const liveRate=(corners/minute)*90; // projected full-match corners
    const liveF=liveRate/baselineCorners;
    factor = 0.7*factor + 0.3*Math.max(0.6,Math.min(1.6,liveF));
  }
  return Number(Math.max(0.7, Math.min(1.4, factor)).toFixed(3));
}

async function updateTeamAttackFactorsFromResult(){
  try{
    if(!state.fixtureId||!state.home||!state.away) return;
    if(!(state.liveStatus==="finished"||state.dataMode==="historical")) return;
    const cH=Number(state.stats?.corners?.home);
    const cA=Number(state.stats?.corners?.away);
    if(!Number.isFinite(cH)||!Number.isFinite(cA)) return;
    const baseline=5.0;
    const stored=await chrome.storage.local.get(["cornerai_team_context"]);
    const cache=stored.cornerai_team_context&&typeof stored.cornerai_team_context==="object"?stored.cornerai_team_context:{};
    const hk=teamKey(state.home), ak=teamKey(state.away);
    const ts=Date.now();
    for(const [key,name,corners] of [[hk,state.home,cH],[ak,state.away,cA]]){
      if(!key) continue;
      const prev=cache[key]||{name,samples:0};
      const obs=Number(corners)/baseline;
      const prevF=Number(prev.attackFactor||1);
      const samples=Number(prev.samples||0)+1;
      // exponential form weight ~0.9 per game on prior
      const attackFactor=Number((0.9*prevF + 0.1*Math.max(0.6,Math.min(1.6,obs))).toFixed(3));
      const avgCorners=prev.avgCorners!=null
        ? Number(((Number(prev.avgCorners)*Math.max(0,samples-1)+corners)/samples).toFixed(2))
        : Number(corners);
      // recent form series (corners per match), exponential use via computeTeamFormFactor
      const formCorners=Array.isArray(prev.formCorners)?prev.formCorners.slice(-9):[];
      formCorners.push(Number(corners));
      // form score snapshot (0.9 decay)
      let wsum=0,vsum=0,w=1;
      for(let i=formCorners.length-1;i>=0;i--){
        const v=Number(formCorners[i]); if(!Number.isFinite(v)) continue;
        vsum += (v/baseline)*w; wsum += w; w *= 0.9;
      }
      const formScore=wsum?Number(Math.max(0.85,Math.min(1.2,vsum/wsum)).toFixed(3)):1;
      cache[key]={...prev,name,avgCorners,attackFactor,formCorners,formScore,samples,lastCorners:corners,fixtureId:state.fixtureId,updatedAt:ts};
    }
    await chrome.storage.local.set({cornerai_team_context:cache});
    state.teamContextCache={
      home:cache[hk]||null,
      away:cache[ak]||null,
      h2h:state.teamContextCache?.h2h||null,
      size:Object.keys(cache).length
    };
    state.diagnostics.teamAttackFactorUpdates=(state.diagnostics.teamAttackFactorUpdates||0)+1;
  }catch(e){try{addError("attack-factor: "+(e?.message||e));}catch{}}
}

function sessionContextMatches(fixtureId,tabId){
  const fid=fixtureId==null?"":String(fixtureId);
  const activeFid=state.fixtureId==null?"":String(state.fixtureId);
  const activeTab=state.capture?.activeTabId??null;
  return !!fid && !!activeFid && fid===activeFid && activeTab!=null && Number(tabId)===Number(activeTab);
}
function rejectForeignSession(reason,fixtureId,tabId){
  state.diagnostics=state.diagnostics||{};
  if(fixtureId && state.fixtureId && String(fixtureId)!==String(state.fixtureId))
    state.diagnostics.foreignFixturePayloads=(state.diagnostics.foreignFixturePayloads||0)+1;
  if(tabId!=null && state.capture?.activeTabId!=null && Number(tabId)!==Number(state.capture.activeTabId))
    state.diagnostics.foreignTabPayloads=(state.diagnostics.foreignTabPayloads||0)+1;
  state.diagnostics.staleMessages=(state.diagnostics.staleMessages||0)+1;
  state.diagnostics.lastIsolationReject={reason:String(reason||"session_mismatch"),fixtureId:fixtureId?String(fixtureId):null,tabId:tabId??null,activeFixture:state.fixtureId?String(state.fixtureId):null,activeTab:state.capture?.activeTabId??null,at:Date.now()};
  return false;
}

function sessionContextMatches(fixtureId,tabId){
  const fid=fixtureId==null?"":String(fixtureId);
  const activeFid=state.fixtureId==null?"":String(state.fixtureId);
  const activeTab=state.capture?.activeTabId??null;
  return !!fid && !!activeFid && fid===activeFid && activeTab!=null && Number(tabId)===Number(activeTab);
}
function rejectForeignSession(reason,fixtureId,tabId){
  state.diagnostics=state.diagnostics||{};
  if(fixtureId && state.fixtureId && String(fixtureId)!==String(state.fixtureId))
    state.diagnostics.foreignFixturePayloads=(state.diagnostics.foreignFixturePayloads||0)+1;
  if(tabId!=null && state.capture?.activeTabId!=null && Number(tabId)!==Number(state.capture.activeTabId))
    state.diagnostics.foreignTabPayloads=(state.diagnostics.foreignTabPayloads||0)+1;
  state.diagnostics.staleMessages=(state.diagnostics.staleMessages||0)+1;
  state.diagnostics.lastIsolationReject={reason:String(reason||"session_mismatch"),fixtureId:fixtureId?String(fixtureId):null,tabId:tabId??null,activeFixture:state.fixtureId?String(state.fixtureId):null,activeTab:state.capture?.activeTabId??null,at:Date.now()};
  return false;
}

function acceptFixtureMessage(payload,source,sender,meta){
 state.diagnostics.lastMessageSource=String(source||"");
 state.diagnostics.lastMessageAt=Date.now();
 state.diagnostics.lastMessageFixture=payload?.fixtureId?String(payload.fixtureId):null;
 const fid=payload?.fixtureId?String(payload.fixtureId):null;
 // 9.2.1: normalize tab ids to Number — string/number mismatch was rejecting valid DOM_SNAPSHOT
 const tabId=sender?.tab?.id!=null?Number(sender.tab.id):null;
 const activeTab=state.capture?.activeTabId!=null?Number(state.capture.activeTabId):null;
 const activeFixture=state.fixtureId?String(state.fixtureId):null;

 // A session can only be established by an explicit reset/arm. Never let a
 // late DOM/hook/chart payload silently roll the session to another fixture.
 if(source==="dom" && !state.capture?.armed && !activeFixture && activeTab==null){
   if(tabId!=null) state.capture.activeTabId=tabId;
   const recovered=fid || extractFixtureIdFromPayload(payload,meta);
   if(recovered) state.fixtureId=String(recovered);
   return !!state.fixtureId;
 }
 // 9.2.2: if payload carries the same fixture already in session, accept even if
 // armed flags were lost after SW restart (manualConsent/armed may reset).
 if((!state.capture?.manualConsent || !state.capture?.armed)){
   const sameFix = fid && state.fixtureId && String(fid)===String(state.fixtureId);
   if(sameFix && source==="dom"){
     state.capture.armed=true;
     state.capture.manualConsent=true;
     if(tabId!=null) state.capture.activeTabId=tabId;
   } else {
     state.diagnostics.unarmedPayloads=(state.diagnostics.unarmedPayloads||0)+1;
     return false;
   }
 }
 if(tabId==null || !Number.isFinite(tabId)){
   state.diagnostics.missingSenderTab=(state.diagnostics.missingSenderTab||0)+1;
   return false;
 }
 if(activeTab==null || tabId!==activeTab){
   // 12.8.7: same fixture → sticky active tab. Só rebind se aba ativa sumiu
   // ou ainda não havia activeTab. Evita ping-pong entre abas e inflação de
   // foreignTab/tabRebinds quando o usuário abre 2+ abas do mesmo fixture.
   if(fid && activeFixture && fid===activeFixture){
     if(activeTab==null){
       state.capture.activeTabId=tabId;
     } else if(tabId!==activeTab){
       // Descarta snapshot de aba secundária sem contar como foreignFixture.
       // Conta secondaryTabDrop para diagnóstico (não polui foreignTab).
       state.diagnostics=state.diagnostics||{};
       state.diagnostics.secondaryTabDrops=(state.diagnostics.secondaryTabDrops||0)+1;
       return false;
     }
   } else if(activeTab==null && fid && !activeFixture){
     state.capture.activeTabId=tabId;
     state.fixtureId=String(fid);
   } else if(activeTab==null && fid && activeFixture && fid===activeFixture){
     state.capture.activeTabId=tabId;
   } else {
     rejectForeignSession("foreign_tab",fid,tabId);
     return false;
   }
 }
 if(activeFixture && fid && fid!==activeFixture){
   rejectForeignSession("foreign_fixture",fid,tabId);
   return false;
 }
 if(!state.fixtureId){
   const recovered=fid || extractFixtureIdFromPayload(payload,meta);
   if(recovered) state.fixtureId=String(recovered);
   else {
     state.diagnostics.missingFixturePayloads=(state.diagnostics.missingFixturePayloads||0)+1;
     return false;
   }
 }
 return true;
}
let stateLoaded=false;
let stateLoadPromise=null;
async function ensureStateLoaded(){
  if(stateLoaded)return;
  if(!stateLoadPromise){
    stateLoadPromise=(async()=>{
      try{await load();}catch(e){try{addError("state-load: "+(e?.message||e));}catch{}}
      try{await loadTeamContextForCurrentMatch();}catch{}
      try{await loadFeedbackStore();}catch{}
      try{await loadAlertPrefs();}catch{}
      try{await loadGeminiConfig();}catch{}
      try{await loadSkillMonitor();}catch{}
      stateLoaded=true;
    })();
  }
  await stateLoadPromise;
}
chrome.runtime.onInstalled.addListener(()=>{stateLoaded=false;stateLoadPromise=null;void ensureStateLoaded();});
chrome.runtime.onStartup.addListener(()=>{stateLoaded=false;stateLoadPromise=null;void ensureStateLoaded();});
let armGeneration=0;
let armQueue=Promise.resolve();
function withArmLock(task){
  const run=armQueue.then(task,task);
  armQueue=run.catch(()=>{});
  return run;
}

async function stopOtherSokkerTabs(activeTabId){
  try{
    const tabs=await chrome.tabs.query({});
    await Promise.all((tabs||[]).filter(t=>Number(t.id)>0 && Number(t.id)!==Number(activeTabId) && isSokkerUrl(t.url)).map(async t=>{
      try{ await chrome.tabs.sendMessage(t.id,{type:"STOP_CAPTURE"}); }catch{}
    }));
  }catch{}
}

async function _autoArmSokkerTab(tabId,url){
  if(!tabId || !(await isSokkerUrl(url))) return {ok:false,ignored:true};
  try{
    const ready=await ensureContentScript(tabId,url);
    if(!ready)return {ok:false,error:"content_script_unavailable"};
    const currentTab=Number(state.capture?.activeTabId);
    if(currentTab&&currentTab!==tabId){
      try{await chrome.tabs.sendMessage(currentTab,{type:"STOP_CAPTURE"})}catch{}
    }

    // A origem é a página atualmente visível. O contexto de captura é lido
    // diretamente do content script para não escolher outra partida.
    let ctx=null;
    try{ctx=await chrome.tabs.sendMessage(tabId,{type:"GET_CAPTURE_CONTEXT"});}catch{}
    const detectedFixture=String(ctx?.fixtureId||"");
    if(!ctx?.isFixturePage||!detectedFixture)return {ok:false,error:"no_fixture"};

    if(String(state.fixtureId||"")!==detectedFixture||currentTab!==tabId){
      state=defaultState();
      state.capture.activeTabId=tabId;
      state.capture.armed=true;
      state.capture.manualConsent=true;
      state.capture.sessionId=`${detectedFixture}:${tabId}:${Date.now().toString(36)}`;
      state.fixtureId=detectedFixture;
      state.url=String(url||"");
      state.lastUpdate=Date.now();
      await awaitPersist();
    }else{
      state.capture.activeTabId=tabId;
      state.capture.armed=true;
      state.capture.manualConsent=true;
      state.fixtureId=detectedFixture;
      state.url=String(url||state.url||"");
      await awaitPersist();
    }
    rememberSokkerTab(tabId);
    // Apenas a aba atualmente visível pode produzir snapshots. Isso elimina
    // produtores antigos de outras partidas e evita foreignTab contamination.
    void stopOtherSokkerTabs(tabId);

    const r=await chrome.tabs.sendMessage(tabId,{type:"AUTO_ARM_CAPTURE"});
    if(!r?.ok)return {ok:false,error:r?.error||"capture_arm_failed"};
    return {ok:true,tabId,fixtureId:detectedFixture,first:r.first||null};
  }catch(e){return {ok:false,error:e?.message||String(e)}}
}


async function autoArmSokkerTab(tabId,url){
  return withArmLock(async()=>{
    const generation=++armGeneration;
    const result=await _autoArmSokkerTab(tabId,url);
    // A newer arm operation owns the session. Never let an older operation
    // report/continue as if it were still authoritative.
    if(generation!==armGeneration) return {ok:false,stale:true,error:"stale_arm_operation"};
    return result;
  });
}

// A captura segue exclusivamente a partida que está na aba visível.
chrome.tabs.onUpdated.addListener((tabId,changeInfo,tab)=>{
  if(changeInfo.status==="complete" && tab?.url){
    void ensureContentScript(tabId,tab.url);
    if(isSokkerUrl(tab.url)) void autoArmSokkerTab(tabId,tab.url);
  }
});
chrome.tabs.onActivated.addListener(async info=>{
  try{
    const tab=await chrome.tabs.get(info.tabId);
    if(!tab?.url)return;
    if(isSokkerUrl(tab.url)){
      rememberSokkerTab(tab.id);
      void autoArmSokkerTab(tab.id,tab.url);
    }else{
      await ensureContentScript(tab.id,tab.url);
    }
  }catch{}
});
chrome.tabs.onRemoved.addListener(tabId=>{
  if(state.capture?.activeTabId===tabId){
    state.capture.activeTabId=null;
    state.capture.armed=false;
    state.lastUpdate=Date.now();
    awaitPersist();
  }
});

function isSokkerUrl(url){return /^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(String(url||""))}
async function ensureContentScript(tabId, url=""){
 if(!tabId || !(await isSokkerUrl(url))) return false;
 // 1) Fast path — content script already alive
 try{
   const ping=await chrome.tabs.sendMessage(tabId,{type:"PING_CONTENT"});
   if(ping?.ok) return true;
 }catch{}
 // 2) Reinjection COMPLETE — same order as manifest content_scripts
 // BUG FIX 9.2.0: previous version omitted lib/* and secondary scripts,
 // so reinjection after install/reload left content.js without CornerAILib
 // and without menu/h2h/charts/diagnostics modules.
 const files=[
   "lib/fixture-id.js",
   "lib/clock-parse.js",
   "lib/pressure-dual.js",
   "lib/corner-align.js",
   "lib/event-clock.js",
   "lib/ws-decode.js",
   "lib/chunk-buffer.js",
   "content.js",
   "activation-diagnostic.js",
   "charts-unified.js",
   "menu-capture.js",
   "h2h-capture.js"
 ];
 async function injectOnce(){
   await chrome.scripting.executeScript({target:{tabId,allFrames:false},files});
   await new Promise(r=>setTimeout(r,450));
   try{
     const ping=await chrome.tabs.sendMessage(tabId,{type:"PING_CONTENT"});
     return !!ping?.ok;
   }catch{ return false; }
 }
 try{
   if(await injectOnce()) return true;
 }catch(e){
   addError(`content reinjection: ${e.message}`);
 }
 // 3) Retry after short delay (handles service-worker / navigation races)
 try{
   await new Promise(r=>setTimeout(r,500));
   try{
     const ping=await chrome.tabs.sendMessage(tabId,{type:"PING_CONTENT"});
     if(ping?.ok) return true;
   }catch{}
   return await injectOnce();
 }catch(e){
   addError(`content reinjection retry: ${e.message}`);
   return false;
 }
}



/** 9.2.3 — colheita DOM direta via scripting API (não depende do content.js stale). */
async function forceDomHarvest(tabId){
  if(!tabId) return {ok:false,error:"no_tab"};
  try{
    const results = await chrome.scripting.executeScript({
      target:{tabId, allFrames:false},
      world:"ISOLATED",
      func: function harvest(){
        try{
          const clean = s => String(s||"").replace(/\s+/g," ").trim();
          const href = location.href || "";
          let fixtureId = null;
          const m = href.match(/\/(?:fixture|partida|match|game|event)\/(\d{5,})/i)
                 || href.match(/[?&#](?:fixture|fixtureId|matchId)=(\d{5,})/i)
                 || href.match(/sokkerpro\.com\/(?:fixture\/)?(\d{6,})(?:\/|$|\?)/i);
          if(m) fixtureId = m[1];
          if(!fixtureId && typeof window.CornerAILib!=="undefined" && window.CornerAILib.extractFidFromString){
            fixtureId = window.CornerAILib.extractFidFromString(href);
          }
          // teams
          let home="", away="";
          const teamEls = document.querySelectorAll("[class*='team-name'],[class*='teamName'],.team-name,.home-name,.away-name,[class*='participant']");
          const names=[];
          teamEls.forEach(el=>{
            const t=clean(el.textContent);
            if(t && t.length>1 && t.length<50 && !/^\d+$/.test(t) && !names.includes(t)) names.push(t);
          });
          if(names.length>=2){ home=names[0]; away=names[1]; }
          // score
          let score={home:null,away:null};
          const body = (document.body && document.body.innerText || "").slice(0,80000);
          const sm = body.match(/\b(\d{1,2})\s*[xX×:-]\s*(\d{1,2})\b/);
          if(sm){ score={home:Number(sm[1]),away:Number(sm[2])}; }
          // minute
          let minute=null, extraMinute=0;
          const mm = body.match(/\b(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?/) || body.match(/\b(\d{1,3})\s*['′]/);
          if(mm){ minute=Number(mm[1]); if(mm[2]) extraMinute=Number(mm[2]); }
          // xG
          let xg={home:null,away:null};
          const xgm = body.match(/xG[^\d]{0,20}(\d+[.,]\d+)\s*[^\d]{0,10}(\d+[.,]\d+)/i)
                   || body.match(/(\d+[.,]\d+)\s*[^\d]{0,10}(\d+[.,]\d+)[^\d]{0,20}xG/i);
          if(xgm){ xg={home:parseFloat(xgm[1].replace(",",".")), away:parseFloat(xgm[2].replace(",","."))}; }
          // corners
          let corners={home:null,away:null};
          const cm = body.match(/(?:escanteio|corner)s?[^\d]{0,30}(\d+)\s*[xX×:-]\s*(\d+)/i)
                  || body.match(/(\d+)\s*[xX×:-]\s*(\d+)[^\d]{0,30}(?:escanteio|corner)/i);
          if(cm){ corners={home:Number(cm[1]),away:Number(cm[2])}; }
          const liveStatus = (minute!=null && minute>=1 && minute<=120) ? "live" : "unknown";
          return {
            ok:true,
            version:"9.2.3-harvest",
            fixtureId: fixtureId?String(fixtureId):null,
            url: href,
            home, away, minute, extraMinute, score,
            liveStatus, dataMode: liveStatus==="live"?"live":"unknown",
            attacks:null, dangerous:null, shots:null, shotsOn:null, shotsOff:null,
            corners, xg, fouls:null, possession:null,
            matchEvents: [],
            harvestedAt: Date.now()
          };
        }catch(e){
          return {ok:false,error:String(e && e.message || e)};
        }
      }
    });
    const payload = results && results[0] && results[0].result;
    if(!payload || !payload.ok){
      return {ok:false,error:(payload&&payload.error)||"harvest_empty",payload};
    }
    // Ensure session flags
    state.capture = state.capture || {};
    state.capture.armed = true;
    state.capture.manualConsent = true;
    if(!state.capture.activeTabId) state.capture.activeTabId = tabId;
    if(payload.fixtureId){
      if(!state.fixtureId) state.fixtureId = String(payload.fixtureId);
    }
    const changed = mergeSnapshot(payload, "dom");
    state.capture.lastPayloadAt = Date.now();
    state.capture.lastAcceptedAt = Date.now();
    state.snapshotCount = Number(state.snapshotCount||0)+1;
    state.capture.acceptedSnapshots = Math.max(1, Number(state.capture.acceptedSnapshots||0)+1);
    state.lastSnapshotSource = "dom-harvest";
    state.lastUpdate = Date.now();
    // Force core fields even if mergeSnapshot was conservative
    if(payload.liveStatus==="live") state.liveStatus = "live";
    else if(payload.minute!=null && Number(payload.minute)>=1 && Number(payload.minute)<=120) state.liveStatus = "live";
    if(payload.home) state.home = String(payload.home);
    if(payload.away) state.away = String(payload.away);
    if(payload.score && (payload.score.home!=null || payload.score.away!=null)) {
      state.score = {home:payload.score.home, away:payload.score.away};
    }
    if(payload.minute!=null) state.minute = Number(payload.minute);
    if(payload.extraMinute!=null) state.extraMinute = Number(payload.extraMinute)||0;
    if(payload.fixtureId) state.fixtureId = String(payload.fixtureId);
    if(payload.xg && (payload.xg.home!=null||payload.xg.away!=null)) {
      state.stats = state.stats||{};
      state.stats.xg = {home:payload.xg.home, away:payload.xg.away};
    }
    if(payload.corners && (payload.corners.home!=null||payload.corners.away!=null)) {
      state.stats = state.stats||{};
      state.stats.corners = {home:payload.corners.home, away:payload.corners.away};
    }
    await awaitPersist({immediate:true});
    return {
      ok:true,
      changed,
      fixtureId: state.fixtureId,
      acceptedSnapshots: state.capture.acceptedSnapshots,
      snapshotCount: state.snapshotCount,
      home: state.home,
      away: state.away,
      score: state.score,
      minute: state.minute,
      liveStatus: state.liveStatus,
      harvest: payload
    };
  }catch(e){
    addError("forceDomHarvest: "+(e?.message||e));
    return {ok:false,error:e?.message||String(e)};
  }
}


let dashboardWindowId=null;
let centralWindowId=null;
let kanteiroChatWindowId=null;
let diagnosticsWindowId=null;
let lastSokkerTabId=null;
let lastSokkerTabSeenAt=0;

function rememberSokkerTab(tabId){
  if(Number.isInteger(Number(tabId))&&Number(tabId)>0){
    lastSokkerTabId=Number(tabId);
    lastSokkerTabSeenAt=Date.now();
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.lastSokkerTabId=lastSokkerTabId;
    state.diagnostics.lastSokkerTabSeenAt=lastSokkerTabSeenAt;
  }
}

async function getPreferredSokkerTab(){
  // 1) sessão de captura já proprietária
  const owned=Number(state.capture?.activeTabId);
  if(Number.isInteger(owned)&&owned>0){
    try{
      const t=await chrome.tabs.get(owned);
      if(t?.id&&isSokkerUrl(t.url)) return t;
    }catch{}
  }
  // 2) última aba SokkerPRO que estava ativa antes de abrir Dashboard/Diagnóstico
  if(Number.isInteger(lastSokkerTabId)&&lastSokkerTabId>0){
    try{
      const t=await chrome.tabs.get(lastSokkerTabId);
      if(t?.id&&isSokkerUrl(t.url)) return t;
    }catch{}
  }
  // 3) aba ativa atual
  try{
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});
    return tabs.find(t=>isSokkerUrl(t.url))||null;
  }catch{return null}
}

async function openToolWindow(kind){
  const source=await getPreferredSokkerTab();
  if(source?.id) rememberSokkerTab(source.id);
  // dashboard/diagnóstico nunca devem virar a aba-alvo da captura.

  // dashboard lives under ui/; diagnostics is at extension root
  const fileMap={dashboard:"ui/dashboard.html",diagnostics:"diagnostics.html",central:"src/aura-quantx-central.html",chat:"src/kanteiro-chat.html"};
  const file=fileMap[kind]||"diagnostics.html";
  const width=kind==="central"?1440:(kind==="chat"?1100:(kind==="dashboard"?1220:980));
  const height=kind==="central"?960:(kind==="chat"?860:(kind==="dashboard"?900:760));
  const getId=()=>kind==="dashboard"?dashboardWindowId:kind==="central"?centralWindowId:kind==="chat"?kanteiroChatWindowId:diagnosticsWindowId;
  const setId=(id)=>{ if(kind==="dashboard") dashboardWindowId=id; else if(kind==="central") centralWindowId=id; else if(kind==="chat") kanteiroChatWindowId=id; else diagnosticsWindowId=id; };
  try{
    const existing=getId();
    if(existing!=null){
      try{
        await chrome.windows.update(existing,{focused:true});
        const tabs=await chrome.tabs.query({windowId:existing});
        // If window exists but is empty/broken, recreate
        if(tabs && tabs.length){
          return {ok:true,windowId:existing,reused:true};
        }
        setId(null);
      }catch{
        setId(null);
      }
    }
    const url=chrome.runtime.getURL(file);
    // Prefer popup window; fallback to normal tab if OS/browser blocks popups
    try{
      const w=await chrome.windows.create({url,type:"popup",width,height,focused:true});
      if(w?.id){
        setId(w.id);
        return {ok:true,windowId:w.id,reused:false,url,mode:"popup"};
      }
    }catch(e1){
      addError(`openToolWindow(${kind}) popup: ${e1?.message||e1}`);
    }
    // Fallback: open as a normal tab in current window
    try{
      const tab=await chrome.tabs.create({url,active:true});
      return {ok:true,tabId:tab?.id||null,reused:false,url,mode:"tab"};
    }catch(e2){
      const msg=e2?.message||String(e2);
      addError(`openToolWindow(${kind}) tab: ${msg}`);
      return {ok:false,error:`Não foi possível abrir ${kind}: ${msg}`};
    }
  }catch(e){
    const msg=e?.message||String(e);
    addError(`openToolWindow(${kind}): ${msg}`);
    return {ok:false,error:`Não foi possível abrir ${kind}: ${msg}`};
  }
}
chrome.windows.onRemoved.addListener(id=>{
  if(id===dashboardWindowId) dashboardWindowId=null;
  if(id===diagnosticsWindowId) diagnosticsWindowId=null;
  if(id===centralWindowId) centralWindowId=null;
  if(id===kanteiroChatWindowId) kanteiroChatWindowId=null;
});


function __cornerDedupEvent(payload){
  try{
    state.capture=state.capture||{};
    state.capture.eventDedup=state.capture.eventDedup||{};
    const key=JSON.stringify({
      fixtureId:payload?.fixtureId??state.fixtureId??null,
      minute:payload?.minute??payload?.minuteKey??null,
      type:payload?.type??payload?.eventType??null,
      event:payload?.event??payload?.name??null,
      player:payload?.playerId??payload?.player??null,
      team:payload?.teamId??payload?.team??null,
      value:payload?.value??null
    });
    const now=Date.now(), prev=state.capture.eventDedup[key];
    if(prev && now-prev<15000){
      state.diagnostics.duplicateEvents=Number(state.diagnostics.duplicateEvents||0)+1;
      state.diagnostics.duplicateEventDetections=Number(state.diagnostics.duplicateEventDetections||0)+1;
      return true;
    }
    state.capture.eventDedup[key]=now;
    const keys=Object.keys(state.capture.eventDedup);
    if(keys.length>300) keys.slice(0,keys.length-250).forEach(k=>delete state.capture.eventDedup[k]);
  }catch{}
  return false;
}


function buildEventIntegrity(){
  const events=Array.isArray(state.matchEvents)?state.matchEvents:[];
  const seen=new Set();
  const duplicates=[];
  for(const e of events){
    const key=String(e?.fixtureId||state.fixtureId||"?")+"|"+String(e?.type||"")+"|"+String(e?.period||"")+"|"+String(e?.minute||"")+"|"+String(e?.extraMinute||0)+"|"+String(e?.side||"")+"|"+String(e?.signature||e?.eventId||"")+"|"+String(e?.playerId||e?.playerName||"");
    if(seen.has(key)) duplicates.push(key); else seen.add(key);
  }
  return {unique:seen.size,total:events.length,duplicates:duplicates.length,sample:duplicates.slice(0,5)};
}

function __cornerSemanticSnapshotKey(payload){
  try{
    const x=payload?.snapshot||payload?.data||payload||{};
    const stable={
      fixtureId:x.fixtureId??state.fixtureId??null,
      minute:x.minute??x.minuteKey??null,
      score:x.score??null,
      teams:x.teams??null,
      stats:x.stats??null,
      events:x.events??null,
      liveStatus:x.liveStatus??null
    };
    return JSON.stringify(stable);
  }catch{return ""}
}
function __cornerShouldBuildAI(payload){
  const key=__cornerSemanticSnapshotKey(payload);
  if(!key)return true;
  state.capture=state.capture||{};
  if(state.capture.lastSemanticSnapshotKey===key){
    state.diagnostics.snapshotDuplicates=Number(state.diagnostics.snapshotDuplicates||0)+1;
    return false;
  }
  state.capture.lastSemanticSnapshotKey=key;
  return true;
}


function extractFixtureIdFromString(s){
  if(s==null) return null;
  const str=String(s);
  if(/^\d{5,12}$/.test(str.trim())) return str.trim();
  let m=str.match(/\/(?:fixture|partida|match|game|event)\/(\d{5,})/i);
  if(m) return m[1];
  m=str.match(/\/ws\/fixture\/(\d{5,})/i);
  if(m) return m[1];
  m=str.match(/[?&#](?:fixture|fixtureId|matchId|match_id|gameId|game_id|eventId)=(\d{5,})/i);
  if(m) return m[1];
  m=str.match(/\/(?:api\/)?fixtures?\/(\d{5,})/i);
  if(m) return m[1];
  m=str.match(/["'](?:fixture(?:Id)?|matchId|gameId)["']\s*[:=]\s*["']?(\d{5,})/i);
  if(m) return m[1];
  m=str.match(/sokkerpro\.com\/(?:fixture\/)?(\d{6,})(?:\/|$|\?)/i);
  if(m) return m[1];
  return null;
}
function extractFixtureIdFromPayload(payload,meta){
  const candidates=[
    payload?.fixtureId, payload?.__fixtureId, payload?.matchId, payload?.gameId,
    meta?.fixtureId,
    payload?.__endpoint, meta?.url, payload?.url, state?.url
  ];
  for(const c of candidates){
    const id=extractFixtureIdFromString(c);
    if(id) return id;
  }
  return null;
}
function recoverFixtureFromCharts(){
  try{
    const urls=[
      ...(Array.isArray(state.charts?.networkUrls)?state.charts.networkUrls:[]),
      state.diagnostics?.lastEndpoint,
      state.url,
      state.menuCapture?.current?.url
    ].filter(Boolean);
    for(const u of urls){
      const id=extractFixtureIdFromString(u);
      if(id){
        if(!state.fixtureId){
          state.fixtureId=String(id);
          state.diagnostics.fixtureRecovered=(state.diagnostics.fixtureRecovered||0)+1;
        }
        return String(id);
      }
    }
  }catch{}
  return state.fixtureId?String(state.fixtureId):null;
}
function adoptFixtureFromPayload(payload,meta){
  let id=extractFixtureIdFromPayload(payload,meta);
  if(!id) id=recoverFixtureFromCharts();
  if(!id) return false;
  if(!state.fixtureId){
    state.fixtureId=String(id);
    state.diagnostics.fixtureRecovered=(state.diagnostics.fixtureRecovered||0)+1;
    return true;
  }
  if(String(state.fixtureId)!==String(id)){
    if(!state.home && !state.away){
      state.fixtureId=String(id);
      return true;
    }
  }
  return false;
}

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
 // FIX 12.5.9: OPEN_SIDE_PANEL precisa ser resolvido ANTES de qualquer await
 // (inclusive ensureStateLoaded), senão o gesto de clique do usuário expira
 // e chrome.sidePanel.open() lança "may only be called in response to a user
 // gesture", deixando o painel (chat/terminal) sem abrir.
 // v12.6.0 — WoM: atualização de mercado (linha/odd asiática de escanteios)
 // enviada pelo market-capture.js. Só agrega no state; não dispara await
 // antes de responder, então não precisa do cuidado de gesto de usuário
 // do OPEN_SIDE_PANEL logo abaixo.
 if(msg?.type==="MARKET_DATA_UPDATE"){
  try{
   const p=msg.payload||{};
   state.wom=state.wom||{};
   const asNum=(v)=>typeof v==="number"&&Number.isFinite(v)?v:(v==null||v===""?null:Number(v));
   const cl=asNum(p.asian_corner_line); if(cl!=null&&!Number.isNaN(cl)) state.wom.asian_corner_line=cl;
   const co=asNum(p.asian_corner_odds); if(co!=null&&!Number.isNaN(co)) state.wom.asian_corner_odds=co;
   const gl=asNum(p.asian_goal_line); if(gl!=null&&!Number.isNaN(gl)) state.wom.asian_goal_line=gl;
   const go=asNum(p.asian_goal_odds); if(go!=null&&!Number.isNaN(go)) state.wom.asian_goal_odds=go;
   // Detalhe Bet365 / listas de mercado (analítico)
   if(p.bet365) state.wom.bet365=p.bet365;
   if(Array.isArray(p.corners)) state.wom.corners_market=p.corners.slice(0,12);
   if(Array.isArray(p.goals)) state.wom.goals_market=p.goals.slice(0,12);
   if(Array.isArray(p.sources)) state.wom.market_sources=p.sources;
   state.wom.schema=p.schema||state.wom.schema||"aura-market-auto";
   state.wom.last_update=Date.now();
   state.wom.autoOnSelect=!!p.autoOnSelect;
   sendResponse({ok:true,wom:state.wom});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  return true;
 }

 // AURA QUANT-X UI: abrir central/chat no gesto do usuário (antes de ensureStateLoaded)
 if(msg?.type==="OPEN_CENTRAL"||msg?.type==="OPEN_KANTEIRO_CHAT"||msg?.type==="OPEN_LEGACY_DASHBOARD"){
  const kind=msg.type==="OPEN_CENTRAL"?"central":msg.type==="OPEN_KANTEIRO_CHAT"?"chat":"dashboard";
  (async()=>{
   try{
    const r=await openToolWindow(kind);
    sendResponse(r||{ok:false,error:"open_failed"});
   }catch(e){
    sendResponse({ok:false,error:e?.message||String(e)});
   }
  })();
  return true;
 }
 if(msg?.type==="OPEN_SIDE_PANEL"){
  (async()=>{
   try{
    if(chrome.sidePanel&&typeof chrome.sidePanel.open==="function"){
     const w=sender?.tab?.windowId!=null?{id:sender.tab.windowId}:await chrome.windows.getCurrent();
     await chrome.sidePanel.open({windowId:w.id});
     sendResponse({ok:true,mode:"sidePanel"});
     return;
    }
    const url=chrome.runtime.getURL("visao/sidepanel.html");
    await chrome.windows.create({url,type:"popup",width:420,height:640,focused:true});
    sendResponse({ok:true,mode:"popup"});
   }catch(e){
    try{
     const url=chrome.runtime.getURL("visao/sidepanel.html");
     await chrome.windows.create({url,type:"popup",width:420,height:640,focused:true});
     sendResponse({ok:true,mode:"popup-fallback"});
    }catch(e2){sendResponse({ok:false,error:(e2?.message||e?.message||String(e))});}
   }
  })();
  return true;
 }
 (async()=>{try{await ensureStateLoaded();switch(msg?.type){
 case"RESET_CAPTURE_SESSION":{
  const fixture=String(msg.fixtureId||"");
  if(!fixture){sendResponse({ok:false,error:"fixture_required"});break;}
  try{ forceMarketScanOnTabs(); }catch(_){}
  const prev=state;
  // 9.2.4: same fixture already armed → soft reset (keep counters / core fields)
  if(String(prev.fixtureId||"")===fixture && prev.capture?.armed){
    state.capture=state.capture||{};
    state.capture.armed=true;
    state.capture.manualConsent=true;
    if(sender?.tab?.id) state.capture.activeTabId=Number(sender.tab.id);
    state.url=String(msg.url||state.url||"");
    state.lastUpdate=Date.now();
    state.diagnostics=(state.diagnostics||{});
    state.diagnostics.lastResetReason=String(msg.reason||"soft-rearm");
    await awaitPersist();
    sendResponse({ok:true,fixtureId:fixture,clean:false,soft:true,activeTabId:state.capture.activeTabId,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),at:Date.now()});
    break;
  }
  const keep={alertPrefs:prev.alertPrefs,webhook:prev.webhook,gemini:prev.gemini};
  state=defaultState();
  state.capture.activeTabId=sender?.tab?.id??null;
  state.capture.armed=true;
  state.capture.manualConsent=true;
  state.capture.sessionId=`${fixture}:${state.capture.activeTabId||"na"}:${Date.now().toString(36)}`;
  state.fixtureId=fixture; try{ forceMarketScanOnTabs(); }catch(_){}
  state.url=String(msg.url||"");
  if(keep.alertPrefs) state.alertPrefs=keep.alertPrefs;
  if(keep.webhook) state.webhook={...state.webhook,...keep.webhook};
  if(keep.gemini) state.gemini=keep.gemini;
  state.diagnostics=(state.diagnostics||{});
  state.diagnostics.sessionStartedAt=Date.now();
  state.diagnostics.lastResetReason=String(msg.reason||"preflight");
  state.diagnostics.preCaptureResets=Number(state.diagnostics.preCaptureResets||0)+1;
  await awaitPersist();
  broadcast();
  sendResponse({ok:true,fixtureId:fixture,clean:true,activeTabId:state.capture.activeTabId,at:Date.now()});
  break;
}
case"MENU_PRIME":{
  const fid=String(msg.fixtureId||state.fixtureId||"");
  if(fid && state.fixtureId && fid!==String(state.fixtureId)){sendResponse({ok:false,error:"fixture_mismatch"});break;}
  try{
    const tabId=sender?.tab?.id;
    if(!tabId){sendResponse({ok:false,error:"tab_required"});break;}
    const result=await new Promise((resolve,reject)=>chrome.tabs.sendMessage(tabId,{type:"MENU_PRIME"},r=>{const e=chrome.runtime.lastError;e?reject(new Error(e.message)):resolve(r||{ok:false});}));
    state.menuCapture=state.menuCapture||defaultState().menuCapture;
    if(Array.isArray(result?.ids)) state.menuCapture.discovered=[...new Set([...(state.menuCapture.discovered||[]),...result.ids])].slice(0,120);
    state.menuCapture.uniqueMenus=state.menuCapture.discovered.length;
    state.diagnostics.menuDiscoveries=(state.diagnostics.menuDiscoveries||0)+Number(result?.discovered||0);
    await awaitPersist();
    sendResponse({ok:!!result?.ok,discovered:Number(result?.discovered||0),ids:result?.ids||[]});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;
}
case"H2H_CAPTURE":{if(!acceptFixtureMessage(msg.payload,"h2h",sender,msg.meta)){sendResponse({ok:false,error:"CAPTURA | sessão não armada ou contexto inválido"});break;}const now=Date.now(),payload=msg.payload||{},tables=Array.isArray(payload.tables)?payload.tables.slice(0,50):[],text=String(payload.text||"").slice(0,30000);
  let matches=Array.isArray(payload.matches)?payload.matches.slice(0,60):[];
  let summary=payload.summary&&typeof payload.summary==="object"?payload.summary:{};
  let parameters=payload.parameters&&typeof payload.parameters==="object"?payload.parameters:{};
  const prev=state.h2h||{};
  // Never let a weaker/empty parse erase a richer H2H snapshot for the same session.
  if(matches.length===0 && Array.isArray(prev.matches)&&prev.matches.length>0) matches=prev.matches;
  if((!summary||summary.homeWins==null)&&(prev.summary&&prev.summary.homeWins!=null)) summary={...prev.summary,...summary};
  // Derive W/D/L from match scores when banner summary is empty
  if(matches.length && (summary.homeWins==null || summary.draws==null || summary.awayWins==null)){
    let hw=0,dr=0,aw=0,counted=0;
    for(const m of matches){
      const hg=Number(m.homeGoals??m.homeScore), ag=Number(m.awayGoals??m.awayScore);
      if(!Number.isFinite(hg)||!Number.isFinite(ag)) continue;
      counted++;
      if(hg===ag) dr++; else if(hg>ag) hw++; else aw++;
    }
    if(counted>0){
      summary={...summary};
      if(summary.homeWins==null) summary.homeWins=hw;
      if(summary.draws==null) summary.draws=dr;
      if(summary.awayWins==null) summary.awayWins=aw;
      if(summary.total==null) summary.total=counted;
    }
  }
  if((!parameters||parameters.matches===0||parameters.avgGoalsTotal==null)&&(prev.parameters&&prev.parameters.avgGoalsTotal!=null)) parameters={...prev.parameters,...parameters};
  // Keep parameters in sync with derived summary
  if(summary && (summary.homeWins!=null||summary.draws!=null||summary.awayWins!=null)){
    parameters={...parameters, homeWins:summary.homeWins??parameters.homeWins??null, draws:summary.draws??parameters.draws??null, awayWins:summary.awayWins??parameters.awayWins??null, totalResults:summary.total??parameters.totalResults??matches.length};
  }
  const hasData=!!(text||tables.length||matches.length||summary.total||(prev.captured&&matches.length));
  const averagesIn=payload.averages&&typeof payload.averages==="object"?payload.averages:{};
  let computed=Object.keys(averagesIn).length?averagesIn:computeH2HAverages(tables,text,{});
  if((!computed||!Object.keys(computed).length)&&prev.averages&&Object.keys(prev.averages).length) computed=prev.averages;
  const rowsIn=tables.flatMap(t=>Array.isArray(t.rows)?t.rows:[]).slice(0,1000);
  state.h2h={...prev,attempted:true,lastAttemptAt:now,captured:hasData||!!prev.captured,rows:rowsIn.length?rowsIn:(prev.rows||[]),tables:tables.length?tables:(prev.tables||[]),matches,summary,parameters,text:text||prev.text||"",averages:computed,rootFound:!!payload.rootFound||!!prev.rootFound,updatedAt:hasData?now:(prev.updatedAt||0)};
  if(hasData)state.lastUpdate=now;await awaitPersist();
  try{await persistTeamContextCache();}catch{}
  sendResponse({ok:!!state.h2h.captured,attempted:true,h2h:{captured:!!state.h2h.captured,tables:Array.isArray(state.h2h.tables)?state.h2h.tables.length:0,matches:Array.isArray(state.h2h.matches)?state.h2h.matches.length:0,rows:Array.isArray(state.h2h.rows)?state.h2h.rows.length:0,summary:state.h2h.summary,parameters:state.h2h.parameters,averages:state.h2h.averages},error:state.h2h.captured?null:"H2H | captação"});break;}
 case"H2H_POLL":{try{const tabs=await chrome.tabs.query({active:true,currentWindow:true});const tab=tabs.find(x=>/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(x.url||""));if(!tab?.id){sendResponse({ok:false,error:"Abra o SokkerPRO."});break;}// Ensure content listeners are armed before polling H2H.
const result=await new Promise((resolve,reject)=>{chrome.tabs.sendMessage(tab.id,{type:"H2H_POLL"},r=>{const err=chrome.runtime.lastError;if(err)reject(new Error(err.message));else resolve(r||{ok:false});});});
// Small settle window for H2H_CAPTURE message to merge into state.
await new Promise(r=>setTimeout(r,800));
sendResponse({ok:!!result?.ok||!!state.h2h?.captured,h2h:{captured:!!state.h2h?.captured,attempted:!!state.h2h?.attempted,tables:Array.isArray(state.h2h?.tables)?state.h2h.tables.length:0,rows:Array.isArray(state.h2h?.rows)?state.h2h.rows.length:0,averages:state.h2h?.averages||{},textLength:String(state.h2h?.text||"").length},result});}catch(e){sendResponse({ok:false,error:e.message});}break;}
 case"MENU_SNAPSHOT":{if(!acceptFixtureMessage(msg.payload,"menu",sender,msg.meta)){sendResponse({ok:false,error:"CAPTURA | sessão não armada ou contexto inválido"});break;}const ok=mergeMenuSnapshot(msg.payload,sender);if(ok){const tid=sender?.tab?.id;if(tid!=null&&state.menuCapture?.sweep?.tabIds?.includes(tid)){state.menuCapture.sweep.completed++;if(state.menuCapture.sweep.completed>=state.menuCapture.sweep.requested)state.menuCapture.sweep.active=false;}await awaitPersist()}sendResponse({ok,menuCapture:clone(state.menuCapture)});break;}
  case"MENU_SWEEP":{try{
 const targetTabId=state.capture?.activeTabId??null;
 let tab=null;
 if(targetTabId!=null){try{tab=await chrome.tabs.get(targetTabId)}catch{tab=null}}
 if(!tab){const tabs=await chrome.tabs.query({active:true,currentWindow:true});tab=tabs.find(x=>/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(x.url||""));}
 if(!tab?.id){sendResponse({ok:false,error:"Abra uma partida do SokkerPRO."});break;}
 if(state.capture?.activeTabId!=null&&Number(tab.id)!==Number(state.capture.activeTabId)){sendResponse({ok:false,error:"MENU | aba fora da sessão"});break;}
 state.menuCapture.sweep={active:true,tabIds:[tab.id],startedAt:Date.now(),requested:1,completed:0,mode:"controlled"};
 const options={...(msg.options||msg.payload?.options||{allowClicks:true,maxOpen:5,waitMs:550,preferIds:["escanteios","estatisticas","h2h","odds","graficos","eventos"]}),fixtureId:String(state.fixtureId||"")};try{const result=await new Promise((resolve,reject)=>{chrome.tabs.sendMessage(tab.id,{type:"MENU_SWEEP",options},r=>{const err=chrome.runtime.lastError;if(err)reject(new Error(err.message));else resolve(r||{ok:false,error:"sem resposta"});});});state.menuCapture.sweep.completed=1;state.menuCapture.sweep.active=false;state.menuCapture.sweep.lastResult={opened:Number(result?.opened||0),restored:!!result?.restored,discovered:Number(result?.discovered||0),errors:Array.isArray(result?.errors)?result.errors.slice(0,10):[],at:Date.now()};if(result?.ok){state.diagnostics.menuSweeps=(state.diagnostics.menuSweeps||0)+1;}else{state.diagnostics.menuErrors=(state.diagnostics.menuErrors||0)+1;}await awaitPersist();sendResponse({ok:!!result?.ok,count:1,urls:[tab.url],sweep:state.menuCapture.sweep.lastResult,error:result?.error||null});}catch(e){state.diagnostics.menuErrors=(state.diagnostics.menuErrors||0)+1;state.menuCapture.sweep.active=false;sendResponse({ok:false,error:e.message});await awaitPersist();}}catch(e){sendResponse({ok:false,error:e.message});}break;}
  case"DOM_SNAPSHOT":{
  if(!acceptFixtureMessage(msg.payload,"dom",sender,msg.meta)){
    state.diagnostics.rejectedDomSnapshots=Number(state.diagnostics.rejectedDomSnapshots||0)+1;
    sendResponse({ok:false,rejected:true,reason:"fixture_or_tab_guard",activeTabId:state.capture?.activeTabId??null,senderTabId:sender?.tab?.id??null,fixtureId:state.fixtureId,armed:!!state.capture?.armed,manualConsent:!!state.capture?.manualConsent,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),state:clone(state)});
    break;
  }
  const changed=mergeSnapshot(msg.payload,"dom");
  // 9.2.1: count pipeline success even if values unchanged (heartbeat)
  state.capture.lastPayloadAt=Date.now();
  state.capture.lastAcceptedAt=Date.now();
  state.capture.lastAcceptedFixture=state.fixtureId;
  state.snapshotCount=Number(state.snapshotCount||0)+1;
  if(Number(state.capture.acceptedSnapshots||0)<1) state.capture.acceptedSnapshots=1;
  else if(changed) state.capture.acceptedSnapshots=Number(state.capture.acceptedSnapshots||0)+1;
  state.lastSnapshotSource="dom";
  state.lastUpdate=Date.now();
  await awaitPersist();
  sendResponse({ok:true,accepted:true,changed,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),fixtureId:state.fixtureId,backgroundVersion:VERSION,state:clone(state)});
  break;
}
 case"NETWORK_SNAPSHOT":if(msg.meta?.url&&state.fixtureId&&!endpointBelongsToFixture(msg.meta.url,state.fixtureId)){state.diagnostics.foreignFixturePayloads++;state.diagnostics.networkPayloadsRejected++;sendResponse({ok:false,rejected:true,state:clone(state)});break;}if(!acceptFixtureMessage(msg.payload,"network",sender,msg.meta)){state.diagnostics.networkPayloadsRejected++;sendResponse({ok:false,rejected:true,state:clone(state)});break;}state.diagnostics.networkResponses++;if(msg.meta?.url && endpointBelongsToFixture(msg.meta.url,state.fixtureId))state.diagnostics.lastEndpoint=String(msg.meta.url).slice(0,500);const histUrlN=msg.meta?.url||msg.payload?.__endpoint||"";if(histUrlN){try{ingestHistoricalEndpoint(histUrlN,msg.payload,"network")}catch{}}const changed=mergeSnapshot(msg.payload,"network");if(state.liveStatus==="finished"||state.dataMode==="historical"){try{rebuildHistoricalCoverage()}catch{}}await awaitPersist();try{scheduleDailyAutoSave(state.fixtureId,"dom")}catch{}sendResponse({ok:true,accepted:true,changed,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),fixtureId:state.fixtureId,state:clone(state)});break;
 case"HOOK_READY":if(!state.capture?.manualConsent||!state.capture?.armed){state.diagnostics.unarmedPayloads=(state.diagnostics.unarmedPayloads||0)+1;sendResponse({ok:false,rejected:true,reason:"unarmed"});break;}if(state.capture.activeTabId!=null&&sender?.tab?.id!==state.capture.activeTabId){state.diagnostics.foreignTabPayloads++;sendResponse({ok:false,rejected:true});break;}state.diagnostics.lastHookAt=Date.now();state.sources.hook={lastUpdate:Date.now(),count:(state.sources.hook?.count||0)+1};sendResponse({ok:true,version:VERSION});break;
 case"HOOK_HEARTBEAT":if(!state.capture?.manualConsent||!state.capture?.armed){state.diagnostics.unarmedPayloads=(state.diagnostics.unarmedPayloads||0)+1;sendResponse({ok:false,rejected:true,reason:"unarmed"});break;}if(state.capture.activeTabId!=null&&sender?.tab?.id!==state.capture.activeTabId){state.diagnostics.foreignTabPayloads++;sendResponse({ok:false,rejected:true});break;}state.diagnostics.lastHookAt=Date.now();state.diagnostics.hookHeartbeats=(state.diagnostics.hookHeartbeats||0)+1;state.sources.hook={lastUpdate:Date.now(),count:(state.sources.hook?.count||0)+1};sendResponse({ok:true,version:VERSION});break;
 case"HISTORICAL_BOOTSTRAP":{
  state.diagnostics.historicalBootstrap=(state.diagnostics.historicalBootstrap||0)+1;
  state.diagnostics.lastHistoricalBootstrapAt=Date.now();
  state.diagnostics.lastHistoricalBootstrap=msg.payload||{};
  if(msg.payload?.fixtureId&&!state.fixtureId)state.fixtureId=String(msg.payload.fixtureId);
  sendResponse({ok:true,version:VERSION});
  break;}
 case"SITE_STORAGE_SCAN":{
  state.diagnostics.siteStorageScans=(state.diagnostics.siteStorageScans||0)+1;
  state.diagnostics.lastSiteStorageScanAt=Date.now();
  state.diagnostics.lastSiteStorageScan=msg.payload||{};
  if(Array.isArray(msg.payload?.keys)) state.diagnostics.siteStorageKeysFound=(state.diagnostics.siteStorageKeysFound||0)+msg.payload.keys.length;
  sendResponse({ok:true,version:VERSION});
  break;}
 case"WS_RECONNECT_BOOTSTRAP":{
  state.diagnostics.wsReconnectBootstraps=(state.diagnostics.wsReconnectBootstraps||0)+1;
  state.diagnostics.lastWsReconnectAt=Date.now();
  state.diagnostics.lastWsReconnect=msg.payload||{};
  sendResponse({ok:true,version:VERSION});
  break;}
 case"GET_LAYER_DIAG":{refreshLayerDiagnostics().then(d=>sendResponse({ok:true,layerDiag:d})).catch(e=>sendResponse({ok:false,error:String(e?.message||e)}));return true;}
 case"BINARY_WS_DECODED":{
  if(state.capture.activeTabId!=null&&sender?.tab?.id!==state.capture.activeTabId){state.diagnostics.foreignTabPayloads=(state.diagnostics.foreignTabPayloads||0)+1;sendResponse({ok:false,rejected:true});break;}
  state.diagnostics.lastHookAt=Date.now();
  state.diagnostics.binaryWsDecoded=(state.diagnostics.binaryWsDecoded||0)+1;
  state.diagnostics.lastBinaryDecodeAt=Date.now();
  state.diagnostics.lastBinaryDecodedType=String(msg.payload?.decodedType||"");
  state.diagnostics.lastBinaryEndpoint=String(msg.payload?.endpoint||"").slice(0,300);
  state.sources.hook={lastUpdate:Date.now(),count:(state.sources.hook?.count||0)+1};
  sendResponse({ok:true,version:VERSION});
  break;}
 case"BINARY_WS_UNKNOWN":{
  if(state.capture.activeTabId!=null&&sender?.tab?.id!==state.capture.activeTabId){state.diagnostics.foreignTabPayloads=(state.diagnostics.foreignTabPayloads||0)+1;sendResponse({ok:false,rejected:true});break;}
  state.diagnostics.lastHookAt=Date.now();
  state.diagnostics.binaryWsUnknown=(state.diagnostics.binaryWsUnknown||0)+1;
  state.diagnostics.lastBinaryUnknownAt=Date.now();
  state.diagnostics.lastBinaryHexHead=String(msg.payload?.hexHead||"").slice(0,96);
  state.diagnostics.lastBinaryEndpoint=String(msg.payload?.endpoint||"").slice(0,300);
  state.sources.hook={lastUpdate:Date.now(),count:(state.sources.hook?.count||0)+1};
  sendResponse({ok:true,version:VERSION});
  break;}
 case"WS_OPEN":{
  state.diagnostics.wsOpenCount=(state.diagnostics.wsOpenCount||0)+1;
  state.diagnostics.lastWsOpenAt=Date.now();
  state.diagnostics.lastWsEndpoint=String(msg.payload?.endpoint||"").slice(0,300);
  state.diagnostics.lastHookAt=Date.now();
  sendResponse({ok:true,version:VERSION});
  break;}
 case"WS_CLOSE":{
  state.diagnostics.wsCloseCount=(state.diagnostics.wsCloseCount||0)+1;
  state.diagnostics.lastWsCloseAt=Date.now();
  sendResponse({ok:true,version:VERSION});
  break;}
 case"HOOK_SNAPSHOT":state.diagnostics.interceptedPayloads++;if(msg.meta?.url&&state.fixtureId&&!endpointBelongsToFixture(msg.meta.url,state.fixtureId)){state.diagnostics.foreignFixturePayloads++;state.diagnostics.networkPayloadsRejected++;sendResponse({ok:false,rejected:true,state:clone(state)});break;}if(!acceptFixtureMessage(msg.payload,"hook",sender,msg.meta)){state.diagnostics.networkPayloadsRejected++;sendResponse({ok:false,rejected:true,state:clone(state)});break;}state.diagnostics.hookMessages++;state.diagnostics.lastHookAt=Date.now();if(msg.meta?.url && endpointBelongsToFixture(msg.meta.url,state.fixtureId))state.diagnostics.lastEndpoint=String(msg.meta.url).slice(0,500);const histUrl=msg.meta?.url||msg.payload?.__endpoint||"";if(histUrl){try{ingestHistoricalEndpoint(histUrl,msg.payload,"hook")}catch{}}const hookChanged=mergeSnapshot(msg.payload,"hook");if(state.liveStatus==="finished"||state.dataMode==="historical"){try{rebuildHistoricalCoverage()}catch{}}await awaitPersist();try{scheduleDailyAutoSave(state.fixtureId,"hook")}catch{}sendResponse({ok:true,accepted:true,changed:hookChanged,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),fixtureId:state.fixtureId,state:clone(state)});break;
 case"NETWORK_TELEMETRY":if(!state.capture?.manualConsent||!state.capture?.armed){state.diagnostics.unarmedPayloads=(state.diagnostics.unarmedPayloads||0)+1;sendResponse({ok:false,rejected:true,reason:"unarmed"});break;}if(state.capture.activeTabId!=null&&sender?.tab?.id!==state.capture.activeTabId){state.diagnostics.foreignTabPayloads++;sendResponse({ok:false,rejected:true});break;}state.diagnostics.networkRequests+=Number(msg.count)||0;if(msg.url && /m[24]\.sokkerpro\.com|\/x7\b|wss:\/\//i.test(String(msg.url))){state.diagnostics.networkResponses=(state.diagnostics.networkResponses||0)+1;}if(msg.url && (!state.capture.activeTabId || sender?.tab?.id===state.capture.activeTabId) && endpointBelongsToFixture(msg.url,state.fixtureId))state.diagnostics.lastEndpoint=String(msg.url).slice(0,500);if(msg.error)addError(`network: ${msg.error}`);state.sources.network={lastUpdate:Date.now(),count:(state.sources.network?.count||0)+1};await awaitPersist();sendResponse({ok:true});break;
 case"OPEN_CENTRAL":openToolWindow("central").then(r=>sendResponse(r));return true;
 case"OPEN_KANTEIRO_CHAT":openToolWindow("chat").then(r=>sendResponse(r));return true;
 case"OPEN_LEGACY_DASHBOARD":openToolWindow("dashboard").then(r=>sendResponse(r));return true;
 case"SW_PING":{sendResponse({ok:true,version:VERSION,alive:true,ts:Date.now(),fixtureId:state.fixtureId||null});break;}
 case"REQUEST_STATE":{try{buildIntegrity()}catch{}sendResponse(clone(state));break;}
 case"GET_CAPTURE_TARGET":{
  const t=await getPreferredSokkerTab();
  if(t?.id) rememberSokkerTab(t.id);
  sendResponse({ok:!!t?.id,tabId:t?.id||null,url:t?.url||null,fixtureId:state.capture?.activeTabId===t?.id?(state.fixtureId||null):null});
  break;
}
case"OPEN_SIDE_PANEL":{
  try{
    if(chrome.sidePanel&&typeof chrome.sidePanel.open==="function"){
      const w=await chrome.windows.getCurrent();
      await chrome.sidePanel.open({windowId:w.id});
      sendResponse({ok:true,mode:"sidePanel"});
    }else{
      const url=chrome.runtime.getURL("visao/sidepanel.html");
      await chrome.windows.create({url,type:"popup",width:420,height:640,focused:true});
      sendResponse({ok:true,mode:"popup"});
    }
  }catch(e){
    try{
      const url=chrome.runtime.getURL("visao/sidepanel.html");
      await chrome.windows.create({url,type:"popup",width:420,height:640,focused:true});
      sendResponse({ok:true,mode:"popup-fallback"});
    }catch(e2){sendResponse({ok:false,error:(e2?.message||e?.message||String(e))});}
  }
  break;}

case"CAPTURE_VISIBLE_TAB":{
  try{
    // FIX 12.5.9: captureVisibleTab só é permitido em abas cobertas pelos
    // host_permissions (sokkerpro.com/*) ou pela concessão temporária de
    // activeTab — que só vale na mesma ação de clique que ativou a extensão,
    // não em cliques posteriores dentro do side panel. Antes disto, quando
    // a aba ativa da janela atual não era o SokkerPRO (ou a query de
    // currentWindow não resolvia a janela certa a partir do service worker),
    // o código caía em tabs[0]/qualquer aba ativa — fora do host_permissions
    // — e o Chrome recusava com "Either the '<all_urls>' or 'activeTab'
    // permission is required.". Agora priorizamos a aba SokkerPRO já armada
    // para a captura (state.capture.activeTabId), que está garantidamente
    // coberta pelos host_permissions.
    let tabId = Number(msg.tabId)||0;
    let winId = null;
    const armedTabId = Number(state.capture?.activeTabId)||0;
    if(!tabId && armedTabId){
      try{ const t=await chrome.tabs.get(armedTabId); tabId=t.id; winId=t.windowId; }catch{}
    }
    if(tabId>0 && !winId){
      try{ const t=await chrome.tabs.get(tabId); winId=t.windowId; }catch{}
    }
    if(!winId){
      const allTabs=await chrome.tabs.query({});
      const sok=allTabs.find(t=>t.url&&/sokkerpro\.com/i.test(t.url)&&t.active) || allTabs.find(t=>t.url&&/sokkerpro\.com/i.test(t.url));
      if(!sok){ sendResponse({ok:false,error:"Nenhuma aba do SokkerPRO encontrada. Abra a partida e ative a captura antes de usar VISÃO."}); break; }
      tabId=sok.id; winId=sok.windowId;
    }
    const dataUrl=await captureVisibleTabThrottled(winId);
    sendResponse({ok:true,dataUrl,tabId});
  }catch(e){ sendResponse({ok:false,error:e?.message||String(e)}); }
  break;}
case"OPEN_DASHBOARD_WINDOW":{const r=await openToolWindow("dashboard");sendResponse(r);break;}
 case"OPEN_DIAGNOSTICS_WINDOW":{const r=await openToolWindow("diagnostics");sendResponse(r);break;}
 case"RUN_ALL_TOOLS_TEST":{
  const requestedTabId=Number(msg.tabId);let tab=null;
  if(Number.isInteger(requestedTabId)&&requestedTabId>0){try{tab=await chrome.tabs.get(requestedTabId)}catch{tab=null}}
  if(!tab){const tabs=await chrome.tabs.query({active:true,currentWindow:true});tab=tabs.find(x=>isSokkerUrl(x.url));}
  if(!tab?.id||!(await isSokkerUrl(tab.url))){sendResponse({ok:false,error:"Abra uma partida do SokkerPRO."});break;}
  const ready=await ensureContentScript(tab.id,tab.url);
  if(!ready){sendResponse({ok:false,error:"Content script indisponível. Recarregue a partida."});break;}
  try{
    // Freeze the audit to the exact page fixture/tab before executing any tool.
    const probe=await chrome.tabs.sendMessage(tab.id,{type:"GET_FIXTURE_ID"});
    const pageFixture=probe?.fixtureId?String(probe.fixtureId):"";
    if(!pageFixture){sendResponse({ok:false,error:"Auditoria | fixture não identificado na página"});break;}
    if(state.capture?.activeTabId!=null && Number(state.capture.activeTabId)!==Number(tab.id)){
      sendResponse({ok:false,error:`Auditoria | aba proprietária diferente (${state.capture.activeTabId} ≠ ${tab.id})`});break;
    }
    if(state.fixtureId && String(state.fixtureId)!==pageFixture){
      sendResponse({ok:false,error:`Auditoria | fixture divergente (${state.fixtureId} ≠ ${pageFixture})`});break;
    }
    state.fixtureId=pageFixture;
    state.capture.activeTabId=tab.id;
    state.capture.armed=true;
    state.capture.manualConsent=true;
    const armed=await chrome.tabs.sendMessage(tab.id,{type:"ARM_CAPTURE"}).catch(e=>({ok:false,error:e?.message||String(e)}));
    // 9.2.5: if ARM ok but fixtureId missing (async channel race), accept pageFixture
    if(!armed?.ok){
      // still try harvest so audit can proceed
      try{ await forceDomHarvest(tab.id); }catch{}
      if(!state.fixtureId){ sendResponse({ok:false,error:"Falha ao armar o motor: "+(armed?.error||"sem resposta")}); break; }
    }
    const armFid=String(armed?.fixtureId||state.fixtureId||pageFixture||"");
    if(armFid && armFid!==pageFixture){
      sendResponse({ok:false,error:`Auditoria | ARM retornou fixture divergente (${armFid} ≠ ${pageFixture})`});break;
    }
    state.fixtureId=pageFixture;
    state.capture.armed=true;
    state.capture.manualConsent=true;
    try{ await forceDomHarvest(tab.id); }catch{}
    await awaitPersist();
    let r=null;
    try{ r=await chrome.tabs.sendMessage(tab.id,{type:"RUN_ALL_TOOLS_TEST"}); }catch(e){ r={ok:false,error:e?.message||String(e)}; }
    if(!r?.report){
      await new Promise(resolve=>setTimeout(resolve,250));
      try{ r=await chrome.tabs.sendMessage(tab.id,{type:"GET_LAST_PAGE_TOOL_TEST"}); }catch{}
    }
    if(!r?.report){
      sendResponse({ok:false,error:`Auditoria não retornou relatório da página: ${r?.error||"sem resposta do content script"}`});
      break;
    }
    await new Promise(resolve=>setTimeout(resolve,300));
    let page=null;try{page=await chrome.tabs.sendMessage(tab.id,{type:"COLLECT_DIAGNOSTICS"});}catch{}
    const report={...(r.report||{}),background:{acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),hookMessages:Number(state.diagnostics.hookMessages||0),networkResponses:Number(state.diagnostics.networkResponses||0),binaryWsDecoded:Number(state.diagnostics.binaryWsDecoded||0),binaryWsUnknown:Number(state.diagnostics.binaryWsUnknown||0),foreignFixture:Number(state.diagnostics.foreignFixturePayloads||0),foreignTab:Number(state.diagnostics.foreignTabPayloads||0),dispatchFailures:Number(state.diagnostics.captureDispatchFailures||0)},page:page||null};
    report.schema=report.schema||"cornerai-all-tools-test-2";
    report.version=report.version||VERSION;
    report.fixtureId=report.fixtureId||state.fixtureId||page?.fixtureId||null;
    report.durationMs=Number(report.durationMs||0);
    if(String(report.fixtureId||"")!==String(pageFixture||"")){
      state.diagnostics.foreignFixturePayloads=(state.diagnostics.foreignFixturePayloads||0)+1;
      report.results=Array.isArray(report.results)?report.results:[];
      report.results.push({id:"isolation",label:"🛡️ Isolamento",status:"FAIL",detail:`auditoria retornou fixture ${report.fixtureId||"—"} · esperado ${pageFixture}`});
      report.summary={total:report.results.length,pass:report.results.filter(x=>x.status==="PASS").length,fail:report.results.filter(x=>x.status==="FAIL").length,pending:report.results.filter(x=>x.status==="AGUARDANDO").length};
      report.rejected=true;
    }
    const bgTools=[
      {id:"h2h",label:"🤝 H2H",status:(state.h2h?.captured||Number(state.h2h?.matches?.length||0)>0||Number(state.h2h?.tables?.length||0)>0||Number(state.h2h?.rows||0)>0)?"PASS":"AGUARDANDO",detail:(state.h2h?.captured||Number(state.h2h?.matches?.length||0)>0)?`${state.h2h.matches?.length||0} jogos · ${state.h2h.tables?.length||0} tabelas · W${state.h2h?.summary?.homeWins??"?"} D${state.h2h?.summary?.draws??"?"} L${state.h2h?.summary?.awayWins??"?"}`:"H2H ainda não consolidado no background"},
      {id:"hook",label:"🪝 Hook",status:Number(state.diagnostics.hookMessages||0)>0?"PASS":"AGUARDANDO",detail:`${Number(state.diagnostics.hookMessages||0)} mensagens · último ${state.diagnostics.lastHookAt?new Date(state.diagnostics.lastHookAt).toLocaleTimeString():"—"}`},
      {id:"network",label:"🌐 Network",status:Number(state.diagnostics.networkResponses||0)>0?"PASS":"AGUARDANDO",detail:`${Number(state.diagnostics.networkResponses||0)} respostas observadas`},
      {id:"websocket",label:"🔌 WebSocket",status:(Number(state.diagnostics.wsOpenCount||0)+Number(state.diagnostics.wsCloseCount||0))>0?"PASS":"AGUARDANDO",detail:`abertos ${Number(state.diagnostics.wsOpenCount||0)} · fechados ${Number(state.diagnostics.wsCloseCount||0)} · binários ${Number(state.diagnostics.binaryWsDecoded||0)}`},
      {id:"isolation",label:"🛡️ Isolamento",status:Number(state.diagnostics.foreignFixturePayloads||0)===0?(Number(state.diagnostics.foreignTabPayloads||0)>50?"AGUARDANDO":"PASS"):"FAIL",detail:`fixture ${Number(state.diagnostics.foreignFixturePayloads||0)} · aba ${Number(state.diagnostics.foreignTabPayloads||0)} · rebinds ${Number(state.diagnostics.tabRebinds||0)}`},
      {id:"persistence",label:"💾 Persistência",status:Number(state.diagnostics.persistErrors||0)===0?"PASS":"FAIL",detail:`erros ${Number(state.diagnostics.persistErrors||0)}`},
      {id:"bridge",label:"🌉 Bridge/Webhook",status:state.webhook?.bridgeOffline?"AGUARDANDO":(state.webhook?.lastOkAt?"PASS":"AGUARDANDO"),detail:state.webhook?.bridgeOffline?"offline · serviço local indisponível":`enviados ${Number(state.webhook?.sent||0)} · pendentes ${Number(state.webhook?.pending||0)}`,external:true},
      {id:"local-ai",label:"🧠 Local AI Engine",status:state.diagnostics?.lastLocalAiOk?"PASS":(state.diagnostics?.lastLocalAiPushAt?"AGUARDANDO":"AGUARDANDO"),detail:state.diagnostics?.lastLocalAiOk?`OK · último push ${new Date(state.diagnostics.lastLocalAiPushAt).toLocaleTimeString()}`:(state.diagnostics?.lastLocalAiError?`erro: ${String(state.diagnostics.lastLocalAiError).slice(0,80)}`:"sem push ainda · verifique Engine :8765"),external:true}
    ];
    // Merge page + background evidence without duplicating tools.
    // Prefer the page result when the tool was actually observed there;
    // use background-only checks only when the page did not report that id.
    const merged=[];
    const byId=new Map();
    for(const item of (report.results||[])){
      if(!item?.id) continue;
      if(!byId.has(item.id)){ byId.set(item.id,item); merged.push(item); }
      else {
        const prev=byId.get(item.id);
        // Prefer PASS over FAIL/AGUARDANDO, then FAIL over AGUARDANDO.
        const rank={PASS:3,FAIL:2,AGUARDANDO:1};
        if((rank[item.status]||0)>(rank[prev.status]||0)){
          const i=merged.indexOf(prev); if(i>=0) merged[i]=item;
          byId.set(item.id,item);
        }
      }
    }
    for(const item of bgTools){
      if(!item?.id) continue;
      if(!byId.has(item.id)){ byId.set(item.id,item); merged.push(item); }
      else {
        const prev=byId.get(item.id);
        const rank={PASS:3,FAIL:2,AGUARDANDO:1};
        if((rank[item.status]||0)>(rank[prev.status]||0)){
          const i=merged.indexOf(prev); if(i>=0) merged[i]=item;
          byId.set(item.id,item);
        }
      }
    }
    report.results=merged;
    report.summary={total:report.results.length,pass:report.results.filter(x=>x.status==="PASS").length,fail:report.results.filter(x=>x.status==="FAIL").length,pending:report.results.filter(x=>x.status==="AGUARDANDO").length};
    report.consistency={
      duplicateIds:[],
      mergedSources:true,
      note:"Resultados de página e background consolidados por id; PASS tem prioridade sobre FAIL/AGUARDANDO."
    };
    state.diagnostics.lastToolTest=report;state.diagnostics.lastDiagnosticAt=Date.now();await awaitPersist();
    sendResponse({ok:true,tabId:tab.id,fixtureId:report.fixtureId||state.fixtureId||null,report});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;}
 case"FORCE_CAPTURE_REQUEST":{const requestedTabId=Number(msg.tabId);let tab=null;if(Number.isInteger(requestedTabId)&&requestedTabId>0){try{tab=await chrome.tabs.get(requestedTabId)}catch{tab=null}}if(!tab){const tabs=await chrome.tabs.query({active:true,currentWindow:true});tab=tabs.find(x=>isSokkerUrl(x.url));}if(!tab?.id||!(await isSokkerUrl(tab.url))){sendResponse({ok:false,error:"Abra o SokkerPRO."});break;}const ready=await ensureContentScript(tab.id,tab.url);if(!ready){sendResponse({ok:false,error:"CAPTURA | Content script indisponível. Recarregue a aba do SokkerPRO e tente novamente."});break;}try{const r=await chrome.tabs.sendMessage(tab.id,{type:"FORCE_CAPTURE"});sendResponse({ok:r?.ok!==false,tabId:tab.id,...(r||{})});}catch(e){sendResponse({ok:false,error:e.message});}break;}
 case"RESET_STATE":state=defaultState();await awaitPersist();sendResponse({ok:true,state:clone(state)});break;
 case"SELF_TEST":sendResponse(runSelfTest());break;
 case"GET_ALERT_PREFS":{
  if(!state.alertPrefs) await loadAlertPrefs();
  sendResponse({ok:true,prefs:state.alertPrefs||DEFAULT_ALERT_PREFS});
  break;}
 case"SET_ALERT_PREFS":{
  const prefs=await saveAlertPrefs(msg.prefs||msg.payload||{});
  sendResponse({ok:true,prefs});
  break;}


 case"GET_LIVE_FEED":{
  try{
    const tabs=await chrome.tabs.query({});
    for(const t of tabs){
      if(!t?.id) continue;
      let sok=false;
      try{sok=await isSokkerUrl(t.url);}catch{}
      if(!sok) continue;
      try{
        const ready=await ensureContentScript(t.id,t.url);
        if(!ready) continue;
        const r=await chrome.tabs.sendMessage(t.id,{type:"SCAN_FIXTURE_LINKS"});
        if(r?.ok && Array.isArray(r.fixtures)) upsertLiveFeed(r.fixtures, "tab-scan");
        let fid=null;
        try{
          const m=String(t.url||"").match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
          if(m) fid=m[1];
        }catch{}
        if(fid) upsertLiveFeed([{fixtureId:fid,url:t.url,label:t.title||"",live:true}], "open-tab");
      }catch{}
    }
    const fixtures=listLiveFeed(msg.limit||40);
    sendResponse({ok:true,count:fixtures.length,fixtures,updatedAt:Date.now()});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e),fixtures:[]});}
  break;}
 case"LIST_SOKKER_TABS":{
  try{
    const tabs=await chrome.tabs.query({});
    const out=[];
    for(const t of tabs){
      if(!t?.id || !isSokkerUrl(t.url)) continue;
      let fid=null;
      try{
        const m=String(t.url||"").match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
        if(m) fid=m[1];
        if(!fid){
          const q=new URL(t.url); fid=q.searchParams.get("fixture")||q.searchParams.get("matchId");
        }
      }catch{}
      out.push({
        tabId:t.id,
        fixtureId:fid?String(fid):null,
        title:String(t.title||"").slice(0,120),
        url:String(t.url||""),
        active:!!t.active,
        windowId:t.windowId
      });
    }
    sendResponse({ok:true,tabs:out,count:out.length});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e),tabs:[]});}
  break;}
 case"OPEN_AND_ARM_FIXTURE":{
  try{
    let fid=msg.fixtureId!=null?String(msg.fixtureId).trim():"";
    let url=msg.url?String(msg.url).trim():"";
    const tabIdHint=Number(msg.tabId);
    if(!fid && url){
      const m=url.match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
      if(m) fid=m[1];
    }
    if(!fid && !(Number.isInteger(tabIdHint)&&tabIdHint>0)){
      sendResponse({ok:false,error:"Informe fixtureId, url ou tabId"});
      break;
    }
    if(!url && fid) url=`https://sokkerpro.com/fixture/${fid}`;
    let tab=null;
    if(Number.isInteger(tabIdHint)&&tabIdHint>0){
      try{tab=await chrome.tabs.get(tabIdHint);}catch{tab=null;}
    }
    if(!tab && fid){
      // Reuse existing tab with same fixture if open
      const tabs=await chrome.tabs.query({});
      for(const t of tabs){
        if(!isSokkerUrl(t.url)) continue;
        if(String(t.url||"").includes(fid)){ tab=t; break; }
      }
    }
    if(tab){
      await chrome.tabs.update(tab.id,{active:true,url: url || tab.url});
      try{await chrome.windows.update(tab.windowId,{focused:true});}catch{}
    } else {
      tab=await chrome.tabs.create({url:url,active:true});
    }
    // Wait load
    const waitLoad=()=>new Promise(resolve=>{
      const to=setTimeout(()=>resolve(false),25000);
      function onUpd(id,info){
        if(id===tab.id && info.status==="complete"){
          clearTimeout(to); chrome.tabs.onUpdated.removeListener(onUpd); resolve(true);
        }
      }
      chrome.tabs.onUpdated.addListener(onUpd);
      chrome.tabs.get(tab.id).then(t=>{ if(t.status==="complete"){ clearTimeout(to); chrome.tabs.onUpdated.removeListener(onUpd); resolve(true);} }).catch(()=>{});
    });
    await waitLoad();
    await new Promise(r=>setTimeout(r,900));
    const ready=await ensureContentScript(tab.id,url);
    if(!ready){ sendResponse({ok:false,error:"Content script indisponível. Recarregue a aba.",tabId:tab.id,fixtureId:fid||null}); break; }
    // Probe fixture
    let probe=null;
    for(let i=0;i<5;i++){
      try{probe=await chrome.tabs.sendMessage(tab.id,{type:"GET_FIXTURE_ID"});}catch{}
      if(probe?.ok && probe.fixtureId) break;
      await new Promise(r=>setTimeout(r,700));
    }
    const fixture=String(probe?.fixtureId||fid||"");
    if(!fixture){ sendResponse({ok:false,error:"Não foi possível ler o fixture nesta página.",tabId:tab.id}); break; }
    // Reset session to this fixture
    state=defaultState();
    state.capture.activeTabId=tab.id;
    state.capture.armed=true;
    state.capture.manualConsent=true;
    state.capture.sessionId=`${fixture}:${tab.id}:${Date.now().toString(36)}`;
    state.fixtureId=fixture;
    state.url=String(url||tab.url||"");
    state.lastUpdate=Date.now();
    await awaitPersist();
    try{await chrome.tabs.sendMessage(tab.id,{type:"ARM_CAPTURE"});}catch{}
    try{await chrome.tabs.sendMessage(tab.id,{type:"FORCE_CAPTURE"});}catch{}
    let harvest=null;
    try{harvest=await forceDomHarvest(tab.id);}catch(e){harvest={ok:false,error:e?.message||String(e)};}
    sendResponse({
      ok:true,
      fixtureId:fixture,
      tabId:tab.id,
      url:state.url,
      acceptedSnapshots:state.capture?.acceptedSnapshots||0,
      harvest:harvest||null,
      home:state.home||null,
      away:state.away||null,
      score:state.score||null
    });
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;}
 case"GET_MATCH_HISTORY":{
  const rows=await idbListMatches(Number(msg.limit||30));
  sendResponse({ok:true,matches:rows,count:rows.length});
  break;}
 case"GET_FEEDBACK_STATS":{
  sendResponse({ok:true,stats:state.feedback?.stats||null,pending:(state.feedback?.pending||[]).length,resolved:(state.feedback?.resolved||[]).length});
  break;}
 case"GET_SKILL_MONITOR":{
  try{await loadSkillMonitor();}catch{}
  sendResponse({ok:true, monitor:buildSkillMonitorReport()});
  break;}
 case"TEST_SKILL_CONNECTION":{
  const r=await testSkillConnection();
  sendResponse({ok:!!r.ok, ...r, monitor:buildSkillMonitorReport()});
  break;}
 case"CLEAR_SKILL_MONITOR":{
  __skillMonitor.log=[];
  __skillMonitor.lastIn=null;
  __skillMonitor.lastOut=null;
  __skillMonitor.lastError=null;
  __skillMonitor.totals={requests:0,ok:0,fail:0,bytesIn:0,bytesOut:0};
  await persistSkillMonitor();
  sendResponse({ok:true, monitor:buildSkillMonitorReport()});
  break;}
 case"GET_SKILL_LAST_PAYLOAD":{
  const compact=(typeof buildGeminiCompactPayload==="function")?buildGeminiCompactPayload():null;
  const prompt=(typeof buildGeminiPrompt==="function")?buildGeminiPrompt(compact):null;
  sendResponse({ok:true, payload:compact, prompt, promptChars:String(prompt||"").length, lastIn:__skillMonitor.lastIn, lastOut:__skillMonitor.lastOut});
  break;}
 case"GET_GEMINI":{
  await loadGeminiConfig();
  sendResponse({ok:true, config: publicGeminiStatus()});
  break;}
 case"SET_GEMINI":{
  const p=msg.config||msg.payload||{};
  const out=await saveGeminiConfig({
    enabled: p.enabled!=null?!!p.enabled:__geminiCfg.enabled,
    auto: p.auto!=null?!!p.auto:__geminiCfg.auto,
    apiKey: p.apiKey!==undefined?(p.apiKey||null):__geminiCfg.apiKey,
    model: p.model||__geminiCfg.model,
    intervalMs: p.intervalMs!=null?Number(p.intervalMs):__geminiCfg.intervalMs,
    onAlert: p.onAlert!=null?!!p.onAlert:__geminiCfg.onAlert,
    temperature: p.temperature!=null?Number(p.temperature):__geminiCfg.temperature,
    maxOutputTokens: p.maxOutputTokens!=null?Number(p.maxOutputTokens):__geminiCfg.maxOutputTokens,
    economy: p.economy!=null?!!p.economy:__geminiCfg.economy,
    onlyCriticalWindows: p.onlyCriticalWindows!=null?!!p.onlyCriticalWindows:__geminiCfg.onlyCriticalWindows,
    maxCallsPerMatch: p.maxCallsPerMatch!=null?Number(p.maxCallsPerMatch):__geminiCfg.maxCallsPerMatch,
    maxCallsPerDay: p.maxCallsPerDay!=null?Number(p.maxCallsPerDay):__geminiCfg.maxCallsPerDay
  });
  sendResponse({ok:true, config:out});
  break;}
 case"RUN_GEMINI":{
  const r=await callGeminiAPI(msg.reason||"manual");
  sendResponse(r);
  break;}
 case"GET_GEMINI_RESULTS":{
  const stored=await chrome.storage.local.get(["cornerai_gemini_results"]);
  sendResponse({ok:true, results:Array.isArray(stored.cornerai_gemini_results)?stored.cornerai_gemini_results.slice(0,Number(msg.limit||10)):[]});
  break;}
 case"GET_EXPLAIN":{
  const bundle=(typeof buildExplainabilityBundle==="function")?buildExplainabilityBundle():null;
  sendResponse({ok:true, explain:bundle, lastAlert:state.lastAlertExplanation||null, drift:state.drift||null});
  break;}
 case"GET_DRIFT":{
  try{runCusumDriftCheck();}catch{}
  sendResponse({ok:true, drift:state.drift||null});
  break;}
 case"EXPORT_STATE":sendResponse({ok:true,version:VERSION,parameters:PARAMS,schemaVersion:"cornerai-export-6",aiFeed:buildAIFeed(),analyst:buildAnalystFeed(),state:clone(state),exportedAt:new Date().toISOString()});break;
 case"AI_HANDOFF_REQUEST":{const feed=buildAIFeed();const analyst=buildAnalystFeed();const handoff={schema:"cornerai-gemini-handoff-2",createdAt:new Date().toISOString(),fixtureId:state.fixtureId,match:{home:state.home,away:state.away,score:state.score,minute:state.minute,liveStatus:state.liveStatus},analyst,feed,state:clone(state)};await chrome.storage.local.set({cornerai_ai_handoff:handoff});sendResponse({ok:true,feed:handoff,analyst});break;}
 case"GEMINI_SYNC_REQUEST":{
  try{
    var connector = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    if(!connector || typeof connector.prepareFromState !== "function"){
      sendResponse({ok:false, error:"gemini-connector não carregado"});
      break;
    }
    var payload = connector.prepareFromState(state);
    if(!payload){
      sendResponse({ok:false, error:"estado inválido para payload Gemini"});
      break;
    }
    if(!msg.forceHttp && connector.wsStatus && connector.wsStatus().state==="open"){
      var wsRes = connector.sendViaWebSocket(payload, !!msg.force);
      sendResponse(Object.assign({ok:!!wsRes.ok, via:"websocket"}, wsRes, msg.includePayload?{payload:payload}:{}));
      break;
    }
    if(msg.endpointUrl){
      var res = await connector.sendToGeminiSkill(msg.endpointUrl, payload, msg.apiKey || null);
      sendResponse(Object.assign({}, res, {via:"http"}));
    } else {
      sendResponse({ok:true, payload: payload, via:"preview"});
    }
  }catch(e){
    sendResponse({ok:false, error: e?.message || String(e)});
  }
  break;
 }
 case"GEMINI_WS_CONNECT":{
  try{
    var cWs = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    if(!cWs || typeof cWs.connectWebSocket !== "function"){
      sendResponse({ok:false, error:"gemini-connector sem WebSocket"});
      break;
    }
    var wsUrl = msg.url || msg.endpointUrl || null;
    var wsKey = msg.apiKey || null;
    if(wsUrl){
      try{
        await chrome.storage.local.set({
          cornerai_gemini_ws_url: wsUrl,
          cornerai_gemini_skill_url: wsUrl,
          cornerai_gemini_skill_key: wsKey || ""
        });
      }catch{}
    }
    var rWs = cWs.connectWebSocket(wsUrl, wsKey);
    if(rWs && rWs.ok){
      setTimeout(function(){
        try{ if(cWs.wsStatus().state==="open") cWs.pushState(state, true); }catch{}
      }, 400);
    }
    sendResponse(rWs);
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"GEMINI_WS_DISCONNECT":{
  try{
    var cOff = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    if(!cOff){ sendResponse({ok:false, error:"connector ausente"}); break; }
    sendResponse(cOff.disconnectWebSocket());
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"GEMINI_WS_STATUS":{
  try{
    var cSt = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    sendResponse({ok:true, status: cSt && cSt.wsStatus ? cSt.wsStatus() : {state:"unavailable"}});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"GEMINI_WS_PUSH":{
  try{
    var cPush = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    if(!cPush){ sendResponse({ok:false, error:"connector ausente"}); break; }
    sendResponse(cPush.pushState(state, !!msg.force));
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"TEST_EVENTOS_FLASK":{
  try{
    if(msg.url) __eventosFlaskUrl = String(msg.url).trim();
    if(msg.enabled!=null) __eventosFlaskEnabled = !!msg.enabled;
    const r = await postEventosFlask(true);
    sendResponse(r);
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"SET_EVENTOS_FLASK":{
  try{
    if(msg.url!=null) __eventosFlaskUrl = String(msg.url).trim() || EVENTOS_FLASK_DEFAULT;
    if(msg.enabled!=null) __eventosFlaskEnabled = !!msg.enabled;
    try{ await chrome.storage.local.set({ cornerai_eventos_flask_url: __eventosFlaskUrl, cornerai_eventos_flask_enabled: __eventosFlaskEnabled }); }catch{}
    sendResponse({ok:true, url:__eventosFlaskUrl, enabled:__eventosFlaskEnabled});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"GET_EVENTOS_DIAG":{
  try{
    sendResponse({ok:true, eventos:getEventosDiagSnapshot()});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"PRUNE_STORAGE":{
  try{
    const r = await emergencyStoragePrune();
    sendResponse({ok:!!r.ok, ...r});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"EXPERIENCE_HEALTH":{
  try{
    var base = (msg.baseUrl || "http://127.0.0.1:3000").replace(/\/$/,"");
    var ctrl = typeof AbortSignal!=="undefined"&&AbortSignal.timeout?AbortSignal.timeout(2500):undefined;
    var res = await fetch(base + "/health", { method:"GET", signal: ctrl });
    var data = await res.json().catch(()=>({}));
    sendResponse({ ok: !!res.ok, status: res.status, online: !!res.ok, health: data, via: "http" });
  }catch(e){
    sendResponse({ ok:false, online:false, error: e?.message||String(e), via:"http" });
  }
  break;
 }
 case"RUN_EXPERIENCE_V10":{
  try{
    var connector = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    if(!connector){ sendResponse({ok:false, error:"gemini-connector ausente"}); break; }
    var payload = connector.prepareFromState(state);
    if(!payload){ sendResponse({ok:false, error:"payload inválido"}); break; }
    var endpoint = msg.endpointUrl || "http://127.0.0.1:3000/experience";
    var res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CornerAI-Schema": payload.schemaVersion || "cornerai-gemini-v1.1" },
      body: JSON.stringify(payload)
    });
    var data = await res.json().catch(()=>({}));
    if(!res.ok){
      sendResponse({ok:false, error: data.error || ("HTTP "+res.status), status: res.status, raw: data});
      break;
    }
    sendResponse({ok:true, via:"experience-v10", decision: data.decision || data, totalHistory: data.totalHistory, success: data.success});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }
 case"RUN_GEMINI_V10":{
  try{
    await loadGeminiConfig();
    var key = msg.apiKey || (__geminiCfg && __geminiCfg.apiKey) || null;
    if(!key){
      try{
        const st = await chrome.storage.local.get(["cornerai_gemini","cornerai_gemini_skill_key"]);
        key = (st.cornerai_gemini && st.cornerai_gemini.apiKey) || st.cornerai_gemini_skill_key || null;
      }catch{}
    }
    if(!key){ sendResponse({ok:false, error:"api_key_missing — cole a key no AUTO-GEMINI ou no card Skill"}); break; }
    var connector = (typeof CornerAIGeminiConnector !== "undefined") ? CornerAIGeminiConnector : null;
    var gem = (typeof CornerAIGemV10 !== "undefined") ? CornerAIGemV10 : null;
    if(!connector || !gem){ sendResponse({ok:false, error:"connectors não carregados"}); break; }
    var payload = connector.prepareFromState(state);
    if(!payload){ sendResponse({ok:false, error:"payload inválido"}); break; }
    var model = msg.model || (__geminiCfg && __geminiCfg.model) || "gemini-2.0-flash";
    var result = await gem.analyzeWithGemV10({
      apiKey: key,
      model: model,
      payload: payload,
      systemInstruction: msg.systemInstruction || null,
      temperature: msg.temperature != null ? msg.temperature : 0.2,
      maxOutputTokens: msg.maxOutputTokens != null ? msg.maxOutputTokens : 500
    });
    if(result && result.ok){
      try{
        const stored = await chrome.storage.local.get(["cornerai_gemini_v10_results"]);
        const arr = Array.isArray(stored.cornerai_gemini_v10_results) ? stored.cornerai_gemini_v10_results : [];
        arr.unshift({
          at: Date.now(),
          fixtureId: state.fixtureId,
          minute: state.minute,
          model: model,
          analysis: result.analysis,
          text: result.text
        });
        await chrome.storage.local.set({ cornerai_gemini_v10_results: arr.slice(0, 30) });
      }catch{}
    }
    sendResponse(Object.assign({ via: "gemini-api-v10", payloadPreview: {
      schema: payload.schemaVersion,
      fixtureId: payload.matchContext && payload.matchContext.fixtureId,
      clock: payload.matchContext && payload.matchContext.clock
    }}, result));
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;
 }

  case"EXPORT_SKILL_PACK":{
  try{
    const gate=exportQualityGate({force:!!msg.force});
    if(gate.blocked && !msg.force){
      sendResponse({ok:false,error:"quality_gate",gate,errors:gate.errors});
      break;
    }
    const pack = buildSkillPackForChat();
    let bridgeOk=false, bridgeErr=null, bridgeFiles=null;
    try{
      const url=(state.webhook?.url||"http://127.0.0.1:8080/api/cornerai/feed").replace(/\/api\/cornerai\/feed\/?$/,"/api/cornerai/skill-feed").replace(/\/feed\/?$/,"/skill-feed");
      const skillUrl = url.includes("skill-feed")?url:"http://127.0.0.1:8080/api/cornerai/skill-feed";
      const res=await fetch(skillUrl,{
        method:"POST",
        headers:{"Content-Type":"application/json","X-CornerAI-Schema":"cornerai-skill-v3"},
        body:JSON.stringify({json:pack.json||pack.pack, pack:pack.pack||pack.json, pasteText:pack.pasteText, filename:pack.filename})
      });
      const body=await res.json().catch(()=>({}));
      bridgeOk=!!res.ok && body.ok!==false;
      bridgeFiles=body.files||null;
      if(!bridgeOk) bridgeErr=body.error||("HTTP "+res.status);
    }catch(e){ bridgeErr=e?.message||String(e); }
    sendResponse({...pack, bridgeOk, bridgeErr, bridgeFiles});
  }catch(e){ sendResponse({ok:false, error:e?.message||String(e)}); }
  break;}
case"EXPORT_ANALYST":sendResponse({ok:true,version:VERSION,analyst:buildAnalystFeed(),exportedAt:new Date().toISOString()});break;
 case"SET_WEBHOOK":{
   const url=msg.url!=null?String(msg.url).trim():"";
   const enabled=msg.enabled!=null?!!msg.enabled:true;
   if(url&&!/^https?:\/\//i.test(url)){sendResponse({ok:false,error:"URL inválida"});break;}
   await chrome.storage.local.set({cornerai_webhook_url:url||null,cornerai_webhook_enabled:enabled});
   state.webhook=state.webhook||{}; state.webhook.url=url||null; PARAMS.webhookEnabled=enabled;
   sendResponse({ok:true,url:state.webhook.url,enabled});
   break;
 }
 case"GET_WEBHOOK":{
   await loadWebhookConfig();
   sendResponse({ok:true,url:state.webhook?.url||null,enabled:!!PARAMS.webhookEnabled,sent:state.webhook?.sent||0,failed:state.webhook?.failed||0,dropped:state.webhook?.dropped||0,pending:(state.outbox||[]).length,lastOkAt:state.webhook?.lastOkAt||0,lastError:state.webhook?.lastError||null,bridgeOffline:!!state.webhook?.bridgeOffline,offlineSince:state.webhook?.offlineSince||0,lastRecoveryAt:state.webhook?.lastRecoveryAt||0});
   break;
 }
 case"LOCAL_AI_ANALYSIS":{
   try{
     const fid=String(msg.fixtureId||state.fixtureId||"").trim();
     if(!fid){sendResponse({ok:false,error:"fixtureId ausente"});break;}
     const classic=String(LOCAL_AI?.classicUrl||"http://127.0.0.1:8765").replace(/\/$/,"");
     const gpu=String(LOCAL_AI?.gpuUrl||"http://127.0.0.1:8000").replace(/\/$/,"");
     const urls=[classic+"/api/analysis/"+encodeURIComponent(fid)];
     if(gpu!==classic) urls.push(gpu+"/api/analysis/"+encodeURIComponent(fid));
     (async()=>{
       let lastError="nenhum endpoint respondeu";
       for(const u of urls){
         try{
           const r=await fetch(u,{signal:AbortSignal.timeout?AbortSignal.timeout(1800):undefined});
           const data=await r.json().catch(()=>({}));
           if(r.ok){sendResponse({ok:true,analysis:data,via:u});return;}
           lastError=`HTTP ${r.status} · ${data?.error||"resposta inválida"} · endpoint ${u}`;
         }catch(e){
           const raw=String(e?.message||e||"erro de rede");
           lastError=/abort|timeout/i.test(raw)?`timeout após 1,8s · endpoint ${u}`:`sem conexão com ${u} · ${raw}`;
         }
       }
       sendResponse({ok:false,error:`Engine OFFLINE: ${lastError}. Execute AURA_INSTALAR_E_INICIAR_TUDO.bat e aguarde os health checks.`,endpoint:classic,optional:true});
     })();
   }catch(e){sendResponse({ok:false,error:String(e?.message||e)});}
   return true;
 }
 case"FLUSH_OUTBOX":{
   const r=await flushAnalystOutbox();
   sendResponse({ok:!!r?.ok,...r});
   break;
 }
 case"PUSH_ANALYST":{
   const analyst=buildAnalystFeed();
   const gate=analystPublishable(analyst);
   if(!gate.ok){sendResponse({ok:false,reason:gate.reason,analyst});break;}
   const queued=enqueueAnalystOutbox(analyst,msg.reason||"manual");
   const flushed=await flushAnalystOutbox();
   sendResponse({ok:true,queued,flushed,analyst});
   break;
 }
 case"ARM_ACTIVE_GAME":{const requestedTabId=Number(msg.tabId);let tab=null;if(Number.isInteger(requestedTabId)&&requestedTabId>0){try{tab=await chrome.tabs.get(requestedTabId)}catch{tab=null}}if(!tab){const tabs=await chrome.tabs.query({active:true,currentWindow:true});tab=tabs.find(x=>isSokkerUrl(x.url));}if(!tab?.id||!(await isSokkerUrl(tab.url))){sendResponse({ok:false,error:"Abra o SokkerPRO."});break;}const previousTabId=state.capture?.activeTabId;if(previousTabId!=null&&previousTabId!==tab.id){try{await chrome.tabs.sendMessage(previousTabId,{type:"STOP_CAPTURE"})}catch{}}const ready=await ensureContentScript(tab.id,tab.url);if(!ready){sendResponse({ok:false,error:"CAPTURA | Content script indisponível. Recarregue a aba do SokkerPRO e tente novamente."});break;}try{const probe=await chrome.tabs.sendMessage(tab.id,{type:"GET_FIXTURE_ID"});if(!probe?.ok||!probe.fixtureId){sendResponse({ok:false,error:"Abra uma partida do SokkerPRO."});break;}const fixture=String(probe.fixtureId);if(String(state.fixtureId||"")!==fixture||state.capture.activeTabId!==tab.id){state=defaultState();state.capture.activeTabId=tab.id;state.capture.armed=true;state.capture.manualConsent=true;state.capture.sessionId=`${fixture}:${tab.id}:${Date.now().toString(36)}`;state.fixtureId=fixture;state.url=String(tab.url||"");state.lastUpdate=Date.now();}else{state.capture.activeTabId=tab.id;state.capture.armed=true;state.capture.manualConsent=true;state.capture.sessionId=state.capture.sessionId||`${fixture}:${tab.id}:${Date.now().toString(36)}`;state.fixtureId=fixture;state.url=String(tab.url||state.url||"");}await awaitPersist();
// 9.2.4: harvest BEFORE content arm (so RESET cannot wipe it afterward if raced)
let harvest=await forceDomHarvest(tab.id);
const arm=await chrome.tabs.sendMessage(tab.id,{type:"ARM_CAPTURE"}).catch(e=>({ok:false,error:e?.message||String(e)}));
const rr=await chrome.tabs.sendMessage(tab.id,{type:"FORCE_CAPTURE"}).catch(e=>({ok:false,error:e?.message||String(e)}));
// harvest AFTER arm again (post-RESET)
harvest=await forceDomHarvest(tab.id);
// schedule reinforcement 1.2s later
const reinforceTab=tab.id;
setTimeout(()=>{ try{ void forceDomHarvest(reinforceTab); }catch{} },1200);
const ok=!!(harvest?.ok || arm?.ok || rr?.ok);
sendResponse({ok,activeTabId:tab.id,fixtureId:fixture||state.fixtureId,capture:rr||{},arm:arm||null,harvest:harvest||null,acceptedSnapshots:Number(state.capture?.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0),liveStatus:state.liveStatus,home:state.home,away:state.away,score:state.score,minute:state.minute});}catch(e){sendResponse({ok:false,error:e.message});}break;}
 case"STOP_CAPTURE_SESSION":{
  if(sender?.tab?.id!=null && state.capture?.activeTabId!=null && sender.tab.id!==state.capture.activeTabId){sendResponse({ok:false,error:"TAB | sessão não é proprietária desta aba"});break;}
  state.capture.armed=false;state.capture.manualConsent=false;state.capture.activeTabId=null;state.capture.sessionId=null;
  await awaitPersist({immediate:true});
  sendResponse({ok:true,stopped:true});break;
 }
 case"SET_ACTIVE_TAB":{const tabId=Number(msg.tabId);if(!Number.isInteger(tabId)||tabId<0){sendResponse({ok:false,error:"tabId inválido"});break;}if(state.capture.activeTabId!==tabId){state.capture.activeTabId=tabId;state.diagnostics.foreignTabPayloads=0;state.diagnostics.staleMessages=0;}sendResponse({ok:true,activeTabId:tabId});break;}
 case"GET_LAST_TOOL_TEST":sendResponse({ok:true,report:state.diagnostics?.lastToolTest||null});break;
 case"GET_DIAGNOSTICS":state.diagnostics.lastDiagnosticAt=Date.now();state.diagnostics.diagnosticRuns++;sendResponse({ok:true,version:VERSION,parameters:PARAMS,state:clone(state),senderTabId:sender?.tab?.id??null,selfTest:runSelfTest(),sessionHealth:buildSessionHealth(),captureHealth:buildCaptureHealth(),eventIntegrity:buildEventIntegrity(),captureContract:{manualOnly:true,armed:!!state.capture?.armed,manualConsent:!!state.capture?.manualConsent,activeTabId:state.capture?.activeTabId??null,sessionId:state.capture?.sessionId??null}});break;
 case"CHARTS_UNIFIED_GET":{
  try{
    const charts=state.charts||null;
    sendResponse({
      ok:true,
      pack:charts,
      charts:charts,
      seriesCount:charts?.seriesCount??null,
      fixtureId:state.fixtureId||null,
      lastUpdate:state.lastUpdate||null
    });
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;
 }
 case"CHARTS_UNIFIED":{
  if(!acceptFixtureMessage(msg.payload,"charts",sender,msg.meta)){sendResponse({ok:false,rejected:true,error:"CAPTURA | sessão não armada ou contexto inválido"});break;}
  try{
    const pack=msg.payload||null;
    if(pack&&typeof pack==="object"){
      state.chartsUnified=pack;
      state.diagnostics=state.diagnostics||{};
      state.diagnostics.lastChartsUnifiedAt=Date.now();
      state.diagnostics.chartsUnifiedReadyCount=Number(pack.readyCount||0);
      // Ensure charts object exists and carries signals for diagnostics
      state.charts=state.charts||{schema:"cornerai-charts-1",pressureBars:{},series:[],tabs:[]};
      if(pack.signals&&typeof pack.signals==="object"){
        state.charts.signals=pack.signals;
      }
      if(Array.isArray(pack.networkUrls)) state.charts.networkUrls=pack.networkUrls.slice(0,8);
      if(Number.isFinite(Number(pack.seriesCount))) state.charts.seriesCount=Number(pack.seriesCount);
      // Merge pressure into charts for downstream skill feed
      if(pack.pbar&&(pack.pbar.homePercent!=null||pack.pbar.awayPercent!=null)){
        const clock=Number(state.minute)||0;
        const key=Math.max(0,clock-5)+"-"+clock;
        if(!state.charts.pressureBars) state.charts.pressureBars={};
        state.charts.pressureBars[key]={
          home:pack.pbar.homePercent,
          away:pack.pbar.awayPercent,
          src:"charts-unified-pbar"
        };
      }
      if(pack.appm&&pack.appm.intervals){
        state.charts.pressureBars={...(state.charts.pressureBars||{}),...pack.appm.intervals};
      }
      // Surface active chart label when available
      if(pack.macdXg&&pack.macdXg.active){ state.charts.activeId="macd_xg"; state.charts.activeLabel="MACD XG"; }
      await awaitPersist();
    }
    sendResponse({ok:true,readyCount:pack?.readyCount??0,hydration:pack?.hydration||null});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;
 }
 case"DIAG_LOG":{
  try{
    const e=msg.payload||{};
    const entry={
      id:e.id||`${Date.now().toString(36)}-${Math.random().toString(36).slice(2,7)}`,
      at:e.at||new Date().toISOString(),epoch:Number(e.epoch)||Date.now(),
      level:String(e.level||"INFO").toUpperCase(),
      layer:String(e.layer||"content"),
      code:String(e.code||"LOG"),
      message:String(e.message||"").slice(0,500),
      fixtureId:e.fixtureId||state.fixtureId||null,
      correlationId:e.correlationId||null,
      url:e.url||null,
      version:VERSION,
      extra:e.extra
    };
    state.diagTimeline=Array.isArray(state.diagTimeline)?state.diagTimeline:[];
    state.diagTimeline.push(entry);
    if(state.diagTimeline.length>DIAG_RING_MAX) state.diagTimeline=state.diagTimeline.slice(-DIAG_RING_MAX);
    state.diagnostics=state.diagnostics||{};
    state.diagnostics.lastDiagAt=Date.now();
    state.diagnostics.diagCount=(state.diagnostics.diagCount||0)+1;
    if(entry.level==="CRITICAL"||entry.level==="ERROR"){
      state.diagnostics.lastCritical=entry;
      try{addError(`${entry.code}: ${entry.message}`);}catch{}
    }
    await awaitPersist();
    sendResponse({ok:true,size:state.diagTimeline.length});
  }catch(err){sendResponse({ok:false,error:err?.message||String(err)});}
  break;
 }
case"DIAG_HEALTH_SAMPLE":{
  try{
    const s=msg.payload||{};
    state.healthSamples=Array.isArray(state.healthSamples)?state.healthSamples:[];
    state.healthSamples.push({at:Date.now(),...s});
    if(state.healthSamples.length>60) state.healthSamples=state.healthSamples.slice(-60);
    if(Number(s.heapRatio)>0.75) logSW("WARNING","MEM_HEAP_HIGH","Heap >75%",s);
    if(s.storageLocalBytes!=null){
      // Esta extensão possui `unlimitedStorage`; 10 MB é apenas a cota padrão,
      // portanto não deve ser tratado como limite operacional.
      const softLimit=50*1024*1024;
      const hardLimit=100*1024*1024;
      const bytes=Number(s.storageLocalBytes);
      const enriched={...s,storageSoftLimitBytes:softLimit,storageHardLimitBytes:hardLimit,
        storageRatio:+(bytes/softLimit).toFixed(4)};
      if(bytes>=hardLimit){
        logSW("CRITICAL","STORAGE_NEAR_QUOTA","chrome.storage.local acima de 100 MB",enriched);
        try{ void emergencyStoragePrune(); }catch{}
      }else if(bytes>=softLimit){
        logSW("WARNING","STORAGE_HIGH","chrome.storage.local acima de 50 MB",enriched);
      }else if(state.diagnostics?.lastCritical?.code==="STORAGE_NEAR_QUOTA"){
        state.diagnostics.lastCritical=null;
      }
    }
    sendResponse({ok:true});
  }catch(err){sendResponse({ok:false,error:err?.message||String(err)});}
  break;
 }
case"PING":
 case"PING_BACKGROUND":
  sendResponse({
    ok:true,
    version:VERSION,
    serviceWorker:true,
    stateLoaded:!!stateLoaded,
    fixtureId:state.fixtureId,
    liveStatus:state.liveStatus,
    acceptedSnapshots:Number(state.capture?.acceptedSnapshots||0),
    snapshotCount:Number(state.snapshotCount||0),
    activeTabId:state.capture?.activeTabId??null,
    ts:Date.now()
  });
  break;
 case"ACTIVATION_DIAG_REPORT":{
  try{
    const report=msg.payload||msg.report||null;
    if(report&&typeof report==="object"){
      state.diagnostics=state.diagnostics||{};
      state.diagnostics.lastActivationDiag=report;
      state.diagnostics.lastActivationDiagAt=Date.now();
      state.diagnostics.activationDiagCount=(state.diagnostics.activationDiagCount||0)+1;
      if(report.severity==="critical"||report.severity==="high"){
        state.diagnostics.activationDiagIssues=(state.diagnostics.activationDiagIssues||0)+1;
        try{addError("activation-diag: "+(report.summary||report.severity));}catch{}
      }
      await awaitPersist();
    }
    sendResponse({ok:true,stored:!!report});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;
 }
 case"SCAN_PAGE_FIXTURES":{
  try{
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});
    const tab=tabs.find(t=>isSokkerUrl(t.url))||tabs[0];
    if(!tab?.id||!(await isSokkerUrl(tab.url))){sendResponse({ok:false,error:"Abra uma página do SokkerPRO (livescores/resultados/partida)."});break;}
    const ready=await ensureContentScript(tab.id,tab.url);
    if(!ready){sendResponse({ok:false,error:"Content script indisponível — recarregue a aba."});break;}
    const r=await chrome.tabs.sendMessage(tab.id,{type:"SCAN_FIXTURE_LINKS"});
    if(r?.ok && Array.isArray(r.fixtures)) upsertLiveFeed(r.fixtures, "page-scan");
    sendResponse({ok:!!r?.ok,count:r?.count||0,fixtures:r?.fixtures||[],url:r?.url||tab.url,title:r?.title||"",error:r?.error});
  }catch(e){sendResponse({ok:false,error:e.message,fixtures:[]});}
  break;}
 case"START_BATCH_HISTORICAL":{
  try{
    const items=normalizeBatchItems(msg.items||msg.fixtures||msg.lines||[]);
    if(!items.length){sendResponse({ok:false,error:"Nenhuma fixture informada. Cole URLs ou IDs (um por linha)."});break;}
    if(__batchJob.running){sendResponse({ok:false,error:"Já existe uma coleta em andamento. Pare antes de iniciar outra."});break;}
    __batchJob={running:true,stopRequested:false,startedAt:Date.now(),finishedAt:0,total:items.length,index:0,ok:0,fail:0,current:null,items:items.map(it=>({...it,status:"queued",detail:""})),lastError:null};
    sendResponse({ok:true,total:items.length,job:publicBatchStatus()});
    runBatchHistoricalJob().catch(e=>{__batchJob.running=false;__batchJob.lastError=e?.message||String(e);});
  }catch(e){sendResponse({ok:false,error:e.message});}
  break;}
 case"STOP_BATCH_HISTORICAL":{
  __batchJob.stopRequested=true;
  sendResponse({ok:true,job:publicBatchStatus()});
  break;}
 case"GET_BATCH_STATUS":{
  sendResponse({ok:true,job:publicBatchStatus()});
  break;}
 case"FIXTURE_CHANGED":{
  try{
    const fid=String(msg.fixtureId||"").replace(/\D/g,"");
    const prev=String(msg.previousFixtureId||"");
    const tabId=sender?.tab?.id;
    // Wipe total do estado do background — nenhum dado do jogo anterior sobrevive
    state=defaultState();
    if(fid) state.fixtureId=fid;
    if(tabId!=null) state.capture.activeTabId=tabId;
    state.url=String(msg.url||sender?.tab?.url||"");
    state.lastUpdate=Date.now();
    state.diagnostics.lastFixtureChangeAt=Date.now();
    state.diagnostics.lastFixtureChangeFrom=prev||null;
    state.diagnostics.lastFixtureChangeTo=fid||null;
    state.stateVersion=(state.stateVersion||0)+1;
    await awaitPersist();
    try{ await broadcast(); }catch{}
    sendResponse({ok:true,fixtureId:fid,wiped:true,from:prev});
  }catch(e){sendResponse({ok:false,error:e?.message||String(e)});}
  break;}
 case"AUTO_CAPTURE_READY":{sendResponse({ok:false,ignored:true,error:"MANUAL_CAPTURE_REQUIRED"});break;}
 case"GET_DAILY_SAVE":{
  sendResponse({ok:true, enabled: !!__dailySave.enabled, savedToday: [...(__dailySave.saved||[])], day: __dailySave.day, last: __dailySave.last||null});
  break;}
 case"SET_DAILY_SAVE":{
  __dailySave.enabled = msg.enabled!=null?!!msg.enabled:__dailySave.enabled;
  try{await chrome.storage.local.set({cornerai_daily_save:{enabled:__dailySave.enabled}})}catch{}
  sendResponse({ok:true,enabled:__dailySave.enabled});
  break;}
 case"FORCE_DAILY_SAVE":{
  const r=await forceDailySaveNow(msg.reason||"manual");
  sendResponse(r);
  break;}
 case"REARM_SESSION":{
  const fixture=String(msg.fixtureId||msg.meta?.fixtureId||state.fixtureId||"");
  state.capture=state.capture||{};
  state.capture.armed=true;
  state.capture.manualConsent=true;
  if(sender?.tab?.id) state.capture.activeTabId=Number(sender.tab.id);
  if(fixture) state.fixtureId=fixture;
  if(msg.meta?.url||msg.url) state.url=String(msg.meta?.url||msg.url);
  state.lastUpdate=Date.now();
  sendResponse({ok:true,fixtureId:state.fixtureId,acceptedSnapshots:Number(state.capture.acceptedSnapshots||0),snapshotCount:Number(state.snapshotCount||0)});
  break;
}
case"FORCE_DOM_HARVEST":{
  const tid=Number(msg.tabId)||Number(state.capture?.activeTabId)||null;
  let tabId=tid;
  if(!tabId){
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});
    const t=tabs.find(x=>isSokkerUrl(x.url));
    tabId=t?.id||null;
  }
  if(!tabId){sendResponse({ok:false,error:"no_tab"});break;}
  const r=await forceDomHarvest(tabId);
  sendResponse(r);
  break;
}
default:sendResponse({ok:false,error:"unknown_message"})}}catch(e){addError("message: "+e.message);sendResponse({ok:false,error:e.message})}})();return true});

// ─── Batch historical collector ─────────────────────────────────────────────
let __batchJob={running:false,stopRequested:false,startedAt:0,finishedAt:0,total:0,index:0,ok:0,fail:0,current:null,items:[],lastError:null};
function publicBatchStatus(){
  return {
    running:!!__batchJob.running,stopRequested:!!__batchJob.stopRequested,
    startedAt:__batchJob.startedAt||0,finishedAt:__batchJob.finishedAt||0,
    total:__batchJob.total||0,index:__batchJob.index||0,ok:__batchJob.ok||0,fail:__batchJob.fail||0,
    current:__batchJob.current||null,lastError:__batchJob.lastError||null,
    items:(__batchJob.items||[]).map(it=>({fixtureId:it.fixtureId,url:it.url,label:it.label||"",status:it.status,detail:it.detail||""}))
  };
}
function normalizeBatchItems(raw){
  const out=[], seen=new Set();
  const push=(fid,url,label)=>{
    const id=String(fid||"").replace(/\D/g,"");
    if(!/^\d{5,}$/.test(id)||seen.has(id)) return;
    seen.add(id);
    let u=String(url||"").trim();
    if(!u||!/^https?:\/\//i.test(u)) u=`https://sokkerpro.com/fixture/${id}`;
    out.push({fixtureId:id,url:u,label:String(label||"").slice(0,120)});
  };
  const list=Array.isArray(raw)?raw:String(raw||"").split(/\r?\n/);
  for(const item of list){
    if(item && typeof item==="object"){ push(item.fixtureId||item.id, item.url, item.label||item.name||""); continue; }
    const line=String(item||"").trim();
    if(!line||line.startsWith("#")) continue;
    const fromUrl=(line.match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i)||[])[1]
      ||(line.match(/[?&#](?:fixture|matchId|match_id|gameId)=(\d{5,})/i)||[])[1]
      ||(line.match(/\b(\d{6,})\b/)||[])[1];
    if(fromUrl) push(fromUrl, /^https?:\/\//i.test(line)?line:null, "");
  }
  return out;
}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
async function waitTabComplete(tabId,timeoutMs=25000){
  const start=Date.now();
  while(Date.now()-start<timeoutMs){
    try{ const t=await chrome.tabs.get(tabId); if(t.status==="complete") return true; }catch{return false;}
    await sleep(400);
  }
  return false;
}
async function waitBatchCaptureReady(fixtureId,timeoutMs=28000){
  const start=Date.now();
  while(Date.now()-start<timeoutMs){
    if(__batchJob.stopRequested) return {ok:false,reason:"stopped"};
    const fid=String(state.fixtureId||"");
    const hasData=Number(state.snapshotCount||0)>0||(state.cornerEvents||[]).length>0||(state.matchEvents||[]).length>0||!!state.score;
    if(fid===String(fixtureId) && state.home && state.away && (state.liveStatus==="finished"||state.liveStatus==="live"||state.dataMode==="historical") && hasData)
      return {ok:true};
    if(fid===String(fixtureId) && state.home && state.away && Date.now()-start>8000)
      return {ok:true,partial:true};
    await sleep(700);
  }
  return {ok:false,reason:"timeout",fixtureId:state.fixtureId,home:state.home,away:state.away};
}
async function exportSkillPackToBridge(filenameHint,opts={}){
  const force=!!opts.force;
  const gate=exportQualityGate({force});
  if(gate.blocked && !force) return {ok:false,error:"quality_gate: "+(gate.errors||[]).join("; "),gate,errors:gate.errors};
  const pack=buildSkillPackForChat();
  const bodyPack=pack.json||pack.pack||pack;
  if(!bodyPack || typeof bodyPack!=="object") return {ok:false,error:"skill_pack_vazio"};
  if(filenameHint && bodyPack && typeof bodyPack==="object") bodyPack._batchFile=filenameHint;
  bodyPack._batch=true;
  bodyPack._daily=!!opts.daily;
  const url=(state.webhook?.url||"http://127.0.0.1:8080/api/cornerai/feed").replace(/\/api\/cornerai\/feed\/?$/,"/api/cornerai/skill-feed").replace(/\/feed\/?$/,"/skill-feed");
  const skillUrl=url.includes("skill-feed")?url:"http://127.0.0.1:8080/api/cornerai/skill-feed";
  let res, body={}, fetchErr=null;
  try{
    res=await fetch(skillUrl,{
      method:"POST",
      headers:{"Content-Type":"application/json","X-CornerAI-Schema":"cornerai-skill-manual-2","X-CornerAI-Batch":"1"},
      body:JSON.stringify({
        json:bodyPack, pack:bodyPack, pasteText:pack.pasteText,
        filename:filenameHint||pack.filename||null,
        daily:!!opts.daily,
        dailyFixtureId:String(state.fixtureId||bodyPack?.match?.fixtureId||""),
        singleDailyFile:!!opts.daily
      })
    });
    body=await res.json().catch(()=>({}));
  }catch(e){
    fetchErr=e?.message||String(e);
  }
  if(fetchErr) return {ok:false,error:"bridge_fetch: "+fetchErr+" · confira se python bridge/server.py está rodando em :8080",pack};
  if(!res || !res.ok) return {ok:false,error:"bridge_http_"+(res?.status||"?")+": "+(body?.error||res?.statusText||"falha"),body,pack};
  if(body.ok===false) return {ok:false,error:"bridge: "+(body.error||"rejeitado"),body,pack};
  return {ok:true, body, pack};
}
async function runBatchHistoricalJob(){
  const job=__batchJob;
  for(let i=0;i<job.items.length;i++){
    if(job.stopRequested){
      job.items[i].status="skipped"; job.items[i].detail="parado pelo usuário";
      for(let j=i+1;j<job.items.length;j++){job.items[j].status="skipped";job.items[j].detail="parado";}
      break;
    }
    const item=job.items[i];
    job.index=i+1; job.current=item.fixtureId;
    item.status="running"; item.detail="abrindo página…";
    let tabId=null;
    try{
      const tab=await chrome.tabs.create({url:item.url,active:false});
      tabId=tab.id;
      await waitTabComplete(tabId,30000);
      await sleep(1200);
      const readyCs=await ensureContentScript(tabId,item.url);
      if(!readyCs) throw new Error("content script indisponível");
      state=defaultState();
      state.capture.activeTabId=tabId;
      state.fixtureId=item.fixtureId;
      state.url=item.url;
      state.lastUpdate=Date.now();
      await awaitPersist();
      let arm=null;
      for(let attempt=0;attempt<4;attempt++){
        try{arm=await chrome.tabs.sendMessage(tabId,{type:"ARM_CAPTURE"});}catch{}
        if(arm?.ok) break;
        await sleep(900);
      }
      if(!arm?.ok) throw new Error(arm?.error||"falha ao armar captura");
      try{await chrome.tabs.sendMessage(tabId,{type:"FORCE_CAPTURE"});}catch{}
      item.detail="capturando dados…";
      await sleep(1500);
      try{await chrome.tabs.sendMessage(tabId,{type:"FORCE_CAPTURE"});}catch{}
      const wait=await waitBatchCaptureReady(item.fixtureId,30000);
      if(!wait.ok && wait.reason==="stopped"){item.status="skipped";item.detail="parado";break;}
      if(!wait.ok) throw new Error(`timeout sem dados úteis (fid=${wait.fixtureId||"?"} home=${wait.home||"?"})`);
      item.detail="exportando skill pack…";
      const fname=`skill_batch_${item.fixtureId}.json`;
      const exp=await exportSkillPackToBridge(fname,{force:true,daily:true});
      if(!exp.ok) throw new Error(exp.error||exp.body?.error||"falha ao gravar no bridge");
      try{await archiveFinishedMatchIfNeeded();}catch{}
      item.status="ok";
      item.detail=`${state.home||"?"} ${state.score?.home??"?"}×${state.score?.away??"?"} ${state.away||"?"} · ${state.liveStatus||"?"}`;
      job.ok++;
    }catch(e){
      item.status="fail"; item.detail=e?.message||String(e);
      job.fail++; job.lastError=item.detail;
    }finally{
      if(tabId!=null){ try{await chrome.tabs.remove(tabId);}catch{} }
      await sleep(600);
    }
  }
  job.running=false; job.finishedAt=Date.now(); job.current=null;
}

// ─── Auto-salvar jogos do dia (1 arquivo · upsert · validação · alerta · limpa memória) ───
let __dailySave={enabled:true,day:"",saved:new Set(),last:null,timers:Object.create(null),fingerprints:Object.create(null)};
(async()=>{try{const r=await chrome.storage.local.get(["cornerai_daily_save"]);if(r.cornerai_daily_save&&r.cornerai_daily_save.enabled!=null)__dailySave.enabled=!!r.cornerai_daily_save.enabled;}catch{}})();
function dailyKey(){const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
function ensureDailyDay(){
  const k=dailyKey();
  if(__dailySave.day!==k){__dailySave.day=k;__dailySave.saved=new Set();__dailySave.fingerprints=Object.create(null);}
}
function scheduleDailyAutoSave(fixtureId,reason){
  if(!__dailySave.enabled) return;
  const fid=String(fixtureId||state.fixtureId||"");
  if(!fid) return;
  ensureDailyDay();
  if(__dailySave.timers[fid]) clearTimeout(__dailySave.timers[fid]);
  // espera estabilizar (dados + cantos + stats)
  __dailySave.timers[fid]=setTimeout(()=>{forceDailySaveNow(reason||"auto").catch(()=>{});},5500);
}
function buildDailyFingerprint(pack){
  const m=pack?.match||{};
  const c=pack?.corners||{};
  const s=pack?.stats||{};
  return JSON.stringify({
    fid:m.fixtureId, status:m.status, minute:m.minute,
    score:m.score, corners:s.corners, events:c.events_count||c.recent?.length,
    attacks:s.attacks, dangerous:s.dangerous, xg:s.xg, possession:s.possession,
    q:pack?.context?.quality, integrity:pack?.context?.integrity
  });
}
function isCaptureReadyForSave(){
  // Precisão mínima antes de gravar
  if(!state.fixtureId || !state.home || !state.away) return {ok:false,reason:"sem times/fixture"};
  if(!(state.liveStatus==="live"||state.liveStatus==="finished"||state.dataMode==="historical"))
    return {ok:false,reason:"status instável: "+state.liveStatus};
  if(state.score==null || (state.score.home==null && state.score.away==null))
    return {ok:false,reason:"placar ausente"};
  const snaps=Number(state.snapshotCount||state.capture?.acceptedSnapshots||0);
  const corners=(state.cornerEvents||[]).length;
  const hasCore=state.stats?.corners||state.stats?.dangerous||state.stats?.xg;
  if(snaps<1 && corners<1 && !hasCore) return {ok:false,reason:"ainda sem stats/cantos/snapshots"};
  // integrity se existir
  if(state.integrity && state.integrity.pass===false)
    return {ok:false,reason:"integridade FAIL"};
  return {ok:true};
}
async function notifyCapture(title,message){
  try{
    if(!chrome.notifications?.create) return;
    const opts={type:"basic",title:title||"CornerAI",message:String(message||"").slice(0,180),priority:1};
    try{opts.iconUrl=chrome.runtime.getURL("popup.html")}catch{}
    await chrome.notifications.create("cornerai-daily-"+Date.now(),opts);
  }catch{
    // notifications permission may be missing — ignore
  }
}
async function forceDailySaveNow(reason){
  ensureDailyDay();
  if(!__dailySave.enabled && reason!=="manual" && reason!=="force") return {ok:false,error:"daily_save_disabled"};
  const fid=String(state.fixtureId||"");
  if(!fid) return {ok:false,error:"sem fixture"};

  const gate=exportQualityGate({force:reason==="force"});
  if(gate.blocked){
    if(reason!=="manual" && reason!=="force") scheduleDailyAutoSave(fid, "retry");
    return {ok:false,error:"quality_gate: "+(gate.errors||[]).join("; "),gate,retry:true};
  }

  const packWrap=buildSkillPackForChat();
  const pack=packWrap.json||packWrap.pack||packWrap;
  const validation=packWrap.validation||(typeof validateSkillPack==="function"?validateSkillPack(pack):{ok:true,errors:[]});
  if(validation && validation.ok===false){
    try{await notifyCapture("CornerAI · captura rejeitada", (validation.errors||[]).slice(0,2).join(" · "));}catch{}
    return {ok:false,error:"validação falhou",errors:validation.errors};
  }
  // skillReady false em finished histórico ainda pode ser true se home/away ok
  if(pack.skillReady===false && reason!=="force"){
    return {ok:false,error:"skillReady=false — dados não estáveis"};
  }

  const fp=buildDailyFingerprint(pack);
  const prevFp=__dailySave.fingerprints[fid];
  if(prevFp && prevFp===fp && reason!=="force" && reason!=="manual"){
    return {ok:true,skipped:true,reason:"igual_ao_salvo",fixtureId:fid};
  }

  try{
    const day=__dailySave.day;
    const url=(state.webhook?.url||"http://127.0.0.1:8080/api/cornerai/feed").replace(/\/api\/cornerai\/feed\/?$/,"/api/cornerai/skill-feed").replace(/\/feed\/?$/,"/skill-feed");
    const skillUrl=url.includes("skill-feed")?url:"http://127.0.0.1:8080/api/cornerai/skill-feed";
    const res=await fetch(skillUrl,{
      method:"POST",
      headers:{"Content-Type":"application/json","X-CornerAI-Schema":"cornerai-skill-manual-2","X-CornerAI-Daily":day},
      body:JSON.stringify({
        json:pack, pack, pasteText:packWrap.pasteText,
        daily:true,
        dailyDay:day,
        dailyFixtureId:fid,
        dailyFingerprint:fp,
        dailyUpsert:true,
        singleDailyFile:true
      })
    });
    const body=await res.json().catch(()=>({}));
    if(!res.ok || body.ok===false) return {ok:false,error:body.error||("HTTP "+res.status)};

    const action=body.dailyAction||(prevFp?"updated":"added");
    __dailySave.saved.add(fid);
    __dailySave.fingerprints[fid]=fp;
    __dailySave.last={fixtureId:fid,home:state.home,away:state.away,score:state.score,at:Date.now(),day,files:body.files||null,reason,action,fp};

    try{await notifyCapture(
      action==="updated"?"CornerAI · jogo atualizado":"CornerAI · captura concluída",
      `${state.home} ${state.score?.home??"?"}×${state.score?.away??"?"} ${state.away} · salvo no arquivo do dia`
    );}catch{}

    // Limpa memória da extensão após partida FINALIZADA salva com sucesso
    // (mantém só o essencial; próximo jogo começa limpo via defaultState no AUTO_CAPTURE)
    if(state.liveStatus==="finished"||state.dataMode==="historical"){
      try{await archiveFinishedMatchIfNeeded();}catch{}
      try{
        // compacta estado: remove históricos pesados já persistidos
        state.statTimeline=(state.statTimeline||[]).slice(-30);
        state.oddsHistory=(state.oddsHistory||[]).slice(-20);
        state.oddsChanges=(state.oddsChanges||[]).slice(-20);
        state.unifiedTimeline=(state.unifiedTimeline||[]).slice(-40);
        state.menuCapture={...(state.menuCapture||{}), menus:{}, discovered:(state.menuCapture?.discovered||[]).slice(0,20)};
        state.matchEvents=(state.matchEvents||[]).slice(-60);
        await awaitPersist();
      }catch{}
    }

    return {ok:true,fixtureId:fid,day,action,files:body.files||null,last:__dailySave.last};
  }catch(e){
    return {ok:false,error:e?.message||String(e)};
  }
}


function runSelfTest(){
  const results=[];
  const pass=(id,ok,detail="")=>{results.push({id,ok:!!ok,detail:String(detail||"")});return!!ok;};
  const backup=state;
  try{
    state={...defaultState(),fixtureId:"TEST",home:"Casa",away:"Fora",liveStatus:"live",minute:21,extraMinute:0,score:{home:1,away:1},lastUpdate:Date.now()};
    // 1) merge eventos legítimos
    const samples=[
      {type:"corner",minute:12,side:"home"},
      {type:"goal",minute:8,side:"home",label:"Gol"},
      {type:"yellow",minute:15,side:"away"},
      {type:"corner",minute:18,side:"away"}
    ];
    const added=mergeEvents(samples,"selftest");
    pass("events-merge", added===4, `added=${added}`);
    pass("corners-count", state.cornerEvents.length===2, `corners=${state.cornerEvents.length}`);
    // 2) rejeita evento futuro
    const before=state.matchEvents.length;
    mergeEvents([{type:"corner",minute:37,side:"home"}],"selftest");
    const futureBlocked=!(state.matchEvents||[]).some(e=>e.minute===37&&e.type==="corner");
    pass("reject-future-events", futureBlocked, futureBlocked?"blocked 37'":"LEAK 37'");
    // 3) odds cantos sane vs absurdas
    recordOdds([
      {market:"Escanteios - Total",marketType:"corners",selection:"Mais de 8.5",line:"8.5",bookmaker:"Test",odds:1.80,minute:21,period:1},
      {market:"Escanteios - Total",marketType:"corners",selection:"Menos de 8.5",line:"8.5",bookmaker:"Test",odds:2.00,minute:21,period:1},
      {market:"Escanteios - Total",marketType:"corners",selection:"Menos de 9.5",line:"9.5",bookmaker:"Test",odds:87,minute:21,period:1},
      {market:"Escanteios - Total",marketType:"corners",selection:"Mais de 9.5",line:"9.5",bookmaker:"Test",odds:9.50,minute:21,period:1}
    ],"selftest",{minute:21,extraMinute:0});
    const cornerOdds=(state.oddsHistory||[]).filter(r=>r.marketType==="corners");
    pass("odds-corner-sane", cornerOdds.length===2 && cornerOdds.every(r=>r.odds>=1.15&&r.odds<=6.5), `n=${cornerOdds.length}`);
    // 4) 1X2 overround coerente
    recordOdds([
      {market:"Resultado Final",selection:"1 (Casa)",odds:5.50,minute:21,period:1,bookmaker:"SokkerPRO"},
      {market:"Resultado Final",selection:"X (Empate)",odds:1.90,minute:21,period:1,bookmaker:"SokkerPRO"},
      {market:"Resultado Final",selection:"2 (Fora)",odds:2.62,minute:21,period:1,bookmaker:"SokkerPRO"}
    ],"selftest",{minute:21,extraMinute:0});
    rebuildOddsAnalytics();
    const ox=(state.oddsHistory||[]).filter(r=>/resultado final/i.test(r.market||"")&&!/justa/i.test(r.market||""));
    const ov=ox.find(r=>r.marketOverround!=null)?.marketOverround;
    pass("odds-overround", ov!=null&&ov>=0.95&&ov<=1.35, `overround=${ov}`);
    // 5) stats vs eventos
    state.stats={corners:{home:1,away:1},dangerous:{home:10,away:12},possession:{home:40,away:60},xg:{home:0.3,away:0.5},shotsOn:{home:1,away:1},shotsOff:{home:2,away:3},attacks:{home:20,away:25},red:{home:0,away:0},yellow:{home:0,away:1}};
    state.charts={pressureBars:{"0-15":{home:58,away:42,pct:58},"15-30":{home:63,away:37,pct:63}}};
    state.intelligence=buildIntelligenceFeatures();
    // 6) integrity suite
    const integ=buildIntegrity();
    pass("integrity-pass", integ.pass===true, `score=${integ.integrityScore} failed=${(integ.failed||[]).join(",")}`);
    pass("integrity-score-high", Number(integ.integrityScore)>=80, `score=${integ.integrityScore}`);
    // 7) analyst schema
    const analyst=buildAnalystFeed();
    pass("analyst-schema", analyst?.schema==="cornerai-analyst-1", analyst?.schema);
    pass("analyst-fixture", !!(analyst.fixture?.id&&analyst.fixture?.home&&analyst.fixture?.away));
    pass("analyst-corners", Array.isArray(analyst.corners?.events));
    // 8) publishable gate
    const gate=analystPublishable(analyst);
    pass("analyst-publishable", gate.ok===true, gate.reason||"ok");
    // 9) gate bloqueia futuro
    state.matchEvents.push({type:"corner",minute:50,side:"home",eventId:"future-test"});
    const integ2=buildIntegrity();
    const analyst2=buildAnalystFeed();
    const gate2=analystPublishable(analyst2);
    pass("gate-blocks-future", gate2.ok===false||(integ2.failed||[]).includes("no-future-events"), `ok=${gate2.ok} failed=${(integ2.failed||[]).join(",")}`);
    // cleanup future
    state.matchEvents=(state.matchEvents||[]).filter(e=>e.eventId!=="future-test");
    // 10) history monitor
    pass("integrity-history", Array.isArray(state.integrityHistory)&&state.integrityHistory.length>=1, `n=${state.integrityHistory?.length||0}`);
    const failed=results.filter(r=>!r.ok);
    return {
      ok:failed.length===0,
      version:VERSION,
      passed:results.filter(r=>r.ok).length,
      total:results.length,
      failed:failed.map(r=>r.id),
      results,
      integrity:integ,
      analystSchema:analyst?.schema
    };
  }catch(e){
    return {ok:false,version:VERSION,error:String(e?.message||e),results};
  }finally{
    state=backup;
  }
}
// Live capture watchdog: recover a lost content timer without touching menus/H2H.
setInterval(async()=>{
  try{
    const tabId=state.capture?.activeTabId;
    if(tabId==null || state.liveStatus!=="live" || !state.capture?.armed) return;
    const age=Date.now()-Number(state.capture?.lastPayloadAt||state.lastUpdate||0);
    if(age<2500) return;
    let tab=null;
    try{tab=await chrome.tabs.get(tabId);}catch{tab=null;}
    if(!tab?.url || !(await isSokkerUrl(tab.url))) return;
    try{await chrome.tabs.sendMessage(tabId,{type:"CAPTURE_HEARTBEAT"});}catch{}
    if(age>5000){
      try{
        const probe=await chrome.tabs.sendMessage(tabId,{type:"GET_FIXTURE_ID"});
        if(probe?.fixtureId && String(probe.fixtureId)===String(state.fixtureId)){
          const r=await chrome.tabs.sendMessage(tabId,{type:"FORCE_CAPTURE"});
          state.diagnostics.watchdogForces=(state.diagnostics.watchdogForces||0)+1;
          if(r?.ok===false) state.diagnostics.captureDispatchFailures=(state.diagnostics.captureDispatchFailures||0)+1;
        }
      }catch{}
    }
    if(age>12000){
      try{
        const probe=await chrome.tabs.sendMessage(tabId,{type:"GET_FIXTURE_ID"});
        if(probe?.fixtureId && String(probe.fixtureId)===String(state.fixtureId)){
          const r=await chrome.tabs.sendMessage(tabId,{type:"ARM_CAPTURE",probeOnly:true});
          if(r?.ok) state.diagnostics.watchdogRearms=(state.diagnostics.watchdogRearms||0)+1;
        }
      }catch{}
    }
  }catch{}
},2000);
setInterval(async()=>{
  try{
    const tabId=state.capture?.activeTabId;
    if(tabId==null || state.liveStatus!=="live" || !state.capture?.armed) return;
    const age=Date.now()-Number(state.capture?.lastPayloadAt||state.lastUpdate||0);
    if(age<2500) return;
    let tab=null;
    try{tab=await chrome.tabs.get(tabId);}catch{tab=null;}
    if(!tab?.url || !(await isSokkerUrl(tab.url))) return;
    try{await chrome.tabs.sendMessage(tabId,{type:"CAPTURE_HEARTBEAT"});}catch{}
  }catch{}
},2000);

setInterval(async()=>{
  try{
    state.captureHealth=buildCaptureHealth();
    if(state.capture.activeTabId!=null){
      try{
        const tab=await chrome.tabs.get(state.capture.activeTabId);
        if(tab?.url && await isSokkerUrl(tab.url)){
          const r=await chrome.tabs.sendMessage(tab.id,{type:"PING_CONTENT"});
          if(r?.ok){state.captureHealth.signals.contentScript={ok:true,label:"OK"};}
          // MAXIMIZE: auto-attempt H2H when never tried or stale (>90s)
          const h2h=state.h2h||{};
          const age=Date.now()-Number(h2h.lastAttemptAt||0);
          if((!h2h.attempted || (!h2h.captured && age>90000)) && age>15000){
            try{
              await chrome.tabs.sendMessage(tab.id,{type:"H2H_POLL"});
              state.h2h={...state.h2h,attempted:true,lastAttemptAt:Date.now()};
              state.diagnostics.h2hAutoPolls=(state.diagnostics.h2hAutoPolls||0)+1;
            }catch{}
          }
          // MAXIMIZE: auto menu sweep for odds / h2h / estatisticas when coverage gaps
          await maybeAutoMenuSweep(tab.id);
        }
      }catch(e){ state.captureHealth.signals.contentScript={ok:false,label:"SEM CONEXÃO"}; }
    }
    broadcast();
  }catch(e){ addError("health watchdog: "+e.message); }
},3000);

// Auto-enrichment: open priority menus with restore, rate-limited.
async function maybeAutoMenuSweep(tabId){
  try{
    const now=Date.now();
    const mc=state.menuCapture||{};
    const last=Number(mc.sweep?.lastAutoAt||0);
    // Rate limit: 35s live / 20s finished (finished needs fewer constraints)
    const finished=state.liveStatus==="finished"||state.dataMode==="historical";
    const minGap=finished?20000:35000;
    if(now-last<minGap) return;
    // Don't overlap with active sweep
    if(mc.sweep?.active) return;
    // Only when we have a fixture
    if(!state.fixtureId) return;
    const live=state.liveStatus==="live";
    // Skip very early pre-match noise
    if(state.liveStatus==="not_started"||state.liveStatus==="scheduled") return;

    const menuIds=new Set(Object.keys(mc.menus||{}).map(k=>String(k).split("|")[0]));
    const discovered=new Set((mc.discovered||[]).map(x=>typeof x==="string"?x:(x?.id||x?.menuId||"")));
    const hasOdds=menuIds.has("odds")||Number(state.oddsCount||0)>0;
    const hasH2H=!!(state.h2h?.captured&&((state.h2h.matches||[]).length>0||state.h2h.summary?.total||(state.h2h.rows||[]).length>0));
    const hasStats=menuIds.has("estatisticas")||menuIds.has("escanteios");
    const hasCards=menuIds.has("cartoes")||menuIds.has("cards");
    const hasLineups=menuIds.has("escalacoes")||menuIds.has("lineups");
    const redMissing=!(state.stats?.red&&(state.stats.red.home!=null||state.stats.red.away!=null));
    const subsMissing=!(state.stats?.subs&&(state.stats.subs.home!=null||state.stats.subs.away!=null));
    const yellowMissing=!(state.stats?.yellow&&(state.stats.yellow.home!=null||state.stats.yellow.away!=null));

    const gaps=[];
    if(!hasOdds) gaps.push("odds");
    if(!hasH2H) gaps.push("h2h");
    if(!hasStats) gaps.push("estatisticas");
    if(!menuIds.has("escanteios")&&!menuIds.has("corners")) gaps.push("escanteios");
    // Prefer card / lineup tabs when optional stats are missing
    if((redMissing||yellowMissing||subsMissing)&&!hasCards&&(discovered.has("cartoes")||discovered.has("cards")||true)) gaps.push("cartoes");
    if(subsMissing&&!hasLineups&&(discovered.has("escalacoes")||true)) gaps.push("escalacoes");
    for(const id of ["xg","eventos","finalizacoes","ataques","posse","jogadores","graficos","pre_odds","dicas","rank"]){
      if(!menuIds.has(id) && discovered.has(id)) gaps.push(id);
    }
    // If everything covered, still light refresh every 3 min while live
    if(!gaps.length){
      if(!live||now-last<180000) return;
    }
    // Prefer gaps first, limit clicks
    const maxOpen=gaps.length?Math.min(gaps.length,8):(live?2:1);
    if(maxOpen<=0) return;

    state.menuCapture.sweep={...(state.menuCapture.sweep||{}),active:true,mode:"auto",lastAutoAt:now,startedAt:now,gaps:gaps.slice(0,8)};
    state.diagnostics.menuAutoSweeps=(state.diagnostics.menuAutoSweeps||0)+1;
    try{
      const prefer=gaps.length?gaps:["odds","h2h","estatisticas","escanteios","cartoes","escalacoes"];
      const result=await new Promise((resolve,reject)=>{
        chrome.tabs.sendMessage(tabId,{
          type:"MENU_SWEEP",
          options:{allowClicks:true,maxOpen,waitMs:finished?550:450,preferIds:prefer}
        },r=>{
          const err=chrome.runtime.lastError;
          if(err)reject(new Error(err.message));
          else resolve(r||{ok:false});
        });
      });
      state.menuCapture.sweep={
        ...(state.menuCapture.sweep||{}),
        active:false,
        lastAutoAt:now,
        lastResult:{opened:Number(result?.opened||0),restored:!!result?.restored,discovered:Number(result?.discovered||0),errors:Array.isArray(result?.errors)?result.errors.slice(0,10):[],mode:"auto",gaps:gaps.slice(0,8),at:now}
      };
      if(result?.ok) state.diagnostics.menuSweeps=(state.diagnostics.menuSweeps||0)+1;
      else state.diagnostics.menuErrors=(state.diagnostics.menuErrors||0)+1;
      // After sweep, force H2H parse if still empty
      if(!hasH2H){
        try{await chrome.tabs.sendMessage(tabId,{type:"H2H_POLL"});}catch{}
      }
      await awaitPersist();
      // Persist team H2H corner cache when sample is useful
      try{await persistTeamContextCache();}catch{}
    }catch(e){
      state.menuCapture.sweep={...(state.menuCapture.sweep||{}),active:false,lastAutoAt:now};
      state.diagnostics.menuErrors=(state.diagnostics.menuErrors||0)+1;
    }
  }catch(e){
    try{addError("auto-menu-sweep: "+(e?.message||e));}catch{}
  }
}

// --- Team context cache (H2H corner averages across fixtures) ---
function teamKey(name){
  return String(name||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"").slice(0,48);
}
async function persistTeamContextCache(){
  try{
    const h=state.h2h||{};
    if(!h.captured) return;
    const home=state.home, away=state.away;
    if(!home||!away) return;
    const avg=h.averages||{};
    const params=h.parameters||{};
    // Prefer structured corner averages; fall back to match-level aggregates
    let cornersHome=null, cornersAway=null, samples=0;
    if(avg.corners&&Number.isFinite(Number(avg.corners.avg))){
      // single aggregate — attribute half/half only if we lack side split
      cornersHome=Number(avg.corners.avg);
      cornersAway=Number(avg.corners.avg);
      samples=Number(avg.corners.samples||params.matches||params.totalResults||0);
    }
    if(avg.cornersHome&&Number.isFinite(Number(avg.cornersHome.avg))){
      cornersHome=Number(avg.cornersHome.avg);
      samples=Math.max(samples,Number(avg.cornersHome.samples||0));
    }
    if(avg.cornersAway&&Number.isFinite(Number(avg.cornersAway.avg))){
      cornersAway=Number(avg.cornersAway.avg);
      samples=Math.max(samples,Number(avg.cornersAway.samples||0));
    }
    // Also mine match rows when available
    const matches=Array.isArray(h.matches)?h.matches:(Array.isArray(h.rows)?h.rows:[]);
    if(matches.length>=3){
      let ch=0,ca=0,n=0;
      for(const m of matches.slice(0,20)){
        const a=Number(m.cornersHome??m.homeCorners??m.corners_home);
        const b=Number(m.cornersAway??m.awayCorners??m.corners_away);
        if(Number.isFinite(a)&&Number.isFinite(b)){ ch+=a; ca+=b; n++; }
      }
      if(n>=3){
        cornersHome=Number((ch/n).toFixed(2));
        cornersAway=Number((ca/n).toFixed(2));
        samples=n;
      }
    }
    // Only cache when sample is meaningful (≥3)
    if(samples<3 && !(cornersHome!=null||cornersAway!=null)) return;
    if(samples<3) return;

    const stored=await chrome.storage.local.get(["cornerai_team_context"]);
    const cache=stored.cornerai_team_context&&typeof stored.cornerai_team_context==="object"?stored.cornerai_team_context:{};
    const hk=teamKey(home), ak=teamKey(away);
    const ts=Date.now();
    const limit=Number(PARAMS.teamContextCacheLimit||80);
    if(hk&&cornersHome!=null){
      const prev=cache[hk]||{};
      const af=prev.attackFactor!=null?prev.attackFactor:Number((cornersHome/5).toFixed(3));
      cache[hk]={...prev,name:home,avgCorners:cornersHome,samples,attackFactor:af,fixtureId:state.fixtureId,updatedAt:ts,vs:away};
    }
    if(ak&&cornersAway!=null){
      const prev=cache[ak]||{};
      const af=prev.attackFactor!=null?prev.attackFactor:Number((cornersAway/5).toFixed(3));
      cache[ak]={...prev,name:away,avgCorners:cornersAway,samples,attackFactor:af,fixtureId:state.fixtureId,updatedAt:ts,vs:home};
    }
    // Pair key for this H2H
    const pair=[hk,ak].filter(Boolean).sort().join("__");
    if(pair){
      cache["h2h:"+pair]={
        home,away,cornersHome,cornersAway,samples,
        cornersVariance:avg.cornersTotal?.variance??avg.corners?.variance??null,
        cornersStd:avg.cornersTotal?.std??avg.corners?.std??null,
        cornersResultCorr:avg.cornersResultCorr??null,
        drawRate:avg.drawRate??null,
        lowCornerDrawBias:!!avg.lowCornerDrawBias,
        goalsHome:avg.goalsHome?.avg??params.avgGoalsHome??null,
        goalsAway:avg.goalsAway?.avg??params.avgGoalsAway??null,
        fixtureId:state.fixtureId,updatedAt:ts
      };
    }
    // Prune oldest if over limit
    const keys=Object.keys(cache);
    if(keys.length>limit){
      keys.sort((a,b)=>(cache[a]?.updatedAt||0)-(cache[b]?.updatedAt||0));
      for(const k of keys.slice(0,keys.length-limit)) delete cache[k];
    }
    await chrome.storage.local.set({cornerai_team_context:cache});
    state.diagnostics.teamContextCacheWrites=(state.diagnostics.teamContextCacheWrites||0)+1;
    state.teamContextCache={home:cache[hk]||null,away:cache[ak]||null,h2h:cache["h2h:"+pair]||null,size:Object.keys(cache).length};
  }catch(e){
    try{addError("team-context-cache: "+(e?.message||e));}catch{}
  }
}
async function loadTeamContextForCurrentMatch(){
  try{
    if(!state.home||!state.away) return null;
    const stored=await chrome.storage.local.get(["cornerai_team_context"]);
    const cache=stored.cornerai_team_context&&typeof stored.cornerai_team_context==="object"?stored.cornerai_team_context:{};
    const hk=teamKey(state.home), ak=teamKey(state.away);
    const pair=[hk,ak].filter(Boolean).sort().join("__");
    const ctx={home:cache[hk]||null,away:cache[ak]||null,h2h:pair?cache["h2h:"+pair]||null:null};
    state.teamContextCache=ctx;
    return ctx;
  }catch{return null;}
}


// ===== Auto-Gemini (v6.8) =====


// ===== Drift CUSUM + Alert explanation (v6.9.1) =====
const __cusum = {
  // one-sided CUSUM on feature means
  series: {
    cornerRate: {pos:0, neg:0, mean:null, n:0},
    opiHome: {pos:0, neg:0, mean:null, n:0},
    opiAway: {pos:0, neg:0, mean:null, n:0},
    cpiMax: {pos:0, neg:0, mean:null, n:0},
    predP: {pos:0, neg:0, mean:null, n:0}
  },
  alerts: [],
  lastAt: 0
};
function cusumUpdate(name, value, k=0.05, h=0.35){
  if(!Number.isFinite(value)) return null;
  const s=__cusum.series[name] || (__cusum.series[name]={pos:0,neg:0,mean:null,n:0});
  // running mean as target
  s.n += 1;
  s.mean = s.mean==null ? value : s.mean + (value - s.mean)/s.n;
  const diff = value - s.mean;
  s.pos = Math.max(0, s.pos + diff - k);
  s.neg = Math.max(0, s.neg - diff - k);
  let hit=null;
  if(s.pos > h){ hit={name, direction:"up", value, mean:s.mean, stat:s.pos}; s.pos=0; }
  if(s.neg > h){ hit={name, direction:"down", value, mean:s.mean, stat:s.neg}; s.neg=0; }
  if(hit){
    hit.at=Date.now();
    hit.minute=state.minute;
    __cusum.alerts.unshift(hit);
    __cusum.alerts=__cusum.alerts.slice(0,30);
    state.diagnostics.cusumHits=(state.diagnostics.cusumHits||0)+1;
  }
  return hit;
}
function runCusumDriftCheck(){
  try{
    const minute=Number(state.minute);
    if(!Number.isFinite(minute) || state.liveStatus!=="live") return null;
    // throttle ~ every ~20s wall or minute change
    const now=Date.now();
    if(now - (__cusum.lastAt||0) < 15000) return state.drift||null;
    __cusum.lastAt=now;

    const totalC=(Number(state.stats?.corners?.home)||0)+(Number(state.stats?.corners?.away)||0);
    const rate=totalC/Math.max(1,minute);
    const opi=(typeof offensivePressureIndex==="function")?offensivePressureIndex():{home:null,away:null};
    const am=state.analyst?.advanced_metrics||{};
    const cpiH=Number(am.CPI_v2?.home?.cpi), cpiA=Number(am.CPI_v2?.away?.cpi);
    const cpiMax=Math.max(Number.isFinite(cpiH)?cpiH:0, Number.isFinite(cpiA)?cpiA:0);
    const predP=Number(am.temporal?.prediction_corner_2m?.probability);

    const hits=[];
    const h1=cusumUpdate("cornerRate", rate, 0.01, 0.08); if(h1) hits.push(h1);
    if(Number.isFinite(opi.home)){ const h=cusumUpdate("opiHome", opi.home, 0.03, 0.25); if(h) hits.push(h); }
    if(Number.isFinite(opi.away)){ const h=cusumUpdate("opiAway", opi.away, 0.03, 0.25); if(h) hits.push(h); }
    if(cpiMax>0){ const h=cusumUpdate("cpiMax", cpiMax, 0.04, 0.30); if(h) hits.push(h); }
    if(Number.isFinite(predP)){ const h=cusumUpdate("predP", predP, 0.04, 0.30); if(h) hits.push(h); }

    const drift={
      schema:"cornerai-drift-1",
      active: hits.length>0,
      hits: hits.slice(0,5),
      recent: __cusum.alerts.slice(0,8),
      series: Object.fromEntries(Object.entries(__cusum.series).map(([k,v])=>[k,{
        mean: v.mean==null?null:Number(v.mean.toFixed(4)),
        pos:Number(v.pos.toFixed(3)),
        neg:Number(v.neg.toFixed(3)),
        n:v.n
      }])),
      updatedAt: now
    };
    state.drift=drift;
    // notify on new hit (throttled by notifyHeadless)
    for(const h of hits){
      try{
        notifyHeadless("drift_"+h.name,
          "Drift detectado",
          `${h.name} ${h.direction} @ ${h.minute||"?"}' (val ${Number(h.value).toFixed(3)} vs μ ${Number(h.mean).toFixed(3)})`);
      }catch{}
    }
    return drift;
  }catch(e){ return null; }
}

function explainCornerAlert(pred, features){
  // Human-readable reasons for why an alert fired / would fire
  const reasons=[];
  const conf=[];
  const against=[];
  const p=Number(pred?.probability||pred?.probability_raw||0);
  const side=pred?.preferredSide||null;
  const thr=(typeof adaptiveAlertThreshold==="function")?adaptiveAlertThreshold():0.55;
  const opi=features?.offensivePressureIndex||((typeof offensivePressureIndex==="function")?offensivePressureIndex():null);
  const ema=features?.cornersEma||((typeof cornersEma10==="function")?cornersEma10():null);
  const eff=features?.cornerEfficiency||((typeof cornerEfficiency==="function")?cornerEfficiency():null);
  const react=features?.goalReaction||null;
  const num=features?.numericalSuperiority||null;
  const kal=features?.kalmanCornerRate||null;
  const am=state.analyst?.advanced_metrics||{};
  const cpiH=Number(am.CPI_v2?.home?.cpi), cpiA=Number(am.CPI_v2?.away?.cpi);

  if(p >= thr) reasons.push({code:"prob_above_thr", text:`Probabilidade ${Math.round(p*100)}% ≥ limiar ${Math.round(thr*100)}%`, weight:1});
  if(side && Number.isFinite(side==="home"?cpiH:cpiA) && (side==="home"?cpiH:cpiA) >= 0.65)
    reasons.push({code:"cpi_side", text:`CPI ${side} elevado (${((side==="home"?cpiH:cpiA)||0).toFixed(2)})`, weight:0.9});
  if(opi){
    const o=Math.max(opi.home||0, opi.away||0);
    if(o>=0.55) reasons.push({code:"opi_high", text:`Pressão ofensiva alta (${o.toFixed(2)})`, weight:0.8});
    else if(o<0.25) against.push({code:"opi_low", text:`Pressão ofensiva baixa (${o.toFixed(2)})`});
  }
  if(ema && Number(ema.ema10)>0.35) reasons.push({code:"ema_corners", text:`EMA de cantos aquecida (${ema.ema10})`, weight:0.7});
  if(ema && Number(ema.last5)>=2) reasons.push({code:"cluster_5m", text:`${ema.last5} cantos nos últimos ~5 min`, weight:0.85});
  if(eff){
    const e=Math.max(eff.home||0, eff.away||0);
    if(e>=0.25) reasons.push({code:"efficiency", text:`Boa conversão perigoso→canto (${e.toFixed(2)})`, weight:0.6});
  }
  if(react && ((react.home||0)>0.05 || (react.away||0)>0.05))
    reasons.push({code:"goal_reaction", text:"Reação pós-gol sofrido ativa", weight:0.55});
  if(num && (Math.abs(num.home)>=1 || Math.abs(num.away)>=1))
    reasons.push({code:"red_card", text:"Superioridade numérica por vermelho", weight:0.7});
  if(kal && Number(kal.uncertainty)>0.12)
    against.push({code:"kalman_unc", text:`Taxa de cantos instável (σ ${kal.uncertainty})`});
  if(pred?.overconfidence?.flag)
    against.push({code:"overconfidence", text:`Overconfidence (${pred.overconfidence.reason})`});
  const iq=Number(state.integrity?.score ?? 100);
  if(iq<85) against.push({code:"integrity", text:`Integridade moderada (${iq})`});

  reasons.sort((a,b)=>(b.weight||0)-(a.weight||0));
  const verdict = p>=thr ? (against.length>=reasons.length ? "alerta_cautela" : "alerta_forte") : "sem_alerta";
  return {
    schema:"cornerai-alert-explain-1",
    verdict,
    probability: p,
    threshold: thr,
    preferredSide: side,
    reasons: reasons.slice(0,5),
    against: against.slice(0,4),
    summary: reasons.length
      ? `Por quê: ` + reasons.slice(0,3).map(r=>r.text).join(" · ")
      : "Sem sinais dominantes de escanteio iminente.",
    at: Date.now(),
    minute: state.minute
  };
}

function buildExplainabilityBundle(){
  const features=(typeof buildAdvancedPredictiveFeatures==="function")?buildAdvancedPredictiveFeatures():null;
  const pred=features?.prediction || state.analyst?.advanced_metrics?.temporal?.prediction_corner_2m || null;
  const explanation=explainCornerAlert(pred, features);
  const drift=state.drift || null;
  return {
    schema:"cornerai-explain-1",
    explanation,
    drift,
    predictive: features ? {
      opi: features.offensivePressureIndex,
      ema: features.cornersEma,
      efficiency: features.cornerEfficiency,
      kalman: features.kalmanCornerRate,
      cpiBand: features.cpiBand
    } : null,
    derivedAt: Date.now()
  };
}


// ===== Predictive features + calibration + adaptive threshold (v6.9) =====
function emaSeries(values, alpha){
  let ema=null; const out=[];
  for(const v of values){
    if(!Number.isFinite(v)){ out.push(ema); continue; }
    ema = ema==null ? v : alpha*v + (1-alpha)*ema;
    out.push(ema);
  }
  return out;
}
function cornersEma10(){
  // Build per-minute cumulative corners then 10-min style EMA on increments
  const events=(state.cornerEvents||[]).slice().sort((a,b)=>eventMinuteValue(a)-eventMinuteValue(b));
  const minute=Number(state.minute)||0;
  const bins={};
  for(const e of events){
    const m=Math.floor(eventMinuteValue(e));
    bins[m]=(bins[m]||0)+1;
  }
  const series=[];
  for(let m=Math.max(0,minute-15); m<=minute; m++) series.push(bins[m]||0);
  const alpha=2/(10+1); // EMA ~10
  const ema=emaSeries(series, alpha);
  const last=ema.length?ema[ema.length-1]:null;
  return {
    ema10: last==null?null:Number(last.toFixed(3)),
    last5: series.slice(-5).reduce((a,b)=>a+b,0),
    ratePerMin: minute>0 ? Number((((Number(state.stats?.corners?.home)||0)+(Number(state.stats?.corners?.away)||0))/minute).toFixed(3)) : null
  };
}
function offensivePressureIndex(){
  // Normalize rough rates into 0..1 composite
  const minute=Math.max(1, Number(state.minute)||1);
  function side(s){
    const at=(Number(state.stats?.attacks?.[s])||0)/minute;
    const dg=(Number(state.stats?.dangerous?.[s])||0)/minute;
    const sh=(Number(state.stats?.shots?.[s])||0)/minute;
    const so=(Number(state.stats?.shotsOn?.[s])||0)/minute;
    // soft caps based on typical match rates
    const nAt=Math.min(1, at/1.2);
    const nDg=Math.min(1, dg/0.7);
    const nSh=Math.min(1, sh/0.5);
    const nSo=Math.min(1, so/0.25);
    const idx=0.25*nAt + 0.35*nDg + 0.20*nSh + 0.20*nSo;
    return Number(Math.max(0,Math.min(1,idx)).toFixed(3));
  }
  return {home:side("home"), away:side("away")};
}
function cornerEfficiency(){
  // corners / dangerous attacks (efficiency)
  function side(s){
    const c=Number(state.stats?.corners?.[s]);
    const d=Number(state.stats?.dangerous?.[s]);
    if(!Number.isFinite(c)||!Number.isFinite(d)||d<=0) return null;
    return Number(Math.min(2, c/d).toFixed(3));
  }
  return {home:side("home"), away:side("away")};
}
function goalReactionFeature(){
  // Pattern change after conceding: pressure index delta post-goal
  const minute=Number(state.minute)||0;
  const goals=(state.matchEvents||[]).filter(e=>normalizeEventType(e.type)==="goal");
  const out={home:0, away:0, recent:[]};
  for(const g of goals){
    const gm=eventMinuteValue(g);
    if(minute-gm<0 || minute-gm>8) continue;
    // conceded side reacts
    const conceded = g.side==="home"?"away":(g.side==="away"?"home":null);
    if(!conceded) continue;
    const age=minute-gm;
    const boost=Math.max(0, 1 - age/8) * 0.15; // up to +15% fading
    out[conceded] += boost;
    out.recent.push({conceded, goalAt:Number(gm.toFixed(2)), boost:Number(boost.toFixed(3))});
  }
  out.home=Number(Math.min(0.25, out.home).toFixed(3));
  out.away=Number(Math.min(0.25, out.away).toFixed(3));
  return out;
}
function numericalSuperiorityFeature(){
  const rH=Number(state.stats?.red?.home)||0;
  const rA=Number(state.stats?.red?.away)||0;
  // +1 if opponent has more reds (we have numerical advantage)
  return {
    home: Number(Math.max(-1, Math.min(1, rA - rH)).toFixed(2)),
    away: Number(Math.max(-1, Math.min(1, rH - rA)).toFixed(2)),
    reds:[rH,rA]
  };
}
function kalmanCornerRate(){
  // 1D Kalman-ish on total corner rate
  const minute=Math.max(1, Number(state.minute)||1);
  const total=(Number(state.stats?.corners?.home)||0)+(Number(state.stats?.corners?.away)||0);
  const z = total/minute; // observation
  state._kalman = state._kalman || {x:z, p:1, q:0.002, r:0.05};
  const k=state._kalman;
  // predict
  k.p = k.p + k.q;
  // update
  const K = k.p / (k.p + k.r);
  k.x = k.x + K*(z - k.x);
  k.p = (1-K)*k.p;
  return {
    rate: Number(k.x.toFixed(4)),
    observed: Number(z.toFixed(4)),
    uncertainty: Number(Math.sqrt(Math.max(0,k.p)).toFixed(4))
  };
}
function cpiConfidenceBand(cpi, uncertainty){
  // Simple symmetric band widened by data quality / kalman uncertainty
  const q=Number(state.quality?.score||50)/100;
  const base=0.06 + (1-q)*0.08 + Number(uncertainty||0.05);
  const lo=Math.max(0, Number(cpi||0)-base);
  const hi=Math.min(1, Number(cpi||0)+base);
  return {lo:Number(lo.toFixed(3)), hi:Number(hi.toFixed(3)), width:Number((hi-lo).toFixed(3))};
}
function detectOverconfidence(prob, band){
  // Flag if probability extreme while band wide or integrity low
  const iq=Number(state.integrity?.score ?? state.analyst?.quality?.integrityScore ?? 100);
  const width=Number(band?.width||0.2);
  const p=Number(prob||0);
  const extreme = p>=0.7 || p<=0.15;
  const weak = width>0.28 || iq<80;
  return {
    flag: !!(extreme && weak),
    reason: extreme && weak ? (iq<80?"integrity":"wide_band") : null,
    suggestedCap: extreme && weak ? Number(Math.min(0.65, Math.max(0.2, p*0.85+0.05)).toFixed(3)) : null
  };
}

// Platt-like scaling from feedback (logistic on raw probability)
function plattScale(rawP){
  const fb=state.feedback?.stats;
  // defaults: mild identity; learn a,b from feedback when n large
  let a=0, b=0; // logit' = a + b*logit(p) with a=0,b=1 identity via transform below
  let slope=1, bias=0;
  if(fb && Number(fb.n||0)>=20 && Number.isFinite(Number(fb.avgPred)) && Number.isFinite(Number(fb.hitRate))){
    // If overconfident (avgPred > hitRate), shrink toward 0.5
    const gap = Number(fb.avgPred) - Number(fb.hitRate);
    slope = Math.max(0.7, Math.min(1.15, 1 - gap)); // compress if overconfident
    bias = Number((Number(fb.hitRate) - 0.5) * 0.15);
  }
  const p=Math.max(1e-3, Math.min(1-1e-3, Number(rawP)||0.5));
  // map through center 0.5
  let y = 0.5 + (p-0.5)*slope + bias;
  y = Math.max(0.02, Math.min(0.85, y));
  return Number(y.toFixed(3));
}

function adaptiveAlertThreshold(){
  // Start from user pref / 0.55; adjust with feedback F1 proxy
  const base=Number(state.alertPrefs?.cornerPredThreshold||0.55);
  const fb=state.feedback?.stats;
  if(!fb || Number(fb.n||0)<15) return Number(base.toFixed(3));
  const hit=Number(fb.hitRate||0);
  const avg=Number(fb.avgPred||0.5);
  // if many misses with high threshold sensitivity: if hitRate low, raise threshold; if high, can lower slightly
  let thr=base;
  if(hit < 0.35 && avg > 0.5) thr = Math.min(0.75, base+0.05);
  else if(hit > 0.55 && avg < 0.55) thr = Math.max(0.40, base-0.03);
  return Number(thr.toFixed(3));
}

function buildAdvancedPredictiveFeatures(){
  const ema=cornersEma10();
  const opi=offensivePressureIndex();
  const eff=cornerEfficiency();
  const react=goalReactionFeature();
  const num=numericalSuperiorityFeature();
  const kal=kalmanCornerRate();
  const am=state.analyst?.advanced_metrics||{};
  const cpiH=Number(am.CPI_v2?.home?.cpi), cpiA=Number(am.CPI_v2?.away?.cpi);
  const bandH=Number.isFinite(cpiH)?cpiConfidenceBand(cpiH, kal.uncertainty):null;
  const bandA=Number.isFinite(cpiA)?cpiConfidenceBand(cpiA, kal.uncertainty):null;
  let pred=am.temporal?.prediction_corner_2m||null;
  if(pred && Number.isFinite(Number(pred.probability))){
    const raw=Number(pred.probability);
    const scaled=plattScale(raw);
    const oc=detectOverconfidence(scaled, {width: Math.max(bandH?.width||0.2, bandA?.width||0.2)});
    const finalP = oc.flag && oc.suggestedCap!=null ? Math.min(scaled, oc.suggestedCap) : scaled;
    pred={
      ...pred,
      probability_raw: raw,
      probability: finalP,
      platt: scaled,
      overconfidence: oc,
      threshold: adaptiveAlertThreshold()
    };
  }
  return {
    schema:"cornerai-predictive-features-1",
    cornersEma: ema,
    offensivePressureIndex: opi,
    cornerEfficiency: eff,
    goalReaction: react,
    numericalSuperiority: num,
    kalmanCornerRate: kal,
    cpiBand: {home:bandH, away:bandA},
    prediction: pred,
    adaptiveThreshold: adaptiveAlertThreshold(),
    derivedAt: Date.now()
  };
}



// ===== Skill API I/O Monitor (v6.9.9) =====
const __skillMonitor = {
  log: [],           // recent IO events
  lastIn: null,      // last outbound payload summary
  lastOut: null,     // last inbound reply summary
  lastError: null,
  connection: { ok:null, testedAt:0, models:[], latencyMs:null, detail:null },
  totals: { requests:0, ok:0, fail:0, bytesIn:0, bytesOut:0 }
};
async function persistSkillMonitor(){
  try{
    await chrome.storage.local.set({
      cornerai_skill_monitor: {
        log: __skillMonitor.log.slice(0,40),
        lastIn: __skillMonitor.lastIn,
        lastOut: __skillMonitor.lastOut,
        lastError: __skillMonitor.lastError,
        connection: __skillMonitor.connection,
        totals: __skillMonitor.totals,
        updatedAt: Date.now()
      }
    });
  }catch{}
}
async function loadSkillMonitor(){
  try{
    const r=await chrome.storage.local.get(["cornerai_skill_monitor"]);
    const m=r.cornerai_skill_monitor;
    if(m&&typeof m==="object"){
      __skillMonitor.log=Array.isArray(m.log)?m.log.slice(0,40):[];
      __skillMonitor.lastIn=m.lastIn||null;
      __skillMonitor.lastOut=m.lastOut||null;
      __skillMonitor.lastError=m.lastError||null;
      __skillMonitor.connection=m.connection||__skillMonitor.connection;
      __skillMonitor.totals=m.totals||__skillMonitor.totals;
    }
  }catch{}
}
function skillMonitorPush(entry){
  const e={
    id:`SM-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
    at: new Date().toISOString(),
    ts: Date.now(),
    ...entry
  };
  __skillMonitor.log.unshift(e);
  __skillMonitor.log=__skillMonitor.log.slice(0,50);
  if(entry.direction==="out" || entry.phase==="request"){
    __skillMonitor.lastIn={
      at:e.at, reason:e.reason, model:e.model, fixtureId:e.fixtureId,
      promptChars:e.promptChars, payloadKeys:e.payloadKeys,
      match:e.match, estTokens:e.estTokens
    };
  }
  if(entry.phase==="response" && entry.ok){
    __skillMonitor.lastOut={
      at:e.at, model:e.model, latencyMs:e.latencyMs,
      replyChars:e.replyChars, replyPreview:e.replyPreview,
      httpStatus:e.httpStatus
    };
    __skillMonitor.lastError=null;
  }
  if(entry.ok===false || entry.phase==="error"){
    __skillMonitor.lastError={
      at:e.at, message:e.error||entry.message||"erro",
      httpStatus:e.httpStatus, model:e.model, phase:e.phase
    };
  }
  void persistSkillMonitor();
  return e;
}
function buildSkillMonitorReport(){
  const cfg=publicGeminiStatus();
  const last=__skillMonitor.log[0]||null;
  const recentErrors=__skillMonitor.log.filter(x=>x.ok===false||x.phase==="error").slice(0,8);
  const recentOk=__skillMonitor.log.filter(x=>x.ok===true&&x.phase==="response").slice(0,5);
  let health="offline";
  if(!cfg.hasKey) health="no_key";
  else if(__skillMonitor.connection.ok===true) health="connected";
  else if(__skillMonitor.connection.ok===false) health="auth_or_model_fail";
  else if(cfg.runs>0 && cfg.fails===0) health="ok_untested";
  else if(cfg.fails>0 && cfg.lastError) health="degraded";
  else health="idle";
  return {
    schema:"cornerai-skill-monitor-1",
    version:VERSION,
    health,
    healthLabel:{
      offline:"Sem atividade",
      no_key:"API key ausente",
      connected:"Conexão OK (teste)",
      auth_or_model_fail:"Falha de auth/modelo",
      ok_untested:"Já houve runs OK",
      degraded:"Com erros recentes",
      idle:"Aguardando primeiro envio"
    }[health]||health,
    config:cfg,
    connection:__skillMonitor.connection,
    totals:__skillMonitor.totals,
    lastIn:__skillMonitor.lastIn,
    lastOut:__skillMonitor.lastOut,
    lastError:__skillMonitor.lastError,
    recentErrors,
    recentOk,
    log:__skillMonitor.log.slice(0,20),
    capture:{
      fixtureId:state.fixtureId,
      home:state.home, away:state.away,
      minute:state.minute, liveStatus:state.liveStatus,
      integrity:state.integrity?.score??null,
      snapshots:state.capture?.acceptedSnapshots||0
    },
    tips: buildSkillMonitorTips(health, cfg)
  };
}
function buildSkillMonitorTips(health, cfg){
  const tips=[];
  if(health==="no_key") tips.push("Cole a API Key no campo Gemini e clique Salvar.");
  if(health==="auth_or_model_fail") tips.push("Teste a key no AI Studio; tente outro modelo (3.6 flash / 3.5 flash).");
  if(health==="degraded") tips.push("Veja lastError e o log de I/O; falhas de modelo disparam fallback automático.");
  if(!state.fixtureId) tips.push("Abra uma partida e aguarde fixtureId antes de Analisar.");
  if(cfg.hasKey && !cfg.enabled) tips.push("Ativo desmarcado: Auto/Alertas off; Analisar agora ainda funciona.");
  if((cfg.dayRuns||0)>=(cfg.maxCallsPerDay||80)) tips.push("Teto diário de chamadas atingido.");
  if(!tips.length) tips.push("Monitor saudável. Use Testar conexão ou Analisar agora.");
  return tips;
}
async function testSkillConnection(){
  const cfg=__geminiCfg||await loadGeminiConfig();
  const started=Date.now();
  if(!cfg.apiKey){
    __skillMonitor.connection={ok:false,testedAt:Date.now(),models:[],latencyMs:null,detail:"API key ausente"};
    skillMonitorPush({phase:"error", direction:"test", ok:false, error:"API key ausente", reason:"connection_test"});
    await persistSkillMonitor();
    return {ok:false, error:"API key ausente", connection:__skillMonitor.connection};
  }
  skillMonitorPush({phase:"request", direction:"test", ok:null, reason:"connection_test", model:"list", promptChars:0});
  try{
    // 1) List models (auth + network check)
    const listUrl=`https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(cfg.apiKey)}&pageSize=30`;
    const listResp=await fetch(listUrl);
    const listData=await listResp.json().catch(()=>({}));
    if(!listResp.ok){
      const err=listData?.error?.message||`HTTP ${listResp.status}`;
      __skillMonitor.connection={ok:false,testedAt:Date.now(),models:[],latencyMs:Date.now()-started,detail:err,httpStatus:listResp.status};
      __skillMonitor.totals.fail++;
      skillMonitorPush({phase:"error", direction:"test", ok:false, error:err, httpStatus:listResp.status, latencyMs:Date.now()-started, reason:"connection_test"});
      await persistSkillMonitor();
      return {ok:false, error:err, connection:__skillMonitor.connection};
    }
    const models=(listData?.models||[])
      .map(m=>String(m.name||"").replace(/^models\//,""))
      .filter(n=>/gemini/i.test(n))
      .slice(0,25);
    // 2) Tiny generateContent on preferred or first available
    const preferred=String(cfg.model||"gemini-3.5-flash-lite");
    const tryModels=[preferred, ...models.filter(m=>/flash/i.test(m))].filter((v,i,a)=>a.indexOf(v)===i).slice(0,5);
    let genOk=false, genModel=null, genErr=null, replyPreview=null;
    for(const model of tryModels){
      const url=`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(cfg.apiKey)}`;
      const body={contents:[{role:"user",parts:[{text:"Responda só: OK"}]}],generationConfig:{maxOutputTokens:8,temperature:0}};
      try{
        const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
        const d=await r.json().catch(()=>({}));
        if(!r.ok){
          const msg=d?.error?.message||`HTTP ${r.status}`;
          if(/no longer available|not found|NOT_FOUND/i.test(msg)) continue;
          genErr=msg; break;
        }
        replyPreview=d?.candidates?.[0]?.content?.parts?.[0]?.text||"";
        genOk=true; genModel=model; break;
      }catch(e){ genErr=e?.message||String(e); }
    }
    const latency=Date.now()-started;
    __skillMonitor.connection={
      ok:genOk, testedAt:Date.now(), models, latencyMs:latency,
      detail: genOk?`OK via ${genModel}`:(genErr||"generateContent falhou"),
      workingModel: genModel
    };
    if(genOk && genModel && genModel!==preferred){
      __geminiCfg.model=genModel;
      try{await saveGeminiConfig({});}catch{}
    }
    __skillMonitor.totals.requests++;
    if(genOk) __skillMonitor.totals.ok++; else __skillMonitor.totals.fail++;
    skillMonitorPush({
      phase: genOk?"response":"error", direction:"test", ok:genOk,
      model:genModel||preferred, latencyMs:latency,
      replyPreview: replyPreview?String(replyPreview).slice(0,80):null,
      replyChars: replyPreview?String(replyPreview).length:0,
      error: genOk?null:(genErr||"falha"),
      reason:"connection_test", modelsAvailable:models.length
    });
    await persistSkillMonitor();
    return {ok:genOk, connection:__skillMonitor.connection, models:models.slice(0,15), workingModel:genModel, error:genOk?null:genErr};
  }catch(e){
    const msg=e?.message||String(e);
    __skillMonitor.connection={ok:false,testedAt:Date.now(),models:[],latencyMs:Date.now()-started,detail:msg};
    __skillMonitor.totals.fail++;
    skillMonitorPush({phase:"error", direction:"test", ok:false, error:msg, reason:"connection_test", latencyMs:Date.now()-started});
    await persistSkillMonitor();
    return {ok:false, error:msg, connection:__skillMonitor.connection};
  }
}


const GEMINI_DEFAULTS = {
  enabled: false,
  auto: false,
  apiKey: null,
  model: "gemini-3.5-flash-lite",
  intervalMs: 60000,           // 60s default — skill auto
  onAlert: true,
  maxOutputTokens: 512,        // shorter replies
  temperature: 0.2,
  // cost controls
  economy: true,               // micro legível (skill-feed-1)
  onlyCriticalWindows: false,  // skill analisa o jogo inteiro
  minDeltaScore: 0.12,         // skip if state barely changed
  maxCallsPerMatch: 30,
  maxCallsPerDay: 80,
  alertMinGapMs: 180000,       // 3 min between alert-triggered calls
  lastRunAt: 0,
  lastOkAt: 0,
  lastError: null,
  runs: 0,
  fails: 0,
  skipped: 0,
  dayKey: null,
  dayRuns: 0,
  matchId: null,
  matchRuns: 0,
  lastFingerprint: null,
  estInputTokens: 0,
  estOutputTokens: 0
};
let __geminiCfg = {...GEMINI_DEFAULTS};
let __geminiTimer = null;

function geminiTodayKey(){
  const d=new Date();
  return `${d.getUTCFullYear()}-${d.getUTCMonth()+1}-${d.getUTCDate()}`;
}
function estimateTokens(str){
  // rough heuristic ~4 chars/token for mixed PT/JSON
  return Math.ceil(String(str||"").length/4);
}
function inCriticalWindow(minute){
  const m=Number(minute);
  if(!Number.isFinite(m)) return false;
  const windows = (PARAMS.criticalWindows)||[{from:28,to:48},{from:78,to:105}];
  return windows.some(w=>m>=w.from && m<=w.to);
}
function buildGeminiFingerprint(){
  const c=state.stats?.corners||{};
  const x=state.stats?.xg||{};
  const d=state.stats?.dangerous||{};
  const am=state.analyst?.advanced_metrics||{};
  const cpiH=am.CPI_v2?.home?.cpi, cpiA=am.CPI_v2?.away?.cpi;
  const pred=am.temporal?.prediction_corner_2m?.probability;
  return [
    state.fixtureId||"",
    state.minute??"",
    state.score?.home??"",
    state.score?.away??"",
    c.home??"",c.away??"",
    x.home??"",x.away??"",
    d.home??"",d.away??"",
    Number(cpiH||0).toFixed(2),
    Number(cpiA||0).toFixed(2),
    Number(pred||0).toFixed(2)
  ].join("|");
}
function deltaScore(prevFp, nextFp){
  if(!prevFp || !nextFp) return 1;
  const a=prevFp.split("|"), b=nextFp.split("|");
  if(a.length!==b.length) return 1;
  let changed=0;
  // minute change alone is weak; weight meaningful fields
  const weights=[0,0.05,0.25,0.25,0.2,0.2,0.15,0.15,0.15,0.15,0.25,0.25,0.3];
  for(let i=0;i<a.length;i++){
    if(a[i]!==b[i]) changed += weights[i]||0.1;
  }
  return Number(Math.min(1, changed).toFixed(3));
}

async function loadGeminiConfig(){
  try{
    const r = await chrome.storage.local.get(["cornerai_gemini", "cornerai_durable_api_key"]);
    let syncKey = null, syncModel = null;
    try {
      const s = await chrome.storage.sync.get(["cornerai_durable_api_key", "cornerai_gemini_model"]);
      syncKey = s.cornerai_durable_api_key || null;
      syncModel = s.cornerai_gemini_model || null;
    } catch {}
    __geminiCfg = {...GEMINI_DEFAULTS, ...(r.cornerai_gemini||{})};
    // Restaura key de backups se sumiu no local (update / race)
    if (!__geminiCfg.apiKey) {
      __geminiCfg.apiKey = r.cornerai_durable_api_key || syncKey || null;
    }
    if ((!__geminiCfg.model || __geminiCfg.model === GEMINI_DEFAULTS.model) && syncModel) {
      __geminiCfg.model = syncModel;
    }
    if(!__geminiCfg.apiKey) __geminiCfg.apiKey = null;
    // Rehidrata local se só sync tinha a key
    if (__geminiCfg.apiKey && !(r.cornerai_gemini && r.cornerai_gemini.apiKey)) {
      try { await chrome.storage.local.set({ cornerai_gemini: {...__geminiCfg}, cornerai_durable_api_key: __geminiCfg.apiKey }); } catch {}
    }
    // Migrate retired model IDs (2.0 / 1.5 families)
    const DEPRECATED_MODELS={
      "gemini-2.0-flash-lite":"gemini-3.5-flash-lite",
      "gemini-2.0-flash":"gemini-3.5-flash",
      "gemini-2.5-flash-lite":"gemini-3.5-flash-lite",
      "gemini-2.5-flash":"gemini-3.5-flash",
      "gemini-2.5-pro":"gemini-3.1-pro-preview",
      "gemini-1.5-flash":"gemini-3.5-flash-lite",
      "gemini-1.5-pro":"gemini-3.5-flash",
      "gemini-pro":"gemini-3.5-flash-lite"
    };
    const mid=String(__geminiCfg.model||"");
    if(DEPRECATED_MODELS[mid]){
      __geminiCfg.model=DEPRECATED_MODELS[mid];
      try{ chrome.storage.local.get(["cornerai_gemini"]).then(x=>{
        const c={...(x.cornerai_gemini||{}), model:__geminiCfg.model};
        chrome.storage.local.set({cornerai_gemini:c});
      }); }catch{}
    }
    // roll day counter
    const dk=geminiTodayKey();
    if(__geminiCfg.dayKey!==dk){ __geminiCfg.dayKey=dk; __geminiCfg.dayRuns=0; }
    // roll match counter
    if(state.fixtureId && __geminiCfg.matchId!==String(state.fixtureId)){
      __geminiCfg.matchId=String(state.fixtureId);
      __geminiCfg.matchRuns=0;
      __geminiCfg.lastFingerprint=null;
    }
    state.gemini = publicGeminiStatus();
    scheduleGeminiAuto();
    return __geminiCfg;
  }catch(e){
    __geminiCfg = {...GEMINI_DEFAULTS};
    return __geminiCfg;
  }
}
function publicGeminiStatus(){
  return {
    enabled: !!__geminiCfg.enabled,
    auto: !!__geminiCfg.auto,
    model: __geminiCfg.model,
    intervalMs: __geminiCfg.intervalMs,
    onAlert: __geminiCfg.onAlert !== false,
    economy: __geminiCfg.economy !== false,
    onlyCriticalWindows: !!__geminiCfg.onlyCriticalWindows,
    maxCallsPerMatch: Number(__geminiCfg.maxCallsPerMatch)||30,
    maxCallsPerDay: Number(__geminiCfg.maxCallsPerDay)||80,
    hasKey: !!__geminiCfg.apiKey,
    lastRunAt: __geminiCfg.lastRunAt||0,
    lastOkAt: __geminiCfg.lastOkAt||0,
    lastError: __geminiCfg.lastError||null,
    runs: __geminiCfg.runs||0,
    fails: __geminiCfg.fails||0,
    skipped: __geminiCfg.skipped||0,
    dayRuns: __geminiCfg.dayRuns||0,
    matchRuns: __geminiCfg.matchRuns||0,
    estInputTokens: __geminiCfg.estInputTokens||0,
    estOutputTokens: __geminiCfg.estOutputTokens||0,
    lastReplyPreview: state.gemini?.lastReplyPreview||null
  };
}
async function saveGeminiConfig(partial){
  const prevKey = __geminiCfg && __geminiCfg.apiKey ? __geminiCfg.apiKey : null;
  let p = Object.assign({}, partial || {});
  // Nunca apagar a key se o partial não trouxer uma nova (evita sumir após update/reload)
  if (p.apiKey === null || p.apiKey === "") {
    if (p._wipeKey !== true) delete p.apiKey;
  }
  __geminiCfg = {...__geminiCfg, ...p};
  if (!__geminiCfg.apiKey && prevKey && p._wipeKey !== true) __geminiCfg.apiKey = prevKey;
  const cfgBlob = {
    enabled: !!__geminiCfg.enabled,
    auto: !!__geminiCfg.auto,
    apiKey: __geminiCfg.apiKey||null,
    model: __geminiCfg.model||GEMINI_DEFAULTS.model,
    intervalMs: Number(__geminiCfg.intervalMs)||60000,
    onAlert: __geminiCfg.onAlert !== false,
    maxOutputTokens: Number(__geminiCfg.maxOutputTokens)||512,
    temperature: Number(__geminiCfg.temperature)||0.2,
    economy: __geminiCfg.economy !== false,
    onlyCriticalWindows: !!__geminiCfg.onlyCriticalWindows,
    minDeltaScore: Number(__geminiCfg.minDeltaScore)||0.12,
    maxCallsPerMatch: Number(__geminiCfg.maxCallsPerMatch)||30,
    maxCallsPerDay: Number(__geminiCfg.maxCallsPerDay)||80,
    alertMinGapMs: Number(__geminiCfg.alertMinGapMs)||180000,
    lastRunAt: __geminiCfg.lastRunAt||0,
    lastOkAt: __geminiCfg.lastOkAt||0,
    lastError: __geminiCfg.lastError||null,
    runs: __geminiCfg.runs||0,
    fails: __geminiCfg.fails||0,
    skipped: __geminiCfg.skipped||0,
    dayKey: __geminiCfg.dayKey||geminiTodayKey(),
    dayRuns: __geminiCfg.dayRuns||0,
    matchId: __geminiCfg.matchId||null,
    matchRuns: __geminiCfg.matchRuns||0,
    lastFingerprint: __geminiCfg.lastFingerprint||null,
    estInputTokens: __geminiCfg.estInputTokens||0,
    estOutputTokens: __geminiCfg.estOutputTokens||0
  };
  await chrome.storage.local.set({
    cornerai_gemini: cfgBlob,
    // backup dedicado — nunca misturado com state da partida
    cornerai_durable_api_key: cfgBlob.apiKey || null
  });
  // chrome.storage.sync sobrevive melhor a alguns fluxos de update (mesma conta Google)
  try {
    if (cfgBlob.apiKey) {
      await chrome.storage.sync.set({
        cornerai_durable_api_key: cfgBlob.apiKey,
        cornerai_gemini_model: cfgBlob.model
      });
    }
  } catch (e) { /* sync pode falhar offline / quota */ }
  state.gemini = publicGeminiStatus();
  scheduleGeminiAuto();
  return publicGeminiStatus();
}

function pairNum(v){
  if(!v||typeof v!=="object") return null;
  const h=v.home, a=v.away;
  if(h==null&&a==null) return null;
  return [h??null, a??null];
}

// [FIX v6.9.9.75] Validador estrito + lifecycle da skill. Roda IMEDIATAMENTE antes de
// qualquer exportação (download, copiar p/ skill, POST pro bridge). Regras equivalentes
// a um schema Zod em vanilla JS puro. Inclui checagem de skillReady e stateVersion.

// ─── Players derivados + gate único de qualidade no export ───
function mergePlayersFromState(){
  if(!state.players || typeof state.players!=="object"){
    state.players={available:false,byId:{},homeIds:[],awayIds:[]};
  }
  const byId=state.players.byId&&typeof state.players.byId==="object"?{...state.players.byId}:{};
  const bump=(id,patch)=>{
    if(!id) return;
    const cur=byId[id]||{
      playerId:id,name:patch.name||id,teamSide:patch.teamSide||null,teamName:patch.teamName||null,
      minutes:null,goals:0,assists:0,shots:null,shotsOn:null,fouls:null,yellow:0,red:0,cornersTaken:0
    };
    if(patch.name) cur.name=patch.name;
    if(patch.teamSide) cur.teamSide=patch.teamSide;
    if(patch.teamName) cur.teamName=patch.teamName;
    if(patch.goal) cur.goals=(cur.goals||0)+1;
    if(patch.yellow) cur.yellow=(cur.yellow||0)+1;
    if(patch.red) cur.red=(cur.red||0)+1;
    if(patch.corner) cur.cornersTaken=(cur.cornersTaken||0)+1;
    byId[id]=cur;
  };
  // payload.players (rede/DOM)
  // (mergeSnapshot chama mergePlayersPayload)
  // Blacklist de labels de evento que o DOM às vezes trata como "nome de jogador"
  // [FIX v6.9.9.77] blacklist expandida (labels de evento que viram "jogador")
  const PLAYER_NOISE=/^(chute|bloqueado|impedimento|offside|falta|foul|corner|escanteio|escante|gol|goal|cart[aã]o|amarelo|vermelho|substit|ataque|posse|cruzamento|defesa|save|tiro|livre|penal|ao lado|no gol|meta|lateral|var|bloqueado|chute bloqueado|tiro de meta)/i;
  for(const e of (state.matchEvents||[])){
    const pname=String(e.playerName||"").trim();
    if(!pname || pname.length<3) continue;
    if(PLAYER_NOISE.test(pname)) continue;
    if(/chute|bloqueado|impedimento|offside|falta|foul|escante|corner|gol\b|goal\b|amarelo|vermelho|substit/i.test(pname)) continue;
    const pid=String(e.playerId||("name:"+pname.toLowerCase()));
    if(PLAYER_NOISE.test(pid.replace(/^name:/,""))) continue;
    const patch={name:pname,teamSide:e.side||null,teamName:e.team||e.teamName||null};
    if(e.type==="goal") patch.goal=1;
    if(e.type==="yellow") patch.yellow=1;
    if(e.type==="red") patch.red=1;
    if(e.type==="corner") patch.corner=1;
    bump(pid,patch);
  }
  // Remove lixo residual que já estava no byId
  for(const id of Object.keys(byId)){
    const n=String(byId[id]?.name||id.replace(/^name:/,""));
    if(PLAYER_NOISE.test(n) || /chute|bloqueado|impedimento|offside|falta|foul|escante|corner/i.test(n)){
      delete byId[id];
    }
  }
  const homeIds=[], awayIds=[];
  for(const [id,p] of Object.entries(byId)){
    if(p.teamSide==="home") homeIds.push(id);
    else if(p.teamSide==="away") awayIds.push(id);
  }
  state.players={
    available:Object.keys(byId).length>0,
    byId,
    homeIds,
    awayIds
  };
}
function mergePlayersPayload(players,source){
  if(!players) return;
  if(!state.players) state.players={available:false,byId:{},homeIds:[],awayIds:[]};
  const byId={...(state.players.byId||{})};
  const list=Array.isArray(players)?players:(players.byId?Object.values(players.byId):[]);
  for(const p of list){
    if(!p||typeof p!=="object") continue;
    const name=String(p.name||p.playerName||"").trim();
    if(!name) continue;
    const id=String(p.playerId||p.id||("name:"+name.toLowerCase()));
    const side=p.teamSide||p.side||null;
    byId[id]={
      playerId:id,
      name,
      teamSide:side==="home"||side==="away"?side:null,
      teamName:p.teamName||p.team||null,
      minutes:finite(p.minutes)?Number(p.minutes):null,
      goals:Number(p.goals)||0,
      assists:Number(p.assists)||0,
      shots:finite(p.shots)?Number(p.shots):null,
      shotsOn:finite(p.shotsOn)?Number(p.shotsOn):null,
      fouls:finite(p.fouls)?Number(p.fouls):null,
      yellow:Number(p.yellow)||0,
      red:Number(p.red)||0,
      cornersTaken:finite(p.cornersTaken)?Number(p.cornersTaken):null,
      source:source||p.source||"network"
    };
  }
  const homeIds=[], awayIds=[];
  for(const [id,p] of Object.entries(byId)){
    if(p.teamSide==="home") homeIds.push(id);
    else if(p.teamSide==="away") awayIds.push(id);
  }
  state.players={available:Object.keys(byId).length>0,byId,homeIds,awayIds};
}

/** Gate único: todo export (manual, daily, batch) passa por aqui */
function exportQualityGate(opts){
  opts=opts||{};
  const force=!!opts.force;
  const errors=[];
  const warnings=[];
  if(!state.fixtureId) errors.push("fixtureId ausente");
  if(!state.home||!String(state.home).trim()) errors.push("home ausente");
  if(!state.away||!String(state.away).trim()) errors.push("away ausente");
  const st=state.liveStatus;
  if(!(st==="live"||st==="finished"||state.dataMode==="historical")) errors.push("status instável: "+st);
  if(!state.score||(state.score.home==null&&state.score.away==null)) errors.push("placar ausente");
  const snaps=Number(state.snapshotCount||state.capture?.acceptedSnapshots||0);
  const corners=(state.cornerEvents||[]).length;
  const hasCore=!!(state.stats?.corners||state.stats?.dangerous||state.stats?.xg);
  if(snaps<1 && corners<1 && !hasCore) errors.push("sem stats/cantos/snapshots");
  // 9.2.9: integrity FAIL is warning for export unless no core data at all
  if(state.integrity && state.integrity.pass===false && !state.home) errors.push("integridade FAIL");
  // alinhamento cantos se ambos existem
  try{
    const cs=state.stats?.corners;
    if(cs && (cs.home!=null||cs.away!=null) && corners>0){
      const eh=(state.cornerEvents||[]).filter(e=>e.side==="home").length;
      const ea=(state.cornerEvents||[]).filter(e=>e.side==="away").length;
      const lagH=Math.abs((cs.home??eh)-eh);
      const lagA=Math.abs((cs.away??ea)-ea);
      if(lagH>2||lagA>2) errors.push(`cantos desalinhados stats×eventos lag ${lagH}/${lagA}`);
    }
  }catch{}
  const stale=state.capture?.lastPayloadAt?(Date.now()-Number(state.capture.lastPayloadAt||0)):null;
  if(typeof stale==="number" && stale>180000 && st==="live") errors.push("dados stale >3min em live");
  if(stale!=null && stale>30000 && st==="live") warnings.push("freshness >30s");
  if(force && errors.length){
    return {ok:true, forced:true, errors, warnings, blocked:false};
  }
  return {ok:errors.length===0, forced:false, errors, warnings, blocked:errors.length>0};
}

function validateSkillPack(pack){
  // Aceita cornerai-skill-v3 (preferencial) e cornerai-skill-manual-2 (legado)
  const errors=[];
  const isPair=(v,path)=>{
    if(!Array.isArray(v)||v.length<2){errors.push(`${path}: esperado par [home,away]`);return;}
    v.forEach((x,i)=>{if(x!==null && typeof x!=="number"){errors.push(`${path}[${i}]: esperado number|null`);}});
  };
  if(!pack||typeof pack!=="object"){return{ok:false,errors:["payload raiz não é um objeto"]};}

  const schema=pack.schema;
  if(schema!=="cornerai-skill-v3" && schema!=="cornerai-skill-manual-2"){
    errors.push(`schema: esperado cornerai-skill-v3|cornerai-skill-manual-2, recebi ${JSON.stringify(schema)}`);
  }

  // --- v3 path ---
  if(schema==="cornerai-skill-v3"){
    const meta=pack.meta||{};
    if(typeof meta.exportedAtMs!=="number") errors.push("meta.exportedAtMs: number obrigatório");
    if(typeof meta.stateVersion!=="number"||meta.stateVersion<0) errors.push("meta.stateVersion inválido");
    if(typeof meta.fixtureId!=="string"||!meta.fixtureId) errors.push("meta.fixtureId ausente");
    if(typeof meta.skillReady!=="boolean") errors.push("meta.skillReady: boolean");
    if(typeof meta.contentSha256!=="string"||meta.contentSha256.length<16) errors.push("meta.contentSha256 ausente/curto");
    const m=pack.match||{};
    if(typeof m.home!=="string"||!m.home.trim()) errors.push("match.home ausente");
    if(typeof m.away!=="string"||!m.away.trim()) errors.push("match.away ausente");
    if(m.minute!=null && (typeof m.minute!=="number"||m.minute<0||m.minute>130)) errors.push("match.minute fora de 0-130");
    isPair(m.score,"match.score");
    const pairs=pack.teams?.pairs||{};
    for(const k of ["corners","attacks","dangerous","shotsOn","xg","possession"]){
      if(k in pairs) isPair(pairs[k],`teams.pairs.${k}`);
    }
    if(!pack.timeline||!Array.isArray(pack.timeline.corners)) errors.push("timeline.corners: array obrigatório");
    if(!pack.timeline||!Array.isArray(pack.timeline.events)) errors.push("timeline.events: array obrigatório");
    if(pack.integrity && typeof pack.integrity.pass!=="boolean") errors.push("integrity.pass: boolean");
    if(meta.skillReady===false) errors.push("skillReady=false: captura não estável");
    if(typeof meta.skillStaleMs==="number" && meta.skillStaleMs>120000) errors.push(`skillStaleMs=${meta.skillStaleMs}: dados >2min`);
    return{ok:errors.length===0,errors};
  }

  // --- legado manual-2 ---
  if(typeof pack.exportedAt!=="string"||isNaN(Date.parse(pack.exportedAt))) errors.push(`exportedAt inválido`);
  if(pack.stateVersion!=null && (typeof pack.stateVersion!=="number"||pack.stateVersion<0)) errors.push(`stateVersion inválido`);
  if(typeof pack.skillReady!=="boolean") errors.push(`skillReady: boolean`);
  const m=pack.match||{};
  if(typeof m.home!=="string"||!m.home.trim()) errors.push("match.home ausente");
  if(typeof m.away!=="string"||!m.away.trim()) errors.push("match.away ausente");
  if(m.minute!=null && (typeof m.minute!=="number"||m.minute<0||m.minute>130)) errors.push("match.minute fora de 0-130");
  const s=pack.stats||{};
  for(const k of ["corners","attacks","dangerous","shotsOn","shots","shotsOff","possession","xg","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed"]){
    if(k in s) isPair(s[k],`stats.${k}`); else errors.push(`stats.${k}: chave ausente`);
  }
  if(!Array.isArray(pack.corner_events)) errors.push("corner_events: array");
  if(!Array.isArray(pack.match_events)) errors.push("match_events: array");
  if(pack.skillReady===false) errors.push("skillReady=false");
  if(typeof pack.skillStaleMs==="number" && pack.skillStaleMs>120000) errors.push(`skillStaleMs=${pack.skillStaleMs}`);
  return{ok:errors.length===0,errors};
}

function buildSkillPackForChat(){
  // cornerai-skill-v3 — contrato hierárquico O(1)/O(k) para a Skill
  // + aliases legados para bridge/validate durante transição
  const micro = (typeof buildGeminiMicroPayload==="function") ? buildGeminiMicroPayload() : {};
  const analyst = (typeof buildAnalystFeed==="function") ? buildAnalystFeed() : (state.analyst||{});
  const fix = analyst.fixture || {};
  const minute = fix.minute ?? state.minute ?? micro.minute;
  const home = fix.home || state.home || micro.home || "";
  const away = fix.away || state.away || micro.away || "";
  const scoreH = Array.isArray(fix.score)?fix.score[0]:(state.score?.home??null);
  const scoreA = Array.isArray(fix.score)?fix.score[1]:(state.score?.away??null);
  const pair = (v)=>{
    if(Array.isArray(v)&&v.length>=2) return [v[0]??null, v[1]??null];
    if(v&&typeof v==="object") return [v.home??null, v.away??null];
    return [null, null];
  };
  const STATS_ALL = ["attacks","dangerous","shots","shotsOn","shotsOff","corners","xg","possession","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed"];
  const fullStats = {};
  for(const k of STATS_ALL){
    fullStats[k] = pair(state.stats?.[k] || analyst.pressure?.[k] || null);
  }
  if(fullStats.corners[0]==null&&fullStats.corners[1]==null) fullStats.corners=[micro.corners_home??null,micro.corners_away??null];
  if(fullStats.dangerous[0]==null&&fullStats.dangerous[1]==null) fullStats.dangerous=[micro.dangerous_home??null,micro.dangerous_away??null];
  if(fullStats.shotsOn[0]==null&&fullStats.shotsOn[1]==null) fullStats.shotsOn=[micro.shots_on_home??null,micro.shots_on_away??null];
  if(fullStats.xg[0]==null&&fullStats.xg[1]==null) fullStats.xg=[micro.xg_home??null,micro.xg_away??null];
  if(fullStats.possession[0]==null&&fullStats.possession[1]==null) fullStats.possession=[micro.possession_home??null,micro.possession_away??null];
  if(fullStats.attacks[0]==null&&fullStats.attacks[1]==null) fullStats.attacks=[micro.attacks_home??null,micro.attacks_away??null];

  const matchEvents = Array.isArray(state.matchEvents)?state.matchEvents.slice():[];
  const cornerEvents = Array.isArray(state.cornerEvents)?state.cornerEvents.slice():[];
  const sortedCorners = cornerEvents.slice().sort((a,b)=>(a.period-b.period)||(a.minute-b.minute)||((a.extraMinute||0)-(b.extraMinute||0)));
  // Contadores por lado para renumerar ordinal corretamente (evita "7º" com só 6 eventos)
  let ordHome=0, ordAway=0;
  const ordinalPt=(n)=>n+"º";
  const mapEv = (e,i)=>{
    const side=e.side==="home"||e.side==="away"?e.side:null;
    let label=e.label||null;
    // Corrige ordinal de escanteio no label com base na ordem real dos eventos
    if(e.type==="corner" && side){
      if(side==="home") ordHome++; else ordAway++;
      const ord=side==="home"?ordHome:ordAway;
      const min=Number(e.minute)||0;
      const extra=Number(e.extraMinute)||0;
      const clock=extra>0?`${min}+${extra}`:`${min}`;
      label=`${clock}'${ordinalPt(ord)} Escanteio`;
    }
    // Não exporta playerId lixo
    let playerId=e.playerId||null;
    if(playerId && /chute|bloqueado|impedimento|offside|falta|foul|escante|corner|gol\b|goal\b/i.test(String(playerId))){
      playerId=null;
    }
    return {
      eventId: e.eventId || e.id || `${state.fixtureId||"x"}|${e.type||"ev"}|${e.period||0}|${e.minute??"?"}|${e.extraMinute||0}|${side||""}|${i}`,
      atMs: e.timestamp || e.atMs || null,
      period: (e.period===2?2:1),
      minute: Number(e.minute)||0,
      extraMinute: Number(e.extraMinute)||0,
      type: e.type || "other",
      side,
      teamName: e.team || e.teamName || null,
      playerId,
      label,
      source: e.source || "dom",
      confidence: typeof e.confidence==="number"?e.confidence:0.9
    };
  };
  // Reset contadores e mapear corners primeiro (para ordinal correto)
  ordHome=0; ordAway=0;
  const cornersMapped = sortedCorners.map(mapEv);
  // Eventos gerais: não renumerar corners de novo
  const eventsMapped = matchEvents.slice(-80).map((e,i)=>{
    if(e.type==="corner"){
      // reutiliza label já corrigido se possível
      const match=cornersMapped.find(c=>c.minute===Number(e.minute)&&c.extraMinute===(Number(e.extraMinute)||0)&&c.side===e.side);
      if(match) return {...mapEv(e,i), label:match.label, playerId:null};
    }
    return mapEv(e,i);
  });
  const goalsMapped = eventsMapped.filter(e=>e.type==="goal");
  const cornersHome = cornersMapped.filter(e=>e.side==="home").length;
  const cornersAway = cornersMapped.filter(e=>e.side==="away").length;
  // Alinha stats.corners com eventos quando diferença <= 1 (fonte DOM incompleta)
  if(fullStats.corners){
    const sh=fullStats.corners[0], sa=fullStats.corners[1];
    if(sh!=null && Math.abs(sh-cornersHome)<=1) fullStats.corners[0]=Math.max(sh,cornersHome);
    if(sa!=null && Math.abs(sa-cornersAway)<=1) fullStats.corners[1]=Math.max(sa,cornersAway);
    // Se stats > eventos por 1, confia nos stats (canto pode ter faltado no DOM)
    // Se eventos >= stats, confia nos eventos
    if(sh!=null && cornersHome>sh) fullStats.corners[0]=cornersHome;
    if(sa!=null && cornersAway>sa) fullStats.corners[1]=cornersAway;
  }
  const lastCorner = cornersMapped.length?cornersMapped[cornersMapped.length-1]:null;
  const mNum = Number(minute);
  const gapLast = lastCorner && Number.isFinite(mNum) ? Math.max(0, mNum - Number(lastCorner.minute||0)) : (micro.gap_last_corner??null);
  const liveStatus = fix.status || state.liveStatus || "unknown";
  const isLive = liveStatus==="live";
  const isFinished = liveStatus==="finished" || state.dataMode==="historical";
  const windowId = (!Number.isFinite(mNum))?"OUT":(mNum>=30&&mNum<=48)?"W1":(mNum>=80)?"W2":"OUT";
  const windowPeak = windowId==="W1"?"43-48":windowId==="W2"?"82-88+":"—";
  const qualityScore = Number(state.quality?.score ?? 0);
  const integrityScore = Number(state.integrity?.score ?? 0);
  const integPass = state.integrity?.pass !== false;
  const skillReady = !!(state.fixtureId && home && away && (isLive || isFinished));
  const staleMs = state.capture?.lastPayloadAt ? (Date.now()-Number(state.capture.lastPayloadAt||0)) : null;
  const cpiH = micro.cpi_home ?? state.cpi?.home?.cpi ?? null;
  const cpiA = micro.cpi_away ?? state.cpi?.away?.cpi ?? null;
  const momH = Number(state.intelligence?.momentum?.home ?? 0);
  const momA = Number(state.intelligence?.momentum?.away ?? 0);

  const teamSide = (side, name)=>({
    side,
    name: name|| (side==="home"?"CASA":"VISITANTE"),
    stats: Object.fromEntries(STATS_ALL.map(k=>[k, fullStats[k][side==="home"?0:1]])),
    pressure: { cpi: side==="home"?cpiH:cpiA, momentum: side==="home"?momH:momA },
    cornerMinutes: cornersMapped.filter(e=>e.side===side).map(e=>e.minute)
  });

  const h2h = state.h2h||{};
  const pressureIntervals = [];
  try{
    const bars = state.charts?.pressureBars || analyst.pressureBars || {};
    const entries = Array.isArray(bars) ? bars : Object.entries(bars||{}).map(([label,v])=>({label,...(v||{})}));
    (entries||[]).slice(0,8).forEach(b=>{
      const label=b.label||b.id||"";
      const hp=Number(b.home??b.homePct??b[0]);
      const ap=Number(b.away??b.awayPct??b[1]);
      if(label && Number.isFinite(hp) && Number.isFinite(ap)) pressureIntervals.push({label:String(label),homePct:hp,awayPct:ap});
    });
  }catch{}

  const timelineTail = (Array.isArray(state.statTimeline)?state.statTimeline:[]).slice(-6).map(p=>({
    minute:p.minute,
    corners:pair(p.stats?.corners),
    dangerous:pair(p.stats?.dangerous),
    xg:pair(p.stats?.xg)
  }));

  // Corpo canônico sem timestamps voláteis (para hash)
  const bodyForHash = {
    schema:"cornerai-skill-v3",
    match:{
      fixtureId:String(state.fixtureId||fix.id||""),
      league: fix.league || state.league || state.competition || null,
      home, away, status: liveStatus,
      minute: Number.isFinite(mNum)?mNum:null,
      extraMinute: Number(fix.extra ?? state.extraMinute ?? 0)||0,
      period: Number.isFinite(mNum)&&(mNum>45)?2:1,
      score:[scoreH, scoreA],
      clockDisplay: isFinished?"FT":(Number.isFinite(mNum)?`${mNum}'`:null),
      lastLiveMinute: state.lastLiveMinute ?? (isFinished?mNum:null),
      url: state.url || null
    },
    decision_frame:{
      objective:"next_corner",
      live:isLive,
      finished:isFinished,
      window:windowId,
      windowPeak,
      gapLastCornerMin:gapLast,
      rules:[
        "Uma única DECISÃO: ENTRA | AGUARDA | NÃO ENTRA",
        "Se finished=true: NÃO ENTRA (sem mercado de próximo canto)",
        "Se window=OUT: preferir AGUARDA salvo sequência ≤4min + pressão",
        "ENTRA só se live + W1/W2 + score/MC/gates; null ≠ 0"
      ],
      gates:{ G1_pressure:null, G2_conversion:null, G3_context:isFinished?false:null }
    },
    teams:{
      home: teamSide("home", home),
      away: teamSide("away", away),
      pairs:{
        attacks:fullStats.attacks,
        dangerous:fullStats.dangerous,
        shots:fullStats.shots,
        shotsOn:fullStats.shotsOn,
        shotsOff:fullStats.shotsOff,
        corners:fullStats.corners,
        xg:fullStats.xg,
        possession:fullStats.possession
      }
    },
    players: (function(){
      try{mergePlayersFromState();}catch{}
      const p=state.players||{available:false,byId:{},homeIds:[],awayIds:[]};
      return {
        available:!!p.available,
        byId:p.byId||{},
        homeIds:Array.isArray(p.homeIds)?p.homeIds:[],
        awayIds:Array.isArray(p.awayIds)?p.awayIds:[]
      };
    })(),
    timeline:{
      events:eventsMapped,
      corners:cornersMapped,
      goals:goalsMapped,
      lastCorner,
      counts:{
        events:eventsMapped.length,
        cornersHome, cornersAway,
        goalsHome:goalsMapped.filter(e=>e.side==="home").length,
        goalsAway:goalsMapped.filter(e=>e.side==="away").length
      }
    },
    market:{
      available: Array.isArray(state.oddsHistory)&&state.oddsHistory.length>0,
      quotes:(state.oddsHistory||[]).slice(-40).map((r,i)=>({
        quoteId:r.id||r.quoteId||`q${i}`,
        minute:r.minute??null,
        marketType:r.marketType||"",
        market:r.market||"",
        line:r.line??null,
        selection:r.selection||"",
        odds:typeof r.odds==="number"?r.odds:Number(r.odds)||0,
        impliedProb:r.impliedProbability??r.fairProbability??null
      }))
    },
    context:{
      quality:qualityScore,
      h2h: h2h.captured?{
        available:true,
        matches:h2h.summary?.total??h2h.parameters?.matches??null,
        homeWins:h2h.summary?.homeWins??h2h.parameters?.homeWins??null,
        draws:h2h.summary?.draws??h2h.parameters?.draws??null,
        awayWins:h2h.summary?.awayWins??h2h.parameters?.awayWins??null,
        avgCorners:h2h.parameters?.avgCorners??null
      }:{available:false,matches:null,homeWins:null,draws:null,awayWins:null,avgCorners:null},
      pressureIntervals,
      timelineTail
    },
    integrity:{
      score:integrityScore,
      pass:!!integPass,
      cornersAligned: Math.abs((fullStats.corners[0]??cornersHome)-(cornersHome))<=2 && Math.abs((fullStats.corners[1]??cornersAway)-cornersAway)<=2,
      noFutureEvents:true,
      orderedCorners:true,
      checks: Array.isArray(state.integrity?.checks)?state.integrity.checks.map(c=>({id:c.id,ok:!!c.ok,detail:String(c.detail||"")})):[]
    }
  };

  const contentSha256 = (typeof corneraiSha256Hex==="function")
    ? corneraiSha256Hex(stableStringify(bodyForHash))
    : simpleContentHash(stableStringify(bodyForHash));

  const exportedAtMs = Date.now();
  const pack = {
    schema: "cornerai-skill-v3",
    meta: {
      exportedAtMs,
      stateVersion: Number(state.stateVersion)||0,
      extensionVersion: typeof VERSION!=="undefined"?VERSION:"6.9.9.90",
      fixtureId: String(state.fixtureId||""),
      sourcePriority: ["network","hook","dom"],
      dataMode: state.dataMode || (isFinished?"historical":isLive?"live":"unknown"),
      skillReady,
      skillStaleMs: staleMs,
      contentSha256,
      env: { timezoneOffsetMin: new Date().getTimezoneOffset()*-1, captureHost: "sokkerpro" }
    },
    ...bodyForHash,
    // aliases legados (bridge / skill antiga)
    exportedAt: new Date(exportedAtMs).toISOString(),
    version: typeof VERSION!=="undefined"?VERSION:"6.9.9.90",
    stateVersion: Number(state.stateVersion)||0,
    skillReady,
    skillStaleMs: staleMs,
    instruction: "Contrato cornerai-skill-v3. Leia meta → integrity → decision_frame → teams.pairs → timeline.corners. Uma decisão. Não invente null.",
    stats: fullStats,
    corner_events: cornersMapped,
    match_events: eventsMapped,
    gap_last_corner: gapLast,
    last_corner_min: lastCorner?.minute ?? null,
    gapSource: isLive ? "live" : "historical",
    cpi: [cpiH, cpiA],
    cpiAvailable: cpiH!=null || cpiA!=null,
    window: windowId,
    market: {
      ...(typeof bodyForHash?.market === "object" ? bodyForHash.market : {}),
      available: Array.isArray(state.oddsHistory) && state.oddsHistory.length > 0,
      cornerQuotes: (state.oddsHistory||[]).filter(o=>String(o.marketType||"").toLowerCase()==="corners"||/escante|corner|canto/i.test(String(o.market||""))).length,
      source: "sokkerpro"
    }
  };

  // pasteText organizado para LLM — espelha TODOS os menus do dashboard (compacto)
  const fmt = (p)=> (p&&(p[0]!=null||p[1]!=null))?`${p[0]??"—"} × ${p[1]??"—"}`:"—";
  const fmtN = (v)=> (v==null||v==="")?"—":String(v);

  // Gráficos
  const charts = state.charts || {};
  const chartTabs = Array.isArray(charts.tabs)?charts.tabs.map(t=>t.id||t.label||t).filter(Boolean):[];
  const pressureLines = [];
  try{
    const bars = charts.pressureBars || {};
    const entries = Array.isArray(bars)?bars:Object.entries(bars||{}).map(([label,v])=>({label,...(v||{})}));
    (entries||[]).slice(0,8).forEach(b=>{
      const label=b.label||b.id||"";
      const hp=Number(b.home??b.homePct??b[0]);
      const ap=Number(b.away??b.awayPct??b[1]);
      if(label) pressureLines.push(`- ${label}: ${Number.isFinite(hp)?hp:"—"} × ${Number.isFinite(ap)?ap:"—"}`);
    });
  }catch{}

  // Velas (Δ perigosos entre snapshots) — fallback via pressureBars se timeline esparsa
  const candleLines = [];
  try{
    const tl = Array.isArray(state.statTimeline)?state.statTimeline.slice(-16):[];
    let prevH=null, prevA=null;
    for(const p of tl){
      const h=Number(p.stats?.dangerous?.home??p.stats?.dangerous?.[0]);
      const a=Number(p.stats?.dangerous?.away??p.stats?.dangerous?.[1]);
      if(!Number.isFinite(h)||!Number.isFinite(a)) continue;
      if(prevH!=null){
        const dH=h-prevH, dA=a-prevA;
        if(dH!==0||dA!==0) candleLines.push(`- ${p.minute}' Δperig=${dH>=0?"+":""}${dH} × ${dA>=0?"+":""}${dA}`);
      }
      prevH=h; prevA=a;
    }
    // Fallback: séries de pressão quando não há Δ de dangerous
    if(candleLines.length<2){
      const bars = state.charts?.pressureBars || {};
      const entries = Array.isArray(bars) ? bars : Object.entries(bars||{}).map(([label,v])=>({label,...(v||{})}));
      let pH=null, pA=null;
      for(const b of (entries||[]).slice(-10)){
        const h=Number(b.home??b.homePct??b[0]);
        const a=Number(b.away??b.awayPct??b[1]);
        if(!Number.isFinite(h)||!Number.isFinite(a)) continue;
        if(pH!=null && (h!==pH||a!==pA)){
          candleLines.push(`- pressão ${b.label||"?"}: Δ ${h-pH>=0?"+":""}${(h-pH).toFixed(0)} × ${a-pA>=0?"+":""}${(a-pA).toFixed(0)}`);
        }
        pH=h; pA=a;
      }
    }
  }catch{}

  // Odds (prioriza mercado de escanteios; fallback 1X2/geral)
  const oddsLines = [];
  try{
    const odds = (state.oddsHistory||[]).slice(-40);
    const isCorner = o => {
      const mt = String(o.marketType||"").toLowerCase();
      const mk = String(o.market||"").toLowerCase();
      return mt==="corners" || /escante|corner|canto/.test(mk);
    };
    const cornerOdds = odds.filter(isCorner);
    const otherOdds = odds.filter(o=>!isCorner(o));
    const use = cornerOdds.length ? cornerOdds.slice(-10) : otherOdds.slice(-8);
    if(cornerOdds.length) oddsLines.push(`- [prioridade] ${cornerOdds.length} cotações de escanteio`);
    use.forEach(o=>{
      const tag = isCorner(o) ? "canto" : (o.marketType||"geral");
      oddsLines.push(`- [${tag}] ${o.market||"?"} | ${o.selection||"?"} ${o.line!=null?"("+o.line+")":""} @ ${o.odds??"?"} (${o.minute??"—"}')`);
    });
  }catch{}

  // Menus capturados — corrige textLength/tables (antes mostrava array/undefined)
  const menuLines = [];
  try{
    const mc = state.menuCapture || {};
    const discovered = Array.isArray(mc.discovered)?mc.discovered:[];
    const menus = mc.menus || {};
    const capturedKeys = Object.keys(menus);
    const withContent = capturedKeys.filter(k=>{
      const m=menus[k]||{};
      const tl = Number(m.textLength ?? (typeof m.text==="string"?m.text.length:0))||0;
      const tb = Array.isArray(m.tables)?m.tables.length:Number(m.tables)||0;
      return tl>40 || tb>0;
    });
    menuLines.push(`- descobertos: ${discovered.length||0} · capturados: ${capturedKeys.length} · com conteúdo: ${withContent.length}`);
    capturedKeys.slice(0,14).forEach(key=>{
      const m=menus[key]||{};
      const id = m.menuId || key.split("|")[0] || key;
      const label = m.menuLabel || m.label || m.title || id;
      const tl = Number(m.textLength ?? (typeof m.text==="string"?m.text.length:0))||0;
      const tb = Array.isArray(m.tables)?m.tables.length:Number(m.tables)||0;
      const oddsN = Array.isArray(m.odds)?m.odds.length:0;
      menuLines.push(`- ${id}: ${label} · tabelas=${tb} · chars=${tl}${oddsN?` · odds=${oddsN}`:""}`);
    });
  }catch{}

  // Saúde
  const healthLines = [];
  try{
    const ch = state.captureHealth || {};
    const q = state.quality || {};
    healthLines.push(`- captureHealth: ${ch.grade||"—"} score=${ch.score??"—"} status=${ch.status||"—"}`);
    healthLines.push(`- quality: ${q.grade||"—"} score=${q.score??"—"}`);
    healthLines.push(`- integrity: pass=${integPass} score=${integrityScore}`);
    healthLines.push(`- snapshots aceitos: ${state.capture?.acceptedSnapshots??"—"}`);
    healthLines.push(`- skillReady=${skillReady} · staleMs=${staleMs??"—"}`);
  }catch{}

  const statLines = STATS_ALL.map(k=>`- ${k}: ${fmt(fullStats[k])}`);
  const cornerHomeMins = cornersMapped.filter(c=>c.side==="home").map(c=>c.minute+(c.extraMinute?`+${c.extraMinute}`:""));
  const cornerAwayMins = cornersMapped.filter(c=>c.side==="away").map(c=>c.minute+(c.extraMinute?`+${c.extraMinute}`:""));

  const lines = [
    "### CORNERAI INGEST v3 — leitura O(1) · todos os menus",
    "",
    "## META",
    `- fixture ${pack.meta.fixtureId} · ready=${skillReady} · staleMs=${staleMs??"—"} · sha=${contentSha256.slice(0,16)}…`,
    `- integrity pass=${integPass} score=${integrityScore} · quality=${qualityScore}`,
    `- versão ${VERSION} · stateVersion ${state.stateVersion||"—"}`,
    "",
    "## 1. VISÃO GERAL",
    `- ${home} ${scoreH??"?"}×${scoreA??"?"} ${away}`,
    `- minuto ${minute??"—"}' · status ${liveStatus} · window ${windowId} · finished=${isFinished}`,
    `- cantos ${fmt(fullStats.corners)} (eventos ${cornersHome}×${cornersAway}) · gap último ${gapLast??"—"} min`,
    `- perigosos ${fmt(fullStats.dangerous)} · xG ${fmt(fullStats.xg)} · posse ${fmt(fullStats.possession)}`,
    `- CPI ${fmtN(cpiH)} × ${fmtN(cpiA)} · momentum ${(Number(momH)||0).toFixed(3)} × ${(Number(momA)||0).toFixed(3)}`,
    "",
    "## 2. ESTATÍSTICAS [casa × fora]",
    ...statLines,
    "",
    "## 3. GRÁFICOS",
    `- aba ativa: ${charts.activeId||charts.activeLabel||"—"}`,
    `- abas: ${chartTabs.length?chartTabs.join(", "):"—"}`,
    `- séries: ${charts.seriesCount??(Array.isArray(charts.series)?charts.series.length:"—")} · fontes: ${(charts.sources||[]).join(", ")||"—"}`,
    ...(pressureLines.length?["### Pressão por intervalo",...pressureLines]:["- (sem intervalos de pressão)"]),
    "",
    "## 4. VELAS (Δ perigosos)",
    ...(candleLines.length?candleLines.slice(-8):["- (sem variação capturada)"]),
    "",
    "## 5. ESCANTEIOS",
    `- total stats ${fmt(fullStats.corners)} · eventos ${cornersHome}×${cornersAway}`,
    `- casa minutos: [${cornerHomeMins.join(", ")||"—"}]`,
    `- fora minutos: [${cornerAwayMins.join(", ")||"—"}]`,
    `- timeline:`,
    ...(cornersMapped.length?cornersMapped.map(c=>`  · ${c.minute}${c.extraMinute?`+${c.extraMinute}`:""}' ${c.side||"?"} ${c.label||"corner"}`):["  · (nenhum)"]),
    `- gap último canto: ${gapLast??"—"} min${isLive?"":" (histórico — não usar para entrada)"}`,
    "",
    "## 6. ODDS",
    `- disponíveis: ${pack.market?.available?"sim":"não"} · quotes=${(state.oddsHistory||[]).length}`,
    ...(oddsLines.length?oddsLines:["- (sem odds de canto/geral)"]),
    "",
    "## 7. MENUS",
    ...(menuLines.length?menuLines:["- (nenhum menu capturado)"]),
    "",
    "## 8. SAÚDE",
    ...healthLines,
    "",
    "## DECISION_FRAME",
    ...pack.decision_frame.rules.map((r,i)=>`${i+1}. ${r}`),
    `- gates: G1=${pack.decision_frame.gates?.G1_pressure??"—"} G2=${pack.decision_frame.gates?.G2_conversion??"—"} G3=${pack.decision_frame.gates?.G3_context??"—"}`,
    `- live=${isLive} · finished=${isFinished} · window=${windowId}`,
    "",
    "## H2H",
    `- available=${!!pack.context?.h2h?.available} · jogos=${pack.context?.h2h?.matches??"—"} · V/E/D casa=${pack.context?.h2h?.homeWins??"—"}/${pack.context?.h2h?.draws??"—"}/${pack.context?.h2h?.awayWins??"—"}`,
    "",
    "```json",
    JSON.stringify(pack, null, 2),
    "```",
    "",
    "DECISÃO: ENTRA|AGUARDA|NÃO ENTRA · TIMING · LADO · GATE · PRESSÃO · MC · KILLS · JUSTIFICATIVA · REG"
  ];
  const pasteText = lines.join("\n");
  const safeName = String(home||"home").replace(/[^\w\-]+/g,"_").slice(0,20)+"_vs_"+String(away||"away").replace(/[^\w\-]+/g,"_").slice(0,20)+"_"+String(minute??"x")+"min";
  const validation = validateSkillPack(pack);
  if(!validation.ok){
    console.error("[CornerAI] skill-v3 validation errors:", validation.errors);
    state.diagnostics = state.diagnostics || {};
    state.diagnostics.lastExportErrors = validation.errors;
  }
  return { ok:true, json:pack, pack, pasteText, filename:`cornerai_skill_${safeName}.json`, validation };
}

function stableStringify(obj){
  const seen=new WeakSet();
  const walk=(v)=>{
    if(v===null||typeof v!=="object") return v;
    if(seen.has(v)) return null;
    seen.add(v);
    if(Array.isArray(v)) return v.map(walk);
    const out={};
    Object.keys(v).sort().forEach(k=>{ out[k]=walk(v[k]); });
    return out;
  };
  return JSON.stringify(walk(obj));
}
function simpleContentHash(str){
  // FNV-1a 64-bit hex (fallback); prefer corneraiSha256Hex quando disponível
  let h=0xcbf29ce484222325n;
  for(let i=0;i<str.length;i++){
    h^=BigInt(str.charCodeAt(i));
    h=(h*0x100000001b3n)&0xffffffffffffffffn;
  }
  return h.toString(16).padStart(16,"0");
}
function corneraiSha256Hex(message){
  // SHA-256 síncrono mínimo (UTF-8)
  const K=new Uint32Array([0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
  const rotr=(x,n)=>((x>>>n)|(x<<(32-n)))>>>0;
  const bytes=unescape(encodeURIComponent(message));
  const len=bytes.length;
  const bitLen=len*8;
  const withPad=len+1+8;
  const nBlocks=((withPad+63)>>6);
  const buf=new Uint8Array(nBlocks*64);
  for(let i=0;i<len;i++) buf[i]=bytes.charCodeAt(i);
  buf[len]=0x80;
  const dv=new DataView(buf.buffer);
  dv.setUint32(buf.length-4, bitLen>>>0, false);
  dv.setUint32(buf.length-8, Math.floor(bitLen/0x100000000), false);
  let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
  const w=new Uint32Array(64);
  for(let i=0;i<nBlocks;i++){
    const off=i*64;
    for(let t=0;t<16;t++) w[t]=dv.getUint32(off+t*4,false);
    for(let t=16;t<64;t++){
      const s0=rotr(w[t-15],7)^rotr(w[t-15],18)^(w[t-15]>>>3);
      const s1=rotr(w[t-2],17)^rotr(w[t-2],19)^(w[t-2]>>>10);
      w[t]=(w[t-16]+s0+w[t-7]+s1)>>>0;
    }
    let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
    for(let t=0;t<64;t++){
      const S1=rotr(e,6)^rotr(e,11)^rotr(e,25);
      const ch=(e&f)^((~e)&g);
      const t1=(h+S1+ch+K[t]+w[t])>>>0;
      const S0=rotr(a,2)^rotr(a,13)^rotr(a,22);
      const maj=(a&b)^(a&c)^(b&c);
      const t2=(S0+maj)>>>0;
      h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;
    h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+h)>>>0;
  }
  const hex=x=>x.toString(16).padStart(8,"0");
  return hex(h0)+hex(h1)+hex(h2)+hex(h3)+hex(h4)+hex(h5)+hex(h6)+hex(h7);
}


function buildGeminiMicroPayload(){
  const am=state.analyst?.advanced_metrics||{};
  const cpiH=am.CPI_v2?.home?.cpi, cpiA=am.CPI_v2?.away?.cpi;
  const pred=am.temporal?.prediction_corner_2m;
  const live = state.liveStatus==="live" && state.fixtureId && state.minute!=null;
  const minute=Number(state.minute);
  const corners=(state.cornerEvents||[]).slice(-12).map(e=>({
    m:e.minute, side:e.side||e.team||null, extra:e.extraMinute||0
  }));
  let lastCornerMin=null, gap=null;
  if(corners.length){
    lastCornerMin=Number(corners[corners.length-1].m);
    if(Number.isFinite(minute)&&Number.isFinite(lastCornerMin)) gap=minute-lastCornerMin;
  }
  const hist=[];
  const metrics=Array.isArray(state.metricEvents)?state.metricEvents:[];
  const fromMin=Number.isFinite(minute)?Math.max(0,minute-12):0;
  for(let i=metrics.length-1;i>=0 && hist.length<8;i--){
    const pt=metrics[i];
    const m=Number(pt?.minute);
    if(!Number.isFinite(m)||m<fromMin) continue;
    hist.unshift({
      m,
      ap:[pt?.stats?.dangerous?.home??pt?.dangerous?.home??null, pt?.stats?.dangerous?.away??pt?.dangerous?.away??null],
      c:[pt?.stats?.corners?.home??null, pt?.stats?.corners?.away??null],
      xg:[pt?.stats?.xg?.home??null, pt?.stats?.xg?.away??null]
    });
  }
  if(!hist.length && Array.isArray(state.statTimeline)){
    const tl=state.statTimeline;
    for(let i=tl.length-1;i>=0 && hist.length<8;i--){
      const pt=tl[i];
      const m=Number(pt?.minute);
      if(!Number.isFinite(m)||m<fromMin) continue;
      hist.unshift({
        m,
        ap:[pt?.dangerous?.home??null, pt?.dangerous?.away??null],
        c:[pt?.corners?.home??null, pt?.corners?.away??null],
        xg:[pt?.xg?.home??null, pt?.xg?.away??null]
      });
    }
  }
  const goals=(state.matchEvents||[]).filter(e=>/goal|gol/i.test(String(e?.type||e?.event||""))).slice(-4).map(e=>({
    m:e.minute, side:e.side||e.team||null
  }));
  const fb=state.feedback?.stats||null;
  const h2h=state.h2h?.averages||null;
  return {
    schema: "cornerai-skill-feed-2",
    live: !!live,
    match_id: state.fixtureId||null,
    home: state.home||null,
    away: state.away||null,
    league: state.league||state.competition||null,
    minute: state.minute,
    extra: state.extraMinute||0,
    status: state.liveStatus||"inactive",
    score_home: state.score?.home??null,
    score_away: state.score?.away??null,
    corners_home: state.stats?.corners?.home??null,
    corners_away: state.stats?.corners?.away??null,
    attacks_home: state.stats?.attacks?.home??null,
    attacks_away: state.stats?.attacks?.away??null,
    dangerous_home: state.stats?.dangerous?.home??null,
    dangerous_away: state.stats?.dangerous?.away??null,
    shots_on_home: state.stats?.shotsOn?.home??null,
    shots_on_away: state.stats?.shotsOn?.away??null,
    shots_off_home: state.stats?.shotsOff?.home??null,
    shots_off_away: state.stats?.shotsOff?.away??null,
    xg_home: state.stats?.xg?.home??null,
    xg_away: state.stats?.xg?.away??null,
    possession_home: state.stats?.possession?.home??null,
    possession_away: state.stats?.possession?.away??null,
    corner_events: corners,
    last_corner_min: lastCornerMin,
    gap_last_corner: gap,
    recent_goals: goals,
    history_12m: hist,
    cpi_home: cpiH??null,
    cpi_away: cpiA??null,
    mc_hint: pred ? {prob: Number(pred.probability)||0, side: pred.preferredSide||null} : null,
    feedback: fb ? {n:fb.n, hitRate:fb.hitRate, brier:fb.brier, avgPred:fb.avgPred} : null,
    h2h_avg: h2h||null,
    quality: state.quality?.score ?? null,
    integrity: state.integrity?.score ?? null
  };
}

function buildGeminiCompactPayload(){
  if(__geminiCfg?.economy !== false) return buildGeminiMicroPayload();
  const feed = (typeof buildAIFeed==="function") ? buildAIFeed() : state.aiFeed;
  const analyst = (typeof buildAnalystFeed==="function") ? buildAnalystFeed() : state.analyst;
  const am = analyst?.advanced_metrics || {};
  const pred = am.temporal?.prediction_corner_2m || null;
  return {
    schema: "cornerai-gemini-compact-1",
    version: VERSION,
    match: {
      fixtureId: state.fixtureId, home: state.home, away: state.away,
      score: state.score, minute: state.minute, extraMinute: state.extraMinute||0,
      status: state.liveStatus
    },
    stats: {
      corners: pairNum(state.stats?.corners),
      attacks: pairNum(state.stats?.attacks),
      dangerous: pairNum(state.stats?.dangerous),
      shots: pairNum(state.stats?.shots),
      shotsOn: pairNum(state.stats?.shotsOn),
      xg: pairNum(state.stats?.xg),
      possession: pairNum(state.stats?.possession)
    },
    ce: (state.cornerEvents||[]).slice(-8).map(e=>[e.minute,e.side]),
    metrics: {
      CPI: [am.CPI_v2?.home?.cpi??null, am.CPI_v2?.away?.cpi??null],
      dAPPM: am.delta_APPM||null,
      p2: pred
    },
    iq: state.integrity?.score ?? null
  };
}

function buildGeminiPrompt(compact){
  const data = JSON.stringify(compact||{});
  const live = !!(compact && (compact.live===true || (compact.status==="live" && compact.minute!=null) || (compact.match&&compact.match.status==="live") || (compact.min!=null&&compact.st==="live")));
  const system = [
    "Você é a CornerAI v9.3.1-TRADER — inteligência de escanteios ao vivo.",
    "Objetivo: próximo escanteio. Não prever gols/vencedor. Nunca invente dados.",
    "PIPELINE: TimingAgent → Gate 2/3 (G1 Pressão, G2 Conversão, G3 Contexto) → Score 0-100 → Monte Carlo P(canto 2-5min) → Kills → Decisão.",
    "JANELAS: W1 30-48 (pico 43-48) | W2 80-105 (pico 82-88+). Fora → AGUARDA (exceto sequência ≤4min + pressão).",
    "ENTRA só se: janela ok + Score≥78 + MC≥45% + gatilhos≥2/3 + sem kill forte.",
    "Se live=false OU status!=live OU minute ausente/0 sem partida: responda NÃO ENTRA ou AGUARDA com motivo 'sem dados de partida ao vivo'. Não invente placar/times.",
    "FORMATO:",
    "🚨 DECISÃO FINAL: ENTRA|AGUARDA|NÃO ENTRA",
    "⏱️ TIMING: [min'] | Janela:",
    "🎯 LADO: home|away|neutro",
    "📊 GATE: PASS|FAIL · x/3",
    "📈 PRESSÃO: Casa n/100 | Fora n/100",
    "🎲 MC 2-5min: n%",
    "🛡️ KILLS:",
    "💬 JUSTIFICATIVA: 2-4 linhas com números do payload",
    "📋 REG: JSON compacto"
  ].join("\n");
  const flag = live ? "STATUS: PARTIDA AO VIVO — use history_12m, corner_events, gap_last_corner e feedback se presentes. Não invente stats." : "STATUS: SEM PARTIDA AO VIVO — não invente dados.";
  return system+"\n"+flag+"\nDADOS:"+data;
}

function geminiBudgetGate(reason){
  const cfg=__geminiCfg;
  const dk=geminiTodayKey();
  if(cfg.dayKey!==dk){ cfg.dayKey=dk; cfg.dayRuns=0; }
  if(state.fixtureId && cfg.matchId!==String(state.fixtureId)){
    cfg.matchId=String(state.fixtureId);
    cfg.matchRuns=0;
    cfg.lastFingerprint=null;
  }
  if(reason!=="manual"){
    if(Number(cfg.dayRuns||0) >= Number(cfg.maxCallsPerDay||80))
      return {ok:false, error:"budget_day", detail:`${cfg.dayRuns}/${cfg.maxCallsPerDay} calls hoje`};
    if(Number(cfg.matchRuns||0) >= Number(cfg.maxCallsPerMatch||12))
      return {ok:false, error:"budget_match", detail:`${cfg.matchRuns}/${cfg.maxCallsPerMatch} calls nesta partida`};
    if(cfg.onlyCriticalWindows && state.liveStatus==="live" && !inCriticalWindow(state.minute))
      return {ok:false, error:"outside_critical_window", detail:`min ${state.minute}`};
  }
  // fingerprint / delta skip (auto + alert)
  if(reason!=="manual"){
    const fp=buildGeminiFingerprint();
    const ds=deltaScore(cfg.lastFingerprint, fp);
    if(cfg.lastFingerprint && ds < Number(cfg.minDeltaScore||0.12))
      return {ok:false, error:"no_delta", detail:`delta ${ds}`, fingerprint:fp};
  }
  return {ok:true};
}

async function callGeminiAPI(reason="manual"){
  const cfg = __geminiCfg || await loadGeminiConfig();
  const isManual = reason==="manual" || reason==="popup" || reason==="dashboard" || reason==="user";
  if(!cfg.apiKey){ try{state.diagnostics.geminiFallback=true;state.diagnostics.geminiLastError="API key ausente";}catch{} return {ok:false, error:"API key ausente — cole a key e clique Salvar"}; }
  // Auto/alert require "Ativo"; manual/popup always allowed when key exists
  if(!cfg.enabled && !isManual) return {ok:false, error:"Auto-Gemini desabilitado — marque Ativo e Salvar"};

  const now = Date.now();
  // stronger throttle for non-manual only
  const minGap = String(reason).startsWith("alert")
    ? Math.max(60000, Number(cfg.alertMinGapMs||180000))
    : Math.max(45000, Number(cfg.intervalMs||300000)*0.5);
  if(!isManual && cfg.lastRunAt && (now - cfg.lastRunAt) < minGap){
    cfg.skipped = Number(cfg.skipped||0)+1;
    return {ok:false, error:"throttled", throttled:true};
  }

  const gate=geminiBudgetGate(isManual ? "manual" : reason);
  if(!gate.ok){
    cfg.skipped = Number(cfg.skipped||0)+1;
    state.diagnostics.geminiSkipped = cfg.skipped;
    return gate;
  }

  const compact = buildGeminiCompactPayload();
  const prompt = buildGeminiPrompt(compact);
  const preferred = String(cfg.model||"gemini-3.5-flash-lite").replace(/[^\w.\-:/]/g,"");
  const _monStart = Date.now();
  const _monMatch = {home:state.home,away:state.away,score:state.score,minute:state.minute,fixtureId:state.fixtureId};
  skillMonitorPush({
    phase:"request", direction:"out", ok:null, reason,
    model:preferred, fixtureId:state.fixtureId,
    match:_monMatch,
    promptChars:String(prompt||"").length,
    payloadKeys: compact && typeof compact==="object" ? Object.keys(compact).slice(0,30) : [],
    estTokens: estimateTokens(prompt),
    payloadPreview: (()=>{ try{return JSON.stringify(compact).slice(0,400);}catch{return null} })()
  });
  __skillMonitor.totals.requests++;
  __skillMonitor.totals.bytesOut += String(prompt||"").length;

  // Fallback chain for new API keys (2.x often blocked for new users)
  const FALLBACKS = [
    preferred,
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
  ];
  const tried = new Set();
  const models = [];
  for(const m of FALLBACKS){ if(m && !tried.has(m)){ tried.add(m); models.push(m); } }
  const maxTok = Math.min(1024, Number(cfg.maxOutputTokens)||512);
  const bodyBase = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: Number(cfg.temperature)||0.2,
      maxOutputTokens: maxTok
    }
  };

  const inTok = estimateTokens(prompt);
  __geminiCfg.lastRunAt = now;
  __geminiCfg.runs = Number(__geminiCfg.runs||0)+1;
  __geminiCfg.dayRuns = Number(__geminiCfg.dayRuns||0)+1;
  __geminiCfg.matchRuns = Number(__geminiCfg.matchRuns||0)+1;
  __geminiCfg.lastFingerprint = buildGeminiFingerprint();
  __geminiCfg.estInputTokens = Number(__geminiCfg.estInputTokens||0) + inTok;
  state.diagnostics.geminiRuns = __geminiCfg.runs;
  state.diagnostics.geminiDayRuns = __geminiCfg.dayRuns;

  let lastErr = null;
  try{
    for(const model of models){
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(cfg.apiKey)}`;
      let resp, data;
      try{
        resp = await fetch(url, {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify(bodyBase)
        });
        data = await resp.json().catch(()=>({}));
      }catch(e){
        lastErr = e?.message||String(e);
        continue;
      }
      if(!resp.ok){
        const errMsg = data?.error?.message || `HTTP ${resp.status}`;
        lastErr = errMsg;
        // If model unavailable, try next; other errors stop (auth, quota)
        const unavailable = /no longer available|not found|is not found|not supported|NOT_FOUND/i.test(errMsg);
        if(unavailable) continue;
        __geminiCfg.lastError = errMsg;
        __geminiCfg.fails = Number(__geminiCfg.fails||0)+1;
        try{state.diagnostics.geminiFallback=true;state.diagnostics.geminiLastError=String(errMsg).slice(0,200);state.diagnostics.geminiLastAt=Date.now();}catch{}
        await saveGeminiConfig({});
        return {ok:false, error:errMsg, status:resp.status, modelTried:model};
      }
      const text =
        data?.candidates?.[0]?.content?.parts?.map(p=>p.text).filter(Boolean).join("\n") ||
        data?.candidates?.[0]?.content?.parts?.[0]?.text ||
        "";
      if(!text){
        lastErr = "resposta vazia";
        continue;
      }
      // Persist working model if different from preferred
      if(model !== preferred){
        __geminiCfg.model = model;
      }
      const outTok = estimateTokens(text);
      __geminiCfg.estOutputTokens = Number(__geminiCfg.estOutputTokens||0) + outTok;
      __geminiCfg.lastOkAt = Date.now();
      __geminiCfg.lastError = null;
      try{state.diagnostics.geminiFallback=false;state.diagnostics.geminiLastError=null;state.diagnostics.geminiLastAt=Date.now();}catch{}
      await saveGeminiConfig({});

      const result = {
        schema: "cornerai-gemini-result-1",
        at: new Date().toISOString(),
        reason, model,
        fixtureId: state.fixtureId,
        match: {home:state.home,away:state.away,score:state.score,minute:state.minute},
        reply: text,
        usage: {estInputTokens: inTok, estOutputTokens: outTok, economy: cfg.economy!==false, fallback: model!==preferred}
      };
      try{
        const stored = await chrome.storage.local.get(["cornerai_gemini_results"]);
        const arr = Array.isArray(stored.cornerai_gemini_results)?stored.cornerai_gemini_results:[];
        arr.unshift({at:result.at, reason, model, fixtureId:result.fixtureId, reply:text.slice(0,2500), match:result.match, usage:result.usage});
        await chrome.storage.local.set({cornerai_gemini_results: arr.slice(0,20)});
      }catch{}
      state.gemini = publicGeminiStatus();
      state.gemini.lastReplyPreview = text.slice(0,280);

      __skillMonitor.totals.ok++;
      __skillMonitor.totals.bytesIn += String(text||"").length;
      skillMonitorPush({
        phase:"response", direction:"in", ok:true, reason,
        model, fixtureId:state.fixtureId, match:_monMatch,
        latencyMs: Date.now()-_monStart,
        replyChars: String(text||"").length,
        replyPreview: String(text||"").slice(0,320),
        httpStatus: 200,
        promptChars: String(prompt||"").length,
        fallback: model!==preferred
      });

      if(reason==="manual" || reason==="popup" || reason==="dashboard" || String(reason).startsWith("alert")){
        try{ await notifyHeadless("gemini_ok", "Análise Gemini", text.slice(0,140)); }catch{}
      }
      return {ok:true, result};
    }
    const errMsg = lastErr || "nenhum modelo Gemini disponível para esta key";
    __geminiCfg.lastError = errMsg;
    __geminiCfg.fails = Number(__geminiCfg.fails||0)+1;
    __skillMonitor.totals.fail++;
    skillMonitorPush({
      phase:"error", direction:"in", ok:false, reason,
      model:preferred, fixtureId:state.fixtureId, match:_monMatch,
      latencyMs: Date.now()-_monStart,
      error: errMsg, httpStatus:null
    });
    await saveGeminiConfig({});
    return {ok:false, error:errMsg};
  }catch(e){
    const msg = e?.message||String(e);
    __geminiCfg.lastError = msg;
    __geminiCfg.fails = Number(__geminiCfg.fails||0)+1;
    try{await saveGeminiConfig({});}catch{}
    return {ok:false, error:msg};
  }
}


// Heartbeat: reenvia analyst ao bridge a cada 30s em partida live
let __webhookHeartbeat=null;
function scheduleWebhookHeartbeat(){
  try{ if(__webhookHeartbeat) clearInterval(__webhookHeartbeat); }catch{}
  __webhookHeartbeat=null;
  __webhookHeartbeat=setInterval(()=>{
    try{
      if(!PARAMS.webhookEnabled) return;
      if(!state.webhook?.url) return;
      // Always try to drain outbox if there are pending items
      const pending = Array.isArray(state.outbox) ? state.outbox.length : 0;
      if(pending > 0){
        flushAnalystOutbox().catch(()=>{});
      }
      if(state.liveStatus!=="live") return;
      if(!state.fixtureId) return;
      state.analyst=buildAnalystFeed();
      enqueueAnalystOutbox(state.analyst,"heartbeat-15s");
    }catch(e){}
  },15000);
}
scheduleWebhookHeartbeat();

function scheduleGeminiAuto(){
  try{ if(__geminiTimer) clearInterval(__geminiTimer); }catch{}
  __geminiTimer = null;
  if(!__geminiCfg?.enabled || !__geminiCfg?.auto || !__geminiCfg?.apiKey) return;
  const ms = Math.max(60000, Number(__geminiCfg.intervalMs)||60000); // min 60s default
  __geminiTimer = setInterval(()=>{
    try{
      // auto: only live (skip finished to save cost unless manual)
      if(state.liveStatus==="live"){
        callGeminiAPI("auto-interval").catch(()=>{});
      }
    }catch{}
  }, ms);
}

async function maybeGeminiOnAlert(kind){
  try{
    if(!__geminiCfg?.enabled || !__geminiCfg?.apiKey) return;
    if(__geminiCfg.onAlert===false) return;
    if(!/cpi_|corner_pred|favorite_losing/.test(String(kind||""))) return;
    // alerts only in critical windows when economy on
    if(__geminiCfg.onlyCriticalWindows && !inCriticalWindow(state.minute)) return;
    await callGeminiAPI("alert:"+kind);
  }catch{}
}

// --- Headless notifications (throttled) ---
const __notifyState={lastAt:{}, lastAnyAt:0};
function cryptoJitterBg(minMs,maxMs){
  const lo=Math.min(minMs,maxMs),hi=Math.max(minMs,maxMs);
  try{const b=new Uint32Array(1);crypto.getRandomValues(b);return lo+(b[0]/0x100000000)*(hi-lo);}catch{return lo+Math.random()*(hi-lo);}
}
async function notifyHeadless(kind,title,message,opts={}){
  try{
    if(PARAMS.notificationsEnabled===false) return false;
    const now=Date.now();
    const minGap=Number(PARAMS.notifyMinGapMs||45000);
    const perKindGap=Number(PARAMS.notifyPerKindGapMs||90000);
    if(now-__notifyState.lastAnyAt<minGap) return false;
    if(now-(__notifyState.lastAt[kind]||0)<perKindGap) return false;
    __notifyState.lastAt[kind]=now;
    __notifyState.lastAnyAt=now;
    const id=`cornerai-${kind}-${now}`;
    await chrome.notifications.create(id,{
      type:"basic",
      iconUrl: chrome.runtime.getURL("icon128.png"),
      title:String(title||"CornerAI").slice(0,120),
      message:String(message||"").slice(0,250),
      priority: opts.priority!=null?opts.priority:1,
      requireInteraction:!!opts.requireInteraction
    });
    state.diagnostics.notificationsSent=(state.diagnostics.notificationsSent||0)+1;
    return true;
  }catch(e){
    state.diagnostics.notificationErrors=(state.diagnostics.notificationErrors||0)+1;
    return false;
  }
}
// Evaluate alert conditions after analyst rebuilds (called from health path opportunistically)
async function maybeNotifySignals(){
  try{
    if(state.liveStatus!=="live") return;
    const prefs=state.alertPrefs||DEFAULT_ALERT_PREFS;
    if(prefs.enabled===false) return;
    const minute=Number(state.minute);
    if(!Number.isFinite(minute)) return;
    const analyst=state.analyst||{};
    const am=analyst.advanced_metrics||{};
    const cpiH=Number(am.CPI_v2?.home?.cpi);
    const cpiA=Number(am.CPI_v2?.away?.cpi);
    const thr=Number(prefs.cpiThreshold||0.72);
    const fav=analyst.match_context||{};
    if(prefs.favorite_losing && fav.favorite_losing){
      await notifyHeadless("favorite_losing",
        "Favorito em perigo",
        `${state.home||"Home"} ${state.score?.home??0}×${state.score?.away??0} ${state.away||"Away"} · ${minute}' — favorito perdendo (odd abertura ≤2.10)`);
    }
    if(prefs.cpi_high && Number.isFinite(cpiH)&&cpiH>=thr){
      await notifyHeadless("cpi_home",
        "CPI alto · Mandante",
        `${state.home||"Home"} CPI ${cpiH.toFixed(2)} @ ${minute}' — pressão de escanteio elevada`);
    }
    if(prefs.cpi_high && Number.isFinite(cpiA)&&cpiA>=thr){
      await notifyHeadless("cpi_away",
        "CPI alto · Visitante",
        `${state.away||"Away"} CPI ${cpiA.toFixed(2)} @ ${minute}' — pressão de escanteio elevada`);
    }
    const deltaH=Number(am.delta_APPM?.home), deltaA=Number(am.delta_APPM?.away);
    if(prefs.appm_accel && Number.isFinite(deltaH)&&deltaH>1.5){
      await notifyHeadless("appm_home", "Aceleração ofensiva · Casa", `${state.home||"Home"} ΔAPPM ${deltaH.toFixed(2)} @ ${minute}'`);
    }
    if(prefs.appm_accel && Number.isFinite(deltaA)&&deltaA>1.5){
      await notifyHeadless("appm_away", "Aceleração ofensiva · Fora", `${state.away||"Away"} ΔAPPM ${deltaA.toFixed(2)} @ ${minute}'`);
    }
    const pred=am.temporal?.prediction_corner_2m;
    const pThr=(typeof adaptiveAlertThreshold==="function")?adaptiveAlertThreshold():Number(prefs.cornerPredThreshold||0.55);
    if(prefs.corner_prediction && pred && Number(pred.probability)>=pThr){
      let explainTxt="";
      try{
        const ex=explainCornerAlert(pred, (typeof buildAdvancedPredictiveFeatures==="function")?buildAdvancedPredictiveFeatures():null);
        state.lastAlertExplanation=ex;
        explainTxt = ex?.summary ? (" · "+ex.summary.slice(0,120)) : "";
      }catch{}
      await notifyHeadless("corner_pred",
        "Possível escanteio (2 min)",
        `Prob ${(Number(pred.probability)*100).toFixed(0)}% · lado ${pred.preferredSide||"—"} @ ${minute}'${explainTxt}`);
    }
    // archive finished matches opportunistically
    // Drift monitor (CUSUM)
    try{ runCusumDriftCheck(); }catch{}
    // Auto-Gemini on high-value live signals
    try{
      const am=analyst.advanced_metrics||{};
      const pred=am.temporal?.prediction_corner_2m;
      const thr=Number((state.alertPrefs||{}).cornerPredThreshold||0.55);
      if(pred && Number(pred.probability)>=thr) await maybeGeminiOnAlert("corner_pred");
      const cpiH=Number(am.CPI_v2?.home?.cpi), cpiA=Number(am.CPI_v2?.away?.cpi);
      const cthr=Number((state.alertPrefs||{}).cpiThreshold||0.72);
      if(Number.isFinite(cpiH)&&cpiH>=cthr) await maybeGeminiOnAlert("cpi_home");
      else if(Number.isFinite(cpiA)&&cpiA>=cthr) await maybeGeminiOnAlert("cpi_away");
    }catch{}
    try{await archiveFinishedMatchIfNeeded();}catch{}
    try{resolveFeedbackAgainstCorners();}catch{}
    try{reorderOutOfOrderEvents();}catch{}
    // clock regression vs last observed minute
    try{
      const prev=Number(state.capture?.lastObservedMinute);
      const cur=Number(state.minute);
      const reg=detectClockRegression(prev, cur);
      if(reg) reconcileClockRegression(reg);
      if(Number.isFinite(cur)) state.capture.lastObservedMinute=cur;
    }catch{}
    // soft stats precision pass
    try{
      if(state.stats) state.stats=applyPrecisionToStats(state.stats);
    }catch{}
  }catch{}
}
// Wire into existing 3s health watchdog via soft hook
const __prevHealthIntervalHint=true;
setInterval(()=>{ try{ void maybeNotifySignals(); }catch{} }, 8000 + Math.round(cryptoJitterBg(0,2000)));

chrome.action.onClicked.addListener(async(tab)=>{try{if(tab?.id&&/^https:\/\/(?:[^.]+\.)?sokkerpro\.com\//i.test(tab.url||"")){await ensureContentScript(tab.id,tab.url);await chrome.tabs.sendMessage(tab.id,{type:"SHOW_PANEL"});}}catch(e){addError("panel-open: "+e.message)}});

setInterval(()=>{ try{ void pushLocalAITelemetry("interval"); }catch{} }, 4000);


// ================= PILAR 6: FACHADA DO ESTADO MV3 ATIVO =================
// O módulo background-state-manager.js é carregado no início como contrato;
// esta fachada é instalada depois da declaração do estado canônico e delega
// para o outbox/persistência reais do worker.
try {
  self.__AURA_ACTIVE_STATE_ADAPTER = {
    getFullStats: function () {
      return {
        active: true,
        version: VERSION,
        fixtureId: state.fixtureId || null,
        capture: state.capture || {},
        diagnostics: state.diagnostics || {},
        outboxPending: Array.isArray(state.outbox) ? state.outbox.length : 0,
        webhook: state.webhook || {},
        wom: state.wom || {},
        lastUpdate: state.lastUpdate || 0
      };
    },
    getWomState: function () {
      const wom = state.wom || {};
      const ageMs = Date.now() - Number(wom.last_update || state.lastUpdate || 0);
      return Object.assign({}, wom, { stale: !Number.isFinite(ageMs) || ageMs > 30000, ageMs: ageMs });
    },
    getRecentTelemetry: function (count) {
      const limit = Math.max(1, Math.min(Number(count) || 10, 100));
      const source = Array.isArray(state.statTimeline) ? state.statTimeline : [];
      return source.slice(-limit);
    },
    getServices: function () {
      return {
        bridge: Object.assign({ url: "http://127.0.0.1:8080" }, state.webhook || {}),
        engine: { url: "http://127.0.0.1:8765", healthy: !!state.diagnostics?.lastLocalAiOk, lastCheck: state.diagnostics?.lastLocalAiPushAt || 0 },
        voice: { url: "http://127.0.0.1:8099", healthy: false, lastCheck: 0 }
      };
    },
    sendTelemetry: async function (payload) {
      const data = payload && typeof payload === "object" ? payload : {};
      if (data.fixtureId && state.fixtureId && String(data.fixtureId) !== String(state.fixtureId)) {
        return { ok: false, error: "fixture_isolation" };
      }
      if (data.market_stats && typeof data.market_stats === "object") {
        state.wom = Object.assign({}, state.wom || {}, data.market_stats);
      }
      await pushLocalAITelemetry("pillar6-facade");
      return { ok: true, delegated: true, paper_trade: true };
    },
    performCleanup: function () {
      try { compactStateForStorage("pillar6-facade"); } catch (e) { addError("pillar6-cleanup: " + (e?.message || e)); }
      return { active: true, outboxPending: Array.isArray(state.outbox) ? state.outbox.length : 0 };
    }
  };
  console.info("[AURA-State] Pilar 6 integrado ao background.js canônico");
} catch (e) {
  console.warn("[AURA-State] Falha ao instalar fachada do Pilar 6", e);
}
