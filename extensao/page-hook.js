(() => {
if(window.__cornerAIHookV69191)return;window.__cornerAIHookV69191=true;
const MARK="cornerai-page-hook", VERSION="12.6.12";
const aliases={attacks:["attacks","ataques"],dangerous:["dangerous","dangerous_attacks","ataques_perigosos"],shots:["shots","total_shots","finalizacoes","finalizações"],shotsOn:["shots_on","shots_on_target","on_target","chutes_a_gol"],shotsOff:["shots_off","shots_off_target","off_target","chutes_ao_lado"],corners:["corners","escanteios","cantos"],xg:["xg","expected_goals"],fouls:["fouls","faltas"],offsides:["offsides","offside","impedimentos"],yellow:["yellow","yellow_cards","amarelos"],red:["red","red_cards","vermelhos"],subs:["subs","substitutions","substituicoes"],crosses:["crosses","cruzamentos"],saves:["saves","defences","defesas"],passes:["passes","accurate_passes","passes_certos"],passesFailed:["passes_failed","failed_passes","passes_errados"],possession:["possession","posse"]};
const normKey=k=>String(k).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9_]/g,"_");

const oddNum=v=>{const n=Number(String(v??"").replace(",","."));return Number.isFinite(n)&&n>=1.01&&n<=1000?n:null};
const textClean=v=>String(v??"").replace(/\s+/g," ").trim();
const marketTypeFrom=t=>{const s=textClean(t).toLowerCase();if(/escante|corner|canto/.test(s))return"corners";if(/gol|goals|over.*under.*gol|total.*gol/.test(s))return"goals";if(/cart[aã]o|cards|amarelo|vermelho/.test(s))return"cards";if(/chute|finaliza|shot/.test(s))return"shots";if(/falta|fouls/.test(s))return"fouls";if(/impedimento|offside/.test(s))return"offsides";return"other"};
const UI_NOISE_RE=/jogador da partida|melhores desempenhos|classifica[cç][aã]o|ver tabela|oddsao vivo|play with responsibility|fora do jogo|informa[cç][oõ]es do tempo|canais de tv|menor probabilidade|maior probabilidade/i;
const HIST_ODDS_RE=/\b\d{1,3}(?:\+\d{1,2})?['′]\s*(?:\d+(?:[.,]\d+)?[=|]?\s*){2,}/i;
const contaminated=(m,s)=>UI_NOISE_RE.test(`${m} ${s}`)||HIST_ODDS_RE.test(`${m} ${s}`)||((`${m} ${s}`.match(/\d+(?:[.,]\d+)?/g)||[]).length>4)||/(?:\d+[=|]){3,}/.test(`${m} ${s}`);
function oddsFromObject(root){
 const out=[],seen=new Set();
 const push=(o,ctx={})=>{if(!o||typeof o!=="object")return;const odd=oddNum(o.odds??o.odd??o.price??o.quota??o.cotacao??o.decimalOdds??o.decimal_odd);if(odd==null)return;
   const selection=textClean(o.selection??o.outcome??o.outcomeName??o.label??o.name??o.title??ctx.selection??"");
   const market=textClean(o.market??o.marketName??o.market_name??o.betType??o.marketType??ctx.market??"");
   if(contaminated(market,selection))return;
   const line=o.line??o.handicap??o.total??o.threshold??ctx.line??null;
   const bookmaker=textClean(o.bookmaker??o.bookmakerName??o.provider??o.operator??ctx.bookmaker??"");
   const blob=[market,selection,ctx.path||""].join(" ");
   // Do not promote unidentified market/selection objects into valid betting quotes.
   if(!market || !selection || /^mercado não identificado$/i.test(market) || /^seleção não identificada$/i.test(selection))return;
   const type=marketTypeFrom(blob);
   const minute=minuteOf(o)??minuteOf(ctx);
   const extra=extraOf(o)||extraOf(ctx)||0;
   const period=periodOf(o,minute??0,extra);
   const side=sideOf(o,"","");
   const key=`${fid()||"unknown"}|${market}|${selection}|${line??""}|${bookmaker}|${odd}|${minute??""}|${extra}`;
   if(seen.has(key))return;seen.add(key);
   out.push({quoteId:hash(key),fixtureId:fid(),minute,extraMinute:extra,period,market:market||"Mercado não identificado",marketType:type,selection:selection||"Seleção não identificada",line:line==null?null:String(line),bookmaker:bookmaker||"Mercado",odds:odd,impliedProbability:1/odd,source:"hook",timestamp:Number(o.timestamp)||Date.now()});
 };
 function walk(x,depth=0,path="",ctx={}){if(depth>10||x==null||typeof x!=="object")return;if(Array.isArray(x)){for(const z of x.slice(0,1000))walk(z,depth+1,path,ctx);return}
   const local={...ctx};for(const[k,v]of Object.entries(x)){const nk=normKey(k),sv=typeof v==="string"?textClean(v):"";if(/market|mercado|bettype/.test(nk))local.market=sv||local.market;if(/selection|outcome|option/.test(nk))local.selection=sv||local.selection;if(/bookmaker|provider|operator/.test(nk))local.bookmaker=sv||local.bookmaker;if(/line|handicap|total|threshold/.test(nk)&&v!=null&&typeof v!=="object")local.line=v;}
   push(x,local);for(const[k,v]of Object.entries(x)){if(v&&typeof v==="object")walk(v,depth+1,path+"/"+k,local)}
 }
 walk(root);return out;
}

function extractFidFromAny(url){
  try{
    const s=String(url||"");
    let m=s.match(/\/(?:fixture|partida|match|game)\/(\d{5,})/i);
    if(m) return m[1];
    m=s.match(/[?&#](?:fixture|matchId|match_id|gameId)=(\d{5,})/i);
    if(m) return m[1];
    m=s.match(/\/ws\/fixture\/(\d{5,})/i);
    if(m) return m[1];
    return null;
  }catch{return null}
}
const fid=()=>{
  try{
    const fromLoc=extractFidFromAny(location.href);
    if(fromLoc) return fromLoc;
    // SPA: last known fixture from network traffic
    if(window.__corneraiNetFixture) return String(window.__corneraiNetFixture);
    return null;
  }catch{return null}
};
const teamName=v=>typeof v==="string"?v.trim():v&&typeof v==="object"?(v.name||v.title||v.shortName||v.teamName||v.label||"").toString().trim():"";
const pair=v=>{if(!v)return null;if(Array.isArray(v)&&v.length>=2&&[v[0],v[1]].every(x=>Number.isFinite(Number(x))))return{home:Number(v[0]),away:Number(v[1])};if(typeof v!=="object")return null;const h=v.home??v.h??v[0],a=v.away??v.a??v[1];return Number.isFinite(Number(h))&&Number.isFinite(Number(a))?{home:Number(h),away:Number(a)}:null};
const minuteOf=o=>{for(const k of["minute","min","elapsed","elapsedMinute","matchMinute","time"]){const v=o?.[k];if(Number.isFinite(Number(v)))return Number(v);if(typeof v==="string"){const m=v.match(/(\d{1,3})(?:\+(\d{1,2}))?\s*(?:['′]|min)/i);if(m)return Number(m[1])}}return null};
const extraOf=o=>{for(const k of["extraMinute","stoppage","addedTime","extra","additionalTime"]){const n=Number(o?.[k]);if(Number.isFinite(n)&&n>0)return n}return 0};
const periodOf=(o,m,e=0)=>{const s=String(o?.period??o?.half??o?.stage??"").toLowerCase();if(/second|segundo|2nd|2º/.test(s)||s==="2")return 2;if(/first|primeiro|1st|1º/.test(s)||s==="1")return 1;return m>45?2:1};
const sideOf=(o,home,away)=>{let s=String(o?.side??o?.teamSide??o?.team_type??o?.sideName??"").toLowerCase();if(/home|casa|mandante/.test(s))return"home";if(/away|visitante|fora/.test(s))return"away";const t=teamName(o?.teamName??o?.teamObject??o?.team??o?.teamData);if(t&&home&&t.toLowerCase()===home.toLowerCase())return"home";if(t&&away&&t.toLowerCase()===away.toLowerCase())return"away";return null};
const hash=s=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16)};
function eventFrom(o,home,away){
 if(!o||typeof o!=="object")return null;
 const type=String(o.type??o.eventType??o.kind??o.incidentType??o.event_name??o.event??"").toLowerCase();
 const label=String(o.label??o.name??o.description??o.text??"").toLowerCase();
 const blob=type+" "+label;
 const map=[
  ["corner",/corner|escante|canto/],
  ["shot_on",/shot on target|on target|finaliza[cç][aã]o.*alvo|chute.*(?:gol|alvo)/],
  ["shot_off",/shot off target|off target|finaliza[cç][aã]o.*fora|chute.*fora|ao lado/],
  ["goal",/\b(?:goal|gol|score)\b|\b\d{1,2}\s*[-x]\s*\d{1,2}\b/],
  ["yellow",/yellow|amarelo|cart[aã]o amarelo/],
  ["red",/red card|cart[aã]o vermelho|vermelho/],["substitution",/substitut|substitui[cç][aã]o|entra|sai/],
  ["foul",/foul|falta/],["offsides",/offside|impedimento/]
 ];
 const hit=map.find(([,rx])=>rx.test(blob)); if(!hit)return null;
 const minute=minuteOf(o); if(minute==null||minute<0||minute>130)return null;
 const extra=extraOf(o),side=sideOf(o,home,away);if(!side)return null;
 const period=periodOf(o,minute,extra),text=String(o.label??o.description??o.name??o.text??"").replace(/\s+/g," ").trim().slice(0,180);
 const raw=o.eventId??o.event_id??o.uid??o.id;
 const signature=`${fid()||"unknown"}|event|${hit[0]}|${period}|${minute}|${extra}|${side}|${text}`;
 return{eventId:String(raw||hash(signature)),signature,fixtureId:fid(),minute,extraMinute:extra,period,teamName:teamName(o.teamName??o.teamObject??o.team??o.teamData)||(side==="home"?home:away),side,type:hit[0],label:text,confidence:.97,timestamp:Number(o.timestamp)||Date.now()}
}
function extract(data){
 let obj=data;if(typeof obj==="string"){try{obj=JSON.parse(obj)}catch{return null}}
 if(!obj||typeof obj!=="object")return null;
 const currentFid=fid();const ids=new Set();
 (function discoverIds(x,depth=0){if(depth>7||x==null||typeof x!=="object")return;if(Array.isArray(x)){for(const z of x.slice(0,300))discoverIds(z,depth+1);return}for(const[k,v]of Object.entries(x)){const nk=normKey(k);if(/fixture.?id|match.?id|game.?id|partida.?id/.test(nk)&&/^[0-9]{5,}$/.test(String(v)))ids.add(String(v));if(v&&typeof v==="object")discoverIds(v,depth+1)}})(obj);
 if(currentFid&&ids.size&&[...ids].some(x=>x!==String(currentFid)))return null;
 const out={fixtureId:currentFid,url:location.href},events=[],seen=new Set(),extendedStats={},xgCandidates=[];let found=0,home="",away="";
 const isNoiseStatKey=k=>/^(id|fixture|match|game|score|goals?|minute|time|timestamp|odds?|price|quota|probability|probabilities|fair|implied|line|handicap|x|y|width|height|lat|lng|latitude|longitude)$/i.test(k)||/odds|probability|price|quota|handicap|coordinate|position|timestamp/i.test(k);
 const addExtended=(key,pp)=>{const nk=normKey(key);if(!nk||isNoiseStatKey(nk)||extendedStats[nk])return;if(!pp)return;const label=String(key).replace(/[_-]+/g," ").replace(/([a-z])([A-Z])/g,"$1 $2").trim();if(label.length<2||label.length>80)return;extendedStats[nk]={label,home:pp.home,away:pp.away,source:"hook",timestamp:Date.now()};};
 function discoverTeams(x,depth=0){
   if(depth>8||x==null||typeof x!=="object")return;
   if(Array.isArray(x)){for(const z of x.slice(0,500))discoverTeams(z,depth+1);return}
   for(const[k,v]of Object.entries(x)){
     const nk=normKey(k);
     if(["home","hometeam","team_home","home_team","hometeamname","home_team_name"].includes(nk)){const n=teamName(v);if(n&&!home)home=n}
     if(["away","awayteam","team_away","away_team","awayteamname","away_team_name"].includes(nk)){const n=teamName(v);if(n&&!away)away=n}
     if(v&&typeof v==="object")discoverTeams(v,depth+1);
   }
 }
 discoverTeams(obj);
 function walk(x,depth=0,parentKey=""){
   if(depth>9||x==null||typeof x!=="object")return;
   if(Array.isArray(x)){for(const z of x.slice(0,500))walk(z,depth+1,parentKey);return}
   for(const[k,v]of Object.entries(x)){
     const nk=normKey(k);
     for(const[canon,names]of Object.entries(aliases)){
       if(names.includes(nk)){let pp=pair(v);
       if(pp&&canon==="xg"){
         const raw={home:pp.home,away:pp.away};
         // Reject implausible xG rather than silently converting arbitrary
         // percentages/IDs into expected goals. Explicit provider metadata can
         // be handled separately by the DOM extractor.
         if(pp.home>=0&&pp.away>=0&&pp.home<=10&&pp.away<=10){
           xgCandidates.push({pair:pp,score:nk==="xg"?100:92,path:parentKey,raw,method:"network-key"});
         } else { pp=null; }
       }
       if(pp&&canon!=="xg"&&!out[canon]){out[canon]=pp;found++}}
     }
     if(["score","result","goals"].includes(nk)){const pp=pair(v);if(pp)out.score=pp}
     let genericPair=pair(v);
     if(genericPair&&/xg|expected.?goals/i.test(nk)){
       if(genericPair.home>=0&&genericPair.away>=0&&genericPair.home<=10&&genericPair.away<=10)
         xgCandidates.push({pair:genericPair,score:88,path:parentKey,raw:{home:genericPair.home,away:genericPair.away},method:"network-generic"});
       genericPair=null;
     }
     if(genericPair&&!Object.keys(aliases).some(c=>aliases[c].includes(nk))&&!['score','result','goals'].includes(nk))addExtended(k,genericPair);
     if(["minute","elapsed","elapsedtime","matchminute"].includes(nk)){if(typeof v==="string"){const cm=v.match(/^(\d{1,3})(?:\+(\d{1,2}))?$/);if(cm){out.minute=Number(cm[1]);out.extraMinute=Number(cm[2]||0)}}else if(Number.isFinite(Number(v)))out.minute=Number(v);}
     if(v&&typeof v==="object"){
       const ev=eventFrom(v,home,away);
       if(ev&&!seen.has(ev.eventId)){seen.add(ev.eventId);events.push(ev)}
       walk(v,depth+1,nk)
     }
   }
 }
 walk(obj);
 if(home&&away&&home.toLowerCase()!==away.toLowerCase()){out.home=home;out.away=away}
 if(xgCandidates.length){
   xgCandidates.sort((a,b)=>b.score-a.score);
   const x=xgCandidates[0];
   out.xg=x.pair;
   out.xgMeta={home:x.pair.home,away:x.pair.away,source:"hook",confidence:Math.min(1,x.score/100),method:x.method,candidateCount:xgCandidates.length,raw:x.raw};
   found++;
 }
 out.extendedStats=extendedStats;out.matchEvents=events.sort((a,b)=>a.period-b.period||a.minute-b.minute||a.extraMinute-b.extraMinute||a.timestamp-b.timestamp);
 out.cornerEvents=events.filter(e=>e.type==="corner"); out.odds=oddsFromObject(obj); return found||out.score||out.home||out.away||out.matchEvents.length||out.odds.length?out:null
}
function isAllowedNetworkUrl(raw){try{const u=new URL(String(raw||""),location.href);const h=u.hostname.toLowerCase();const p=u.protocol;if(p!=="https:"&&p!=="http:"&&p!=="wss:"&&p!=="ws:")return false;if(h==="sokkerpro.com"||h.endsWith(".sokkerpro.com"))return true;// APIs/CDNs de gráfico + históricos
if(/sokker|fixture|match|stats|chart|graph|live|history|histor|preodds|odds|x7|api/i.test(h))return true;
const path=u.pathname.toLowerCase();
if(/\/(history|histor|fixture|match|stats|preodds|odds|x7|timeline|events|incidents)/i.test(path))return true;
return false}catch{return false}}
function post(payload,endpoint){
  if(!payload||!isAllowedNetworkUrl(endpoint))return;
  payload.__endpoint=endpoint;
  const fromEp=extractFidFromAny(endpoint);
  if(fromEp){ try{window.__corneraiNetFixture=String(fromEp)}catch{} }
  payload.__fixtureId=fid()||fromEp||null;
  payload.__capturedAt=Date.now();
  if(payload.__fixtureId && !payload.fixtureId) payload.fixtureId=String(payload.__fixtureId);
  window.postMessage({source:MARK,type:"NETWORK_PAYLOAD",payload},location.origin)
}
function chartHint(url,text){try{const u=String(url||"");const t=String(text||"");if(t.length<8||t.length>500000)return;const head=(u+" "+t.slice(0,2000)).toLowerCase();
  // Aceita m2 e m4 (gráficos x7/projecao vêm do m4)
  const hostOk=/m[24]\.sokkerpro\.com|sokkerpro\.com\/(api|fixture|live|graph|chart|team)/i.test(u)||/sokkerpro/i.test(u);
  const pathOk=/\/(x7|grafic|projecao|chart|graph|macd|pressure|xg|history|histor|timeline|events|preodds|odds)\b/i.test(u);
  const bodyOk=/chart|graph|macd|pressure|xg|attack|series|dataset|barra|pressao|timeline|performance|points|minute|dangerous|"__m4"|projecao/i.test(head)||/"home"\s*:\s*[\[{]|data\s*:\s*\[/i.test(t.slice(0,500));
  if(!hostOk&&!pathOk&&!bodyOk)return;
  // Guarda também respostas criptografadas (__m4) para diagnóstico / futura decrypt
  window.postMessage({source:MARK,type:"CHART_PAYLOAD",url:u.slice(0,400),sample:t.slice(0,120000),encrypted:/"__m4"\s*:\s*1/.test(t)},location.origin);
}catch{}}
function inspect(text,type,url){if(!text)return;
  // Chart payloads even when host is outside strict stats allowlist
  try{chartHint(url,text)}catch{}
  if(!isAllowedNetworkUrl(url))return;
  const lower=text.toLowerCase();
  const hint=/attack|ataque|corner|escante|canto|shot|chute|xg|possession|posse|foul|falta|fixture|dangerous|yellow|red|stats|statistics|incident|event|chart|graph|macd|pressure|series|dataset/.test(lower);
  if(!String(type||"").includes("json")&&!hint)return;
  const p=extract(text);if(p)post(p,url)
}
const origFetch=window.fetch;window.fetch=async function(...args){const url=typeof args[0]==="string"?args[0]:args[0]?.url||"";const response=await origFetch.apply(this,args);try{if(response&&response.ok!==false&&typeof response.clone==="function"){const copy=response.clone();const type=(copy.headers&&copy.headers.get)?(copy.headers.get("content-type")||""):"";Promise.resolve().then(async()=>{try{const text=await copy.text();inspect(text,type,url)}catch{}}).catch(()=>{})}}catch{}return response};
const oOpen=XMLHttpRequest.prototype.open,oSend=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.open=function(method,url,...rest){this.__cornerAIUrl=String(url||"");return oOpen.call(this,method,url,...rest)};XMLHttpRequest.prototype.send=function(body){this.addEventListener("load",function(){try{inspect(this.responseText,this.getResponseHeader("content-type")||"",this.__cornerAIUrl);chartHint(this.__cornerAIUrl,this.responseText)}catch{}});return oSend.call(this,body)};
// --- Binary WebSocket deserialization cascade + Application-level chunk buffer (v6.0.0 Enterprise) ---
// Pure JS, zero external deps. Tries: UTF-8 JSON → length-prefixed JSON →
// UTF-8 text with JSON island → diagnostic dump. Preserves decimal precision
// by feeding raw text into existing extract()/inspect() path.
// NEW: Multi-frame text chunk reconstruction with balance check + timeout + byte cap.

const WS_META = new WeakMap();
const CHUNK_TIMEOUT_BASE_MS = 20;
const CHUNK_TIMEOUT_MAX_MS = 90;
const CHUNK_MAX_BYTES = 2 * 1024 * 1024; // 2 MiB hard cap
const chunkBuffers = new Map(); // endpoint → { buf, timer, bytes, parts, firstAt }
try{window.__corneraiChunkStats={flushes:0,overflows:0,completes:0,buffered:0};}catch{}
const wsHealth = { opens: 0, closes: 0, lastOpenAt: 0, lastCloseAt: 0, lastMessageAt: 0, endpoints: {} };

function cryptoJitter(minMs, maxMs){
  const lo=Math.min(minMs,maxMs), hi=Math.max(minMs,maxMs);
  try{
    const buf=new Uint32Array(1);
    crypto.getRandomValues(buf);
    return lo + (buf[0] / 0x100000000) * (hi - lo);
  }catch{
    return lo + Math.random() * (hi - lo);
  }
}

function isJsonBalanced(str) {
  let depthObj = 0, depthArr = 0, inString = false, escape = false;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (inString) {
      if (escape) escape = false;
      else if (c === "\\") escape = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') { inString = true; continue; }
    if (c === "{") depthObj++;
    else if (c === "}") depthObj--;
    else if (c === "[") depthArr++;
    else if (c === "]") depthArr--;
    if (depthObj < 0 || depthArr < 0) return false;
  }
  return depthObj === 0 && depthArr === 0 && !inString;
}

function dynamicChunkTimeout(entry){
  // Larger / multi-part buffers get more time; small single fragments stay tight.
  const parts = Math.max(1, Number(entry?.parts || 1));
  const bytes = Math.max(0, Number(entry?.bytes || 0));
  const sizeFactor = Math.min(1, bytes / 64000);
  const partFactor = Math.min(1, (parts - 1) / 8);
  const ms = CHUNK_TIMEOUT_BASE_MS + (CHUNK_TIMEOUT_MAX_MS - CHUNK_TIMEOUT_BASE_MS) * Math.max(sizeFactor, partFactor);
  return Math.round(ms + cryptoJitter(0, 8));
}

function flushChunkBuffer(endpoint, reason) {
  try{if(window.__corneraiChunkStats)window.__corneraiChunkStats.flushes++;}catch{}
  const entry = chunkBuffers.get(endpoint);
  if (!entry) return;
  clearTimeout(entry.timer);
  chunkBuffers.delete(endpoint);
  const raw = entry.buf;
  if (!raw || raw.length === 0) return;

  if (reason === "overflow" || reason === "timeout" || reason === "close") {
    const island = (typeof tryExtractJsonIsland === "function") ? tryExtractJsonIsland(raw) : null;
    if (island) {
      try { inspect(island, "application/json; chunk-" + reason, endpoint); return; } catch {}
    }
    if (raw.length >= 8 && /[{["]|attack|corner|escante|fixture|stats|pressure|xg|odds/i.test(raw)) {
      try { inspect(raw, "text/plain; chunk-" + reason, endpoint); return; } catch {}
    }
    try {
      window.postMessage({
        source: MARK,
        type: "BINARY_WS_UNKNOWN",
        payload: {
          endpoint: String(endpoint || "").slice(0, 300),
          reason: "chunk_" + reason,
          length: raw.length,
          preview: raw.slice(0, 256),
          ts: Date.now()
        }
      }, location.origin);
    } catch {}
    return;
  }

  // reason === "complete"
  try {
    if (!isJsonBalanced(raw)) {
      window.postMessage({
        source: MARK,
        type: "BINARY_WS_UNKNOWN",
        payload: {
          endpoint: String(endpoint || "").slice(0, 300),
          reason: "chunk_unbalanced",
          length: raw.length,
          ts: Date.now()
        }
      }, location.origin);
      return;
    }
    // Feed the reconstructed full message into the existing pipeline
    inspect(raw, "application/json; chunk-reconstructed", endpoint);
  } catch (err) {
    try {
      window.postMessage({
        source: MARK,
        type: "BINARY_WS_UNKNOWN",
        payload: {
          endpoint: String(endpoint || "").slice(0, 300),
          reason: "chunk_parse_error",
          message: String(err && err.message),
          length: raw.length,
          ts: Date.now()
        }
      }, location.origin);
    } catch {}
  }
}

function appendTextChunk(endpoint, chunk) {
  if (typeof chunk !== "string" || !chunk) return;
  wsHealth.lastMessageAt = Date.now();

  const fast = String(chunk).trim();
  if (isJsonBalanced(fast) && (fast[0] === "{" || fast[0] === "[")) {
    inspect(fast, "application/json", endpoint);
    return;
  }

  let entry = chunkBuffers.get(endpoint);
  if (!entry) {
    entry = { buf: "", timer: null, bytes: 0, parts: 0, firstAt: Date.now() };
    chunkBuffers.set(endpoint, entry);
  }

  entry.buf += chunk;
  entry.bytes += chunk.length;
  entry.parts = (entry.parts || 0) + 1;

  if (entry.bytes > CHUNK_MAX_BYTES) {
    flushChunkBuffer(endpoint, "overflow");
    return;
  }

  if (isJsonBalanced(entry.buf) && (entry.buf[0] === "{" || entry.buf[0] === "[")) {
    flushChunkBuffer(endpoint, "complete");
    return;
  }

  // Dynamic timeout: grows with fragment count / size
  if (entry.timer) clearTimeout(entry.timer);
  entry.timer = setTimeout(() => flushChunkBuffer(endpoint, "timeout"), dynamicChunkTimeout(entry));
}

function bytesToHex(u8, max=64){
  const n=Math.min(u8.length, max);
  let s="";
  for(let i=0;i<n;i++) s+=(u8[i]<16?"0":"")+u8[i].toString(16);
  return s+(u8.length>max?"…":"");
}
function tryDecodeUtf8(u8){
  try{return new TextDecoder("utf-8",{fatal:false}).decode(u8)}catch{return null}
}
function tryExtractJsonIsland(text){
  if(!text||typeof text!=="string")return null;
  const t=text.trim();
  if((t[0]==="{"&&t[t.length-1]==="}")||(t[0]==="["&&t[t.length-1]==="]"))return t;
  // Search for first balanced {…} or […] that looks like JSON
  const startObj=t.indexOf("{"), startArr=t.indexOf("[");
  let start=-1, open="{", close="}";
  if(startObj>=0&&(startArr<0||startObj<=startArr)){start=startObj}
  else if(startArr>=0){start=startArr;open="[";close="]"}
  if(start<0)return null;
  let depth=0, inStr=false, esc=false;
  for(let i=start;i<t.length;i++){
    const c=t[i];
    if(inStr){if(esc)esc=false;else if(c==="\\")esc=true;else if(c==='"')inStr=false;continue}
    if(c==='"'){inStr=true;continue}
    if(c===open)depth++;
    else if(c===close){depth--;if(depth===0)return t.slice(start,i+1)}
  }
  return null;
}
function tryLengthPrefixedJson(u8){
  // Common patterns: 4-byte BE/LE length + payload, or 2-byte length
  if(u8.length<6)return null;
  const tryLen=(len,offset)=>{
    if(len<=0||offset+len>u8.length||len>2e6)return null;
    const slice=u8.subarray(offset,offset+len);
    const txt=tryDecodeUtf8(slice);
    if(!txt)return null;
    const island=tryExtractJsonIsland(txt);
    if(island){try{JSON.parse(island);return island}catch{}}
    return null;
  };
  // Big-endian uint32
  const be=((u8[0]<<24)|(u8[1]<<16)|(u8[2]<<8)|u8[3])>>>0;
  let r=tryLen(be,4);if(r)return r;
  // Little-endian uint32
  const le=((u8[3]<<24)|(u8[2]<<16)|(u8[1]<<8)|u8[0])>>>0;
  r=tryLen(le,4);if(r)return r;
  // Big-endian uint16
  const be16=(u8[0]<<8)|u8[1];
  r=tryLen(be16,2);if(r)return r;
  // Little-endian uint16
  const le16=(u8[1]<<8)|u8[0];
  r=tryLen(le16,2);if(r)return r;
  return null;
}
function deserializeBinaryFrame(raw){
  // Returns {text, decodedType, meta} or null
  let u8=null;
  try{
    if(raw instanceof ArrayBuffer) u8=new Uint8Array(raw);
    else if(ArrayBuffer.isView(raw)) u8=new Uint8Array(raw.buffer,raw.byteOffset,raw.byteLength);
    else if(raw instanceof Blob) return null; // handled async by caller
    else return null;
  }catch{return null}
  if(!u8||u8.length===0)return null;

  const meta={byteLength:u8.length,hexHead:bytesToHex(u8,48)};

  // 1) Direct UTF-8 → full text / JSON island
  const utf=tryDecodeUtf8(u8);
  if(utf){
    const island=tryExtractJsonIsland(utf);
    if(island){
      try{JSON.parse(island);return {text:island,decodedType:"utf8-json",meta}}
      catch{}
    }
    // Accept plain text that still looks like telemetry (existing inspect filters)
    if(utf.length>=8&&/[{\["]|attack|corner|escante|fixture|stats|pressure|xg|odds/i.test(utf)){
      return {text:utf,decodedType:"utf8-text",meta};
    }
  }

  // 2) Length-prefixed JSON
  const prefixed=tryLengthPrefixedJson(u8);
  if(prefixed) return {text:prefixed,decodedType:"length-prefixed-json",meta};

  // 3) Diagnostic only (do not drop silently)
  return {text:null,decodedType:"binary-unknown",meta};
}

async function handleWsMessageData(data, endpoint){
  try{
    markActivity();
    if(typeof data==="string"){
      // Application-level chunk reconstruction for fragmented JSON text frames
      appendTextChunk(endpoint, data);
      return;
    }
    // Blob → ArrayBuffer
    if(typeof Blob!=="undefined"&&data instanceof Blob){
      const ab=await data.arrayBuffer();
      data=ab;
    }
    if(data instanceof ArrayBuffer||ArrayBuffer.isView(data)){
      const result=deserializeBinaryFrame(data);
      if(!result)return;
      if(result.text){
        // Feed existing pipeline (extract + post)
        inspect(result.text,"application/json; binary-decoded="+result.decodedType,endpoint);
        // Optional diagnostic side-channel
        try{
          window.postMessage({
            source:MARK,
            type:"BINARY_WS_DECODED",
            payload:{
              endpoint:String(endpoint||"").slice(0,300),
              decodedType:result.decodedType,
              byteLength:result.meta?.byteLength||0,
              hexHead:result.meta?.hexHead||"",
              textPreview:String(result.text).slice(0,400),
              ts:Date.now()
            }
          },location.origin);
        }catch{}
      }else{
        // Unknown binary — still notify for diagnostics / future schema work
        try{
          window.postMessage({
            source:MARK,
            type:"BINARY_WS_UNKNOWN",
            payload:{
              endpoint:String(endpoint||"").slice(0,300),
              decodedType:result.decodedType,
              byteLength:result.meta?.byteLength||0,
              hexHead:result.meta?.hexHead||"",
              ts:Date.now()
            }
          },location.origin);
        }catch{}
      }
    }
  }catch(e){}
}

const NativeWebSocket=window.WebSocket;
const __wsReconnectState={attempts:0,timer:null,lastBootstrapAt:0};
function scheduleReconnectBootstrap(reason){
  try{
    if(__wsReconnectState.timer) clearTimeout(__wsReconnectState.timer);
    const attempt=Math.min(8, (__wsReconnectState.attempts||0)+1);
    __wsReconnectState.attempts=attempt;
    // Exponential backoff with crypto jitter: ~0.8s → ~20s
    const base=Math.min(20000, Math.round(800 * Math.pow(1.7, attempt-1)));
    const delay=Math.round(base + cryptoJitter(0, base*0.35));
    __wsReconnectState.timer=setTimeout(()=>{
      try{
        const now=Date.now();
        if(now-__wsReconnectState.lastBootstrapAt<1500) return;
        __wsReconnectState.lastBootstrapAt=now;
        historicalBootstrap("ws-reconnect:"+reason+":a"+attempt);
        scanSiteStorage("ws-reconnect");
        window.postMessage({
          source:MARK,
          type:"WS_RECONNECT_BOOTSTRAP",
          payload:{attempt,delay,reason:String(reason||""),ts:now,version:VERSION}
        },location.origin);
      }catch{}
    }, delay);
  }catch{}
}
try{
  window.WebSocket=function(...args){
    const ws=new NativeWebSocket(...args);
    const endpoint=String(args[0]||"websocket");
    const meta={endpoint, open:false, sequence:0, created:Date.now()};
    WS_META.set(ws, meta);

    ws.addEventListener("message",ev=>{
      try{
        meta.sequence++;
        wsHealth.lastMessageAt=Date.now();
        handleWsMessageData(ev.data,endpoint);
      }catch{}
    });
    // Also surface open/close for pipeline health
    ws.addEventListener("open",()=>{
      try{
        meta.open=true;
        markActivity();
        wsHealth.opens++;
        wsHealth.lastOpenAt=Date.now();
        wsHealth.endpoints[endpoint.slice(0,120)]={open:true,at:Date.now()};
        // Successful open resets backoff
        __wsReconnectState.attempts=0;
        if(__wsReconnectState.timer){clearTimeout(__wsReconnectState.timer);__wsReconnectState.timer=null;}
        window.postMessage({source:MARK,type:"WS_OPEN",payload:{endpoint:endpoint.slice(0,300),ts:Date.now()}},location.origin);
      }catch{}
    });
    ws.addEventListener("close",(ev)=>{
      try{
        meta.open=false;
        wsHealth.closes++;
        wsHealth.lastCloseAt=Date.now();
        wsHealth.endpoints[endpoint.slice(0,120)]={open:false,code:ev.code,at:Date.now()};
        // Flush any pending chunk buffer on close
        if(chunkBuffers.has(endpoint)) flushChunkBuffer(endpoint, "close");
        window.postMessage({source:MARK,type:"WS_CLOSE",payload:{
          endpoint:endpoint.slice(0,300),
          code:ev.code,
          reason:String(ev.reason||""),
          wasClean:!!ev.wasClean,
          ts:Date.now()
        }},location.origin);
        // Non-clean closes during live pages → REST bootstrap with jittered backoff
        if(!ev.wasClean || (ev.code && ev.code!==1000 && ev.code!==1001)){
          scheduleReconnectBootstrap("close:"+ev.code);
        }
      }catch{}
    });
    ws.addEventListener("error",()=>{
      try{
        window.postMessage({source:MARK,type:"WS_ERROR",payload:{endpoint:endpoint.slice(0,300),ts:Date.now()}},location.origin);
        scheduleReconnectBootstrap("error");
      }catch{}
    });
    return ws;
  };
  window.WebSocket.prototype=NativeWebSocket.prototype;
  window.WebSocket.CONNECTING=0;
  window.WebSocket.OPEN=1;
  window.WebSocket.CLOSING=2;
  window.WebSocket.CLOSED=3;
}catch{}
try{const NativeES=window.EventSource;window.EventSource=function(...args){const es=new NativeES(...args);es.addEventListener("message",ev=>{try{if(ev.data)inspect(ev.data,"application/json",String(args[0]||"eventsource"))}catch{}});return es};window.EventSource.prototype=NativeES.prototype}catch{}

// --- Chart.js / canvas series scraper (page world) ---
function readChartJsSeries(){
  const series=[];
  const push=(p)=>{if(p&&Number.isFinite(p.value)||Number.isFinite(p.home)||Number.isFinite(p.away)) series.push(p)};
  // Chart.js if present
  let chartApi=null;
  try{chartApi=window.Chart||window.ChartJS||null;}catch{}
  for(const c of document.querySelectorAll("canvas#line-chart, canvas[class*='chart'], canvas[id*='chart'], .chart-container canvas, .macd-wrapper canvas")){
    let ch=null;
    try{if(chartApi&&typeof chartApi.getChart==="function") ch=chartApi.getChart(c);}catch{}
    if(!ch) try{ch=c.__chartjs__||c.chart||c._chart||null;}catch{}
    // Alguns builds guardam a instância no parent Vue
    if(!ch) try{const p=c.parentElement;ch=p&&(p.__chart||p.chart)||null;}catch{}
    if(!ch||!ch.data) continue;
    const labels=ch.data.labels||[];
    (ch.data.datasets||[]).forEach((d,di)=>{
      const name=String(d.label||d.yAxisID||("dataset-"+di));
      (d.data||[]).forEach((v,i)=>{
        let minute,value,home,away;
        if(v!=null&&typeof v==="object"){
          minute=Number(v.x??v.minute??v.t??labels[i]);
          value=Number(v.y??v.value??v.v);
          home=Number(v.home??v.h);
          away=Number(v.away??v.a);
        } else {
          minute=Number(labels[i]??i);
          value=Number(v);
        }
        if(Number.isFinite(value)) push({minute:Number.isFinite(minute)?minute:i,value,series:name,src:"chartjs-page"});
        else if(Number.isFinite(home)||Number.isFinite(away)) push({minute:Number.isFinite(minute)?minute:i,home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null,series:name,src:"chartjs-page"});
      });
    });
  }
  // Vue 3/2 internals + elementos com __vueParentComponent
  try{
    const roots=[];
    const appEl=document.querySelector("#app");
    if(appEl&&appEl.__vue_app__){
      try{roots.push(appEl.__vue_app__._instance);}catch{}
      try{if(appEl.__vue_app__._instance?.subTree) roots.push(appEl.__vue_app__._instance.subTree);}catch{}
    }
    if(appEl&&appEl._vnode) roots.push(appEl);
    if(appEl&&appEl.__vue__) roots.push(appEl.__vue__);
    try{
      document.querySelectorAll(".macd-wrapper, .chart-container, .slide, canvas, svg, [class*='chart']").forEach(el=>{
        if(el.__vueParentComponent) roots.push(el.__vueParentComponent);
        if(el.__vue__) roots.push(el.__vue__);
      });
    }catch{}
    const seen=new Set();
    const walkVue=(node,depth)=>{
      if(!node||depth>16) return;
      const raw=node.ctx||node.proxy||node.$data||node.setupState||node.data||node.props||node;
      if(!raw||typeof raw!=="object") return;
      if(seen.has(raw)) return; seen.add(raw);
      try{
        for(const [k,v] of Object.entries(raw).slice(0,80)){
          if(!v) continue;
          const nk=String(k).toLowerCase();
          if(Array.isArray(v)&&v.length>=2&&v.length<=300){
            if(typeof v[0]==="number"){
              v.forEach((val,i)=>{if(Number.isFinite(val)) push({minute:i,value:Number(val),series:k,src:"vue-array"})});
            } else if(v[0]&&typeof v[0]==="object"){
              for(const p of v){
                if(!p||typeof p!=="object") continue;
                const minute=Number(p.minute??p.m??p.x??p.time??p.t??p.period);
                const value=Number(p.value??p.y??p.v??p.xg??p.pressure??p.attacks??p.macd??p.signal??p.hist);
                const home=Number(p.home??p.h??p.homeValue); const away=Number(p.away??p.a??p.awayValue);
                if(Number.isFinite(minute)&&minute>=0&&minute<=130){
                  if(Number.isFinite(value)) push({minute,value,series:k,src:"vue-obj"});
                  else if(Number.isFinite(home)||Number.isFinite(away)) push({minute,home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null,series:k,src:"vue-obj"});
                }
              }
            }
          }
          if(/chart|series|macd|pressure|xg|attack|dataset|timeline|performance|grafico|graph|points|values|dados/i.test(nk)&&typeof v==="object") walkVue({proxy:v},depth+1);
        }
      }catch{}
      try{
        const sub=node.subTree||node.$children||node.children||node.component;
        if(Array.isArray(sub)) sub.slice(0,40).forEach(c=>walkVue(c.component||c,depth+1));
        else if(sub&&typeof sub==="object") walkVue(sub.component||sub,depth+1);
      }catch{}
    };
    roots.forEach(r=>walkVue(r,0));
  }catch{}

  // SVG polylines/paths (quando o gráfico não usa Chart.js)
  try{
    const svgs=document.querySelectorAll(".macd-wrapper svg, .chart-container svg, .slide svg, svg.line-chart, svg[class*='chart'], svg");
    for(const svg of [...svgs].slice(0,12)){
      const vb=(svg.viewBox&&svg.viewBox.baseVal)||{width:0,height:0};
      const w=vb.width||svg.clientWidth||0, h=vb.height||svg.clientHeight||0;
      if(w<20||h<20) continue;
      [...svg.querySelectorAll("polyline, polygon")].forEach((pl,pi)=>{
        const pts=(pl.getAttribute("points")||"").trim().split(/[\s,]+/).map(Number).filter(Number.isFinite);
        for(let i=0;i+1<pts.length;i+=2){
          const x=pts[i], y=pts[i+1];
          const minute=Math.round((x/Math.max(w,1))*90);
          const value=Number(((h-y)/Math.max(h,1)).toFixed(4));
          if(minute>=0&&minute<=130&&Number.isFinite(value)) push({minute,value,series:"svg-poly-"+pi,src:"svg-poly"});
        }
      });
      [...svg.querySelectorAll("path")].slice(0,10).forEach((path,pi)=>{
        const d=path.getAttribute("d")||"";
        if(!/^[\sMmLlHhVv0-9.,Zz-]+$/.test(d)||d.length>5000) return;
        const nums=d.match(/-?\d*\.?\d+/g)?.map(Number)||[];
        for(let i=0;i+1<nums.length;i+=2){
          const x=nums[i], y=nums[i+1];
          if(!Number.isFinite(x)||!Number.isFinite(y)) continue;
          const minute=x>=0&&x<=130?Math.round(x):Math.round((x/Math.max(w,1))*90);
          if(minute<0||minute>130) continue;
          const value=y>=-5&&y<=20?Number(y):Number(((h-y)/Math.max(h,1)).toFixed(4));
          if(Number.isFinite(value)) push({minute,value,series:"svg-path-"+pi,src:"svg-path"});
        }
      });
    }
  }catch{}

  return series.slice(0,1200);
}

function readPressureFromDom(){
  const bars={};
  for(const block of document.querySelectorAll(".pressure-block")){
    const interval=(block.querySelector(".pressure-interval")?.textContent||"").replace(/\s+/g," ").trim();
    const m=interval.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
    if(!m) continue;
    const key=m[1]+"-"+m[2];
    const readGrow=el=>{
      if(!el) return null;
      const d=Number(el.style.flexGrow);
      if(Number.isFinite(d)&&d>0) return d;
      const st=el.getAttribute("style")||"";
      const gm=st.match(/flex-grow\s*:\s*([\d.]+)/i);
      return gm?Number(gm[1]):null;
    };
    const home=readGrow(block.querySelector(".seg-green,.pressure-seg.seg-green"));
    const away=readGrow(block.querySelector(".seg-red,.pressure-seg.seg-red"));
    const pctTxt=(block.querySelector(".pressure-pct")?.textContent||"").trim();
    const pct=pctTxt==="-"?null:Number(String(pctTxt).replace("%","").replace(",","."));
    const noGrow=(home==null||home===0)&&(away==null||away===0);
    const oneSided=(home==null||home===0)^(away==null||away===0);
    // empty DOM / dash
    if(block.querySelector(".pressure-bar-empty")||pctTxt==="-")
      bars[key]={home:null,away:null,empty:true};
    // residual unilateral sem pct confiável
    else if(noGrow||(oneSided&&!Number.isFinite(pct)))
      bars[key]={home:null,away:null,empty:true};
    // unilateral com pct oficial → só pct (evita 72×0 via flex)
    else if(oneSided&&Number.isFinite(pct))
      bars[key]={home:null,away:null,pct,empty:false};
    else bars[key]={home,away,pct:Number.isFinite(pct)?pct:null,empty:false};
  }
  return bars;
}

function detectActiveChartTab(){
  // Seletores amplos usados pelo SokkerPRO (PT + EN)
  const selectors=[
    ".slide-navigation .slide-btn",
    "button.slide-btn",
    ".charts-tabs button",
    ".chart-tabs button",
    "[class*='chart'] button",
    "[class*='slide'] button",
    ".tabs button",
    "[role='tab']"
  ];
  const btns=[...document.querySelectorAll(selectors.join(","))];
  for(const b of btns){
    const label=(b.textContent||"").replace(/\s+/g," ").trim();
    if(!label||label.length>40) continue;
    const st=String(b.getAttribute("style")||"");
    const cls=String(b.className||"");
    const active=/will-change/i.test(st)||/\bactive\b|\bselected\b|\bcurrent\b/i.test(cls)||b.getAttribute("aria-selected")==="true";
    if(active) return label;
  }
  // Fallback por presença de componentes conhecidos
  if(document.querySelector(".pressure-grid .pressure-block, .pressure-block, [class*='pressure']")) return "BARRA DE PRESSÃO";
  if(document.querySelector(".macd-wrapper, [class*='macd']")) return "MACD XG";
  if(document.querySelector("[class*='xg'], [class*='expected']")) return "XG";
  if(document.querySelector("canvas#line-chart, canvas[class*='chart']")) return "GRÁFICO";
  return null;
}

function emitChartSnapshot(reason){
  try{
    const series=readChartJsSeries();
    const pressureBars=readPressureFromDom();
    const fid=fid();
    const activeLabel=detectActiveChartTab();
    if(!series.length&&!Object.keys(pressureBars).length) return;
    // Build a JSON sample compatible with content parseChartNetworkSample + direct fields
    const payload={
      reason:reason||"scrape",
      activeLabel,
      series,
      pressureBars,
      seriesCount:series.length,
      pressureIntervals:Object.keys(pressureBars).length,
      fixtureId:chartFixtureId||null,
      at:Date.now()
    };
    const origin=location.origin;
    const sample=JSON.stringify(payload);
    window.postMessage({source:MARK,type:"CHART_PAYLOAD",url:"page-scrape://charts",sample},origin);
    // CHART_SERIES is the low-cost direct channel consumed by charts-unified.
    window.postMessage({source:MARK,type:"CHART_SERIES",payload:{...payload,url:"page-scrape://charts"}},origin);
  }catch(e){}
}

// Periodic + mutation-driven scrape (passive, no clicks)
let __chartScrapeTimer=0;
function scheduleChartScrape(reason){
  clearTimeout(__chartScrapeTimer);
  __chartScrapeTimer=setTimeout(()=>emitChartSnapshot(reason),180);
}
try{
  let __moPending=false;
  let __chartObserverTarget=null;
  let __chartObserverRebindTimer=0;
  let __chartObserverBootTimer=0;

  const __findChartObserverTarget=()=>{
    const selectors=['.macd-wrapper','.pressure-grid','#line-chart','canvas#line-chart','[class*="chart"]','[class*="macd"]','[class*="pressure"]'];
    for(const sel of selectors){
      const el=document.querySelector(sel);
      if(!el) continue;
      if(el.closest?.('[data-cornerai-ignore="1"], #cornerai-always-visible-host')) continue;
      return el.tagName==='CANVAS' ? (el.parentElement||el) : el;
    }
    return null;
  };
  const __ownSubtree=(mutations)=>{
    for(const m of mutations){
      const nodes=[m.target,...(m.addedNodes||[]),...(m.removedNodes||[])];
      for(const n of nodes){
        const el=n&&n.nodeType===1?n:(n&&n.parentElement);
        if(el&&el.closest&&(el.closest('[data-cornerai-ignore="1"]')||el.closest('#cornerai-always-visible-host'))) return true;
      }
    }
    return false;
  };
  const mo=new MutationObserver((mutations)=>{
    try{ window.__corneraiPageDiag=(window.__corneraiPageDiag||{}); window.__corneraiPageDiag.chartMutations=Number(window.__corneraiPageDiag.chartMutations||0)+mutations.length; }catch{}
    if(__ownSubtree(mutations)||__moPending) return;
    __moPending=true;
    setTimeout(()=>{__moPending=false;scheduleChartScrape("mutation");},1800);
  });
  const __bindChartObserver=()=>{
    const target=__findChartObserverTarget();
    if(!target || target===__chartObserverTarget) return !!target;
    try{mo.disconnect();}catch{}
    __chartObserverTarget=target;
    mo.observe(target,{childList:true,subtree:true,attributes:false,characterData:false});
    return true;
  };
  __bindChartObserver();
  __chartObserverBootTimer=setTimeout(__bindChartObserver,1200);
  __chartObserverRebindTimer=setInterval(__bindChartObserver,5000);
}catch{}
// Scraping periódico (mais útil na aba de gráficos)
setInterval(()=>{
  const chartRoot=document.querySelector(".macd-wrapper, .pressure-grid, canvas#line-chart, .chart-container, .standard-chart-container, [class*='macd'], [class*='pressure']");
  const visible=!!(chartRoot && (chartRoot.offsetParent!==null || chartRoot.getClientRects?.().length));
  if(visible) emitChartSnapshot("interval-charts");
}, 5000);
setTimeout(()=>{ try{ if(document.querySelector(".macd-wrapper,.pressure-grid,#line-chart,.chart-container")) emitChartSnapshot("boot"); }catch{} },1200);
document.addEventListener("click",e=>{
  const t=e.target&&e.target.closest&&e.target.closest(".slide-btn, button, [role='tab'], [class*='chart'], [class*='slide']");
  if(t) scheduleChartScrape("tab-click");
},true);
// Também reage a troca de hash/rota (SPA)
try{
  const _ps=history.pushState,_rs=history.replaceState;
  history.pushState=function(){_ps.apply(this,arguments);scheduleChartScrape("route");};
  history.replaceState=function(){_rs.apply(this,arguments);scheduleChartScrape("route");};
  window.addEventListener("popstate",()=>scheduleChartScrape("popstate"));
}catch{}

// --- Historical API bootstrap (v6.1.0) ---
// Forces same-origin / m2 / m4 fixture feeds so L0 intercept captures preodds, x7,
// events, stats, timeline, form, h2h and projections even when the user lands mid-match or on FT pages.
const __histFetched=new Set();
let __histBootAt=0;
function historicalBootstrap(reason){
  try{
    const id=fid();
    if(!id)return;
    const now=Date.now();
    if(now-__histBootAt<15000 && reason!=="ws-reconnect")return;
    __histBootAt=now;
    const paths=[
      `/fixture/${id}/preodds`,
      `/fixture/${id}/x7`,
      `/fixture/${id}/events`,
      `/fixture/${id}/stats`,
      `/fixture/${id}/timeline`,
      `/fixture/${id}/incidents`,
      `/fixture/${id}/history`,
      `/fixture/${id}/grafic`,
      `/fixture/${id}/projecao`,
      `/fixture/${id}`,
      `/api/fixture/${id}/preodds`,
      `/api/fixture/${id}/x7`,
      `/api/fixture/${id}/events`,
      `/api/fixture/${id}/stats`,
      `/api/fixture/${id}/timeline`,
      `/api/fixture/${id}/incidents`,
    ];
    const hosts=[
      location.origin,
      "https://m4.sokkerpro.com",
    ];
    const urls=[];
    for(const h of hosts){
      for(const path of paths){
        try{urls.push(new URL(path,h).href)}catch{}
      }
    }
    // Team-level context when we can resolve team ids from page state
    try{
      const teamIds=[];
      const scan=(obj,depth=0)=>{
        if(!obj||typeof obj!=="object"||depth>4)return;
        if(Array.isArray(obj)){obj.slice(0,30).forEach(z=>scan(z,depth+1));return;}
        for(const[k,v] of Object.entries(obj)){
          const nk=String(k).toLowerCase();
          if(/(home|away)?team.?id|teamid/.test(nk)&&/^[0-9]{3,}$/.test(String(v))) teamIds.push(String(v));
          if(v&&typeof v==="object") scan(v,depth+1);
        }
      };
      // Best-effort from window globals / Vue / React state
      try{scan(window.__NUXT__||window.__INITIAL_STATE__||window.__PRELOADED_STATE__||null)}catch{}
      const uniqueTeams=[...new Set(teamIds)].slice(0,4);
      for(const tid of uniqueTeams){
        for(const h of hosts){
          for(const p of [`/team/${tid}/form`,`/api/team/${tid}/form`,`/team/${tid}/stats`,`/api/team/${tid}/stats`]){
            try{urls.push(new URL(p,h).href)}catch{}
          }
        }
      }
      if(uniqueTeams.length>=2){
        const [a,b]=uniqueTeams;
        for(const h of hosts){
          for(const p of [`/h2h/${a}/${b}`,`/api/h2h/${a}/${b}`,`/fixture/h2h/${a}/${b}`]){
            try{urls.push(new URL(p,h).href)}catch{}
          }
        }
      }
    }catch{}
    let launched=0;
    for(const url of urls){
      if(__histFetched.has(url))continue;
      __histFetched.add(url);
      launched++;
      Promise.resolve()
        .then(()=>fetch(url,{credentials:"include",cache:"no-store",headers:{"Accept":"application/json, text/plain, */*"}}))
        .then(r=>r)
        .catch(()=>{});
    }
    if(launched){
      try{
        window.postMessage({
          source:MARK,
          type:"HISTORICAL_BOOTSTRAP",
          payload:{fixtureId:id,reason:reason||"boot",launched,version:VERSION,ts:Date.now()}
        },location.origin);
      }catch{}
    }
  }catch{}
}
setTimeout(()=>historicalBootstrap("boot"),900);
setTimeout(()=>historicalBootstrap("retry"),3500);
setTimeout(()=>historicalBootstrap("late"),9000);
try{
  const _ps2=history.pushState,_rs2=history.replaceState;
  history.pushState=function(){_ps2.apply(this,arguments);setTimeout(()=>historicalBootstrap("pushState"),600)};
  history.replaceState=function(){_rs2.apply(this,arguments);setTimeout(()=>historicalBootstrap("replaceState"),600)};
  window.addEventListener("popstate",()=>setTimeout(()=>historicalBootstrap("popstate"),600));
}catch{}

// --- Site storage scanner (v6.1.0) ---
// Reads localStorage / sessionStorage keys that look like match/stats/odds state
// and forwards them for enrichment (non-destructive, read-only).
const SITE_STORAGE_KEYS_RE=/match|fixture|stats|live|odds|preodds|x7|events|timeline|pressure|xg|attack|corner|escante|h2h|form|team|chart|graf|serie|possession|posse/i;
const __storageScanned=new Set();
function scanSiteStorage(reason){
  try{
    const buckets=[
      {name:"localStorage",store:window.localStorage},
      {name:"sessionStorage",store:window.sessionStorage}
    ];
    const found=[];
    for(const b of buckets){
      if(!b.store)continue;
      let keys=[];
      try{keys=Object.keys(b.store)}catch{continue;}
      for(const key of keys){
        if(!SITE_STORAGE_KEYS_RE.test(key))continue;
        const sig=`${b.name}:${key}`;
        if(__storageScanned.has(sig))continue;
        let raw=null;
        try{raw=b.store.getItem(key)}catch{continue;}
        if(raw==null||raw.length<8||raw.length>800000)continue;
        // Prefer JSON-looking payloads
        const trimmed=String(raw).trim();
        if(!(trimmed.startsWith("{")||trimmed.startsWith("[")))continue;
        __storageScanned.add(sig);
        found.push({bucket:b.name,key,length:raw.length,preview:trimmed.slice(0,120)});
        try{
          // Feed into the same inspect pipeline used by fetch/WS
          inspect(raw,"application/json",`site-storage://${b.name}/${encodeURIComponent(key)}`);
        }catch{}
      }
    }
    if(found.length){
      try{
        window.postMessage({
          source:MARK,
          type:"SITE_STORAGE_SCAN",
          payload:{reason:reason||"boot",count:found.length,keys:found.slice(0,40),ts:Date.now(),version:VERSION}
        },location.origin);
      }catch{}
    }
  }catch{}
}
setTimeout(()=>scanSiteStorage("boot"),1400);
setTimeout(()=>scanSiteStorage("retry"),5000);
setInterval(()=>scanSiteStorage("interval"),45000);

// --- MAXIMIZE: strong heartbeat so "SEM SINAL RECENTE" is rare ---
let __lastActivityAt = Date.now();
let __heartbeatSeq = 0;
function emitHeartbeat(reason){
  try{
    __heartbeatSeq++;
    window.postMessage({
      source: MARK,
      type: "HOOK_HEARTBEAT",
      payload: {
        version: VERSION,
        url: location.href,
        seq: __heartbeatSeq,
        reason: reason || "tick",
        lastActivityAt: __lastActivityAt,
        ts: Date.now()
      }
    }, location.origin);
  }catch(e){}
}
function markActivity(){ __lastActivityAt = Date.now(); }

// Periodic heartbeat (content.js can accelerate in critical windows)
setInterval(()=>emitHeartbeat("interval"), 4000);
document.addEventListener("visibilitychange", ()=>{ if(!document.hidden) emitHeartbeat("visible"); });


// --- PAGE ERROR / LONG TASK / RESOURCE TELEMETRY (v6.9.9.96) ---
try{
  const __pd=window.__corneraiPageDiag=window.__corneraiPageDiag||{startedAt:Date.now(),errors:[],rejections:[],network:[],longTasks:[],resourceErrors:[],ws:[],chartMutations:0};
  const ring=(arr,v,max=60)=>{arr.push(v);if(arr.length>max)arr.splice(0,arr.length-max)};
  const emitDiag=(type,payload)=>{try{window.postMessage({source:MARK,type,payload:{...payload,ts:Date.now(),version:VERSION}},location.origin)}catch{}};
  window.addEventListener("error",(e)=>{
    const target=e?.target;
    const tag=String(target?.tagName||"").toUpperCase();
    const resourceTarget=target&&target!==window&&(tag==="SCRIPT"||tag==="LINK"||tag==="IMG"||tag==="VIDEO"||tag==="AUDIO"||tag==="SOURCE");
    const v={message:String(e.message||"resource error").slice(0,400),source:String(e.filename||target?.src||target?.href||"").slice(0,300),lineno:e.lineno||null,colno:e.colno||null,stack:String(e.error?.stack||"").slice(0,700),resource:resourceTarget,tag:resourceTarget?tag:null};
    if(resourceTarget){ ring(__pd.resourceErrors,v); emitDiag("PAGE_RESOURCE_ERROR",{tag,url:v.source,message:v.message}); return; }
    ring(__pd.errors,v); emitDiag("PAGE_ERROR",v);
  },true);
  window.addEventListener("unhandledrejection",(e)=>{const r=e.reason;const v={message:String(r?.message||r||"").slice(0,400),stack:String(r?.stack||"").slice(0,700)};ring(__pd.rejections,v);emitDiag("PAGE_REJECTION",v)});
  const po=new PerformanceObserver(list=>{for(const e of list.getEntries()){if(e.duration>80){const v={duration:Math.round(e.duration),start:Math.round(e.startTime)};ring(__pd.longTasks,v);if(e.duration>120)emitDiag("PAGE_LONG_TASK",v)}}});
  po.observe({entryTypes:["longtask"]});
  window.addEventListener("error",e=>{const t=e.target;if(t&&t!==window&&(t.tagName==="SCRIPT"||t.tagName==="LINK"||t.tagName==="IMG"||t.tagName==="VIDEO")){const v={tag:t.tagName,url:String(t.src||t.href||"").slice(0,400)};ring(__pd.resourceErrors,v);emitDiag("PAGE_RESOURCE_ERROR",v)}},true);
  const NativeWS=window.WebSocket;
  if(NativeWS&&!NativeWS.__corneraiDiagWrapped){
    const W=function(...args){const ws=new NativeWS(...args);const meta={url:String(args[0]||"").slice(0,500),openedAt:Date.now()};ws.addEventListener("open",()=>{meta.openedAt=Date.now();ring(__pd.ws,{...meta,event:"open"});emitDiag("PAGE_WS",{...meta,event:"open"})});ws.addEventListener("error",()=>{ring(__pd.ws,{...meta,event:"error"});emitDiag("PAGE_WS",{...meta,event:"error"})});ws.addEventListener("close",e=>{const v={...meta,event:"close",code:e.code,reason:String(e.reason||"").slice(0,200),durationMs:Date.now()-meta.openedAt};ring(__pd.ws,v);emitDiag("PAGE_WS",v)});return ws};
    W.prototype=NativeWS.prototype; W.CONNECTING=0;W.OPEN=1;W.CLOSING=2;W.CLOSED=3; W.__corneraiDiagWrapped=true; window.WebSocket=W;
  }
}catch{}
try{
  const Vue=window.Vue||window.__VUE__;
  if(Vue?.config){
    const prev=Vue.config.errorHandler;
    Vue.config.errorHandler=function(err,vm,info){
      try{
        window.postMessage({
          source:MARK,type:"PAGE_VUE_ERROR",
          payload:{message:String(err?.message||err).slice(0,300),info:String(info||"").slice(0,200),ts:Date.now()}
        },location.origin);
      }catch{}
      if(typeof prev==="function") try{prev(err,vm,info);}catch{}
    };
  }
}catch{}

window.postMessage({source:MARK,type:"HOOK_READY",payload:{version:VERSION,url:location.href}} ,location.origin);
setTimeout(()=>emitHeartbeat("boot"), 400);
})();
