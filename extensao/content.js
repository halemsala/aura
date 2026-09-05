(() => {
if(window.__cornerAIContentV923)return;window.__cornerAIContentV923=true;
"use strict";
const VERSION="12.8.12",MARK="cornerai-page-hook",PREFIX="[CornerAI]";
const clean=s=>String(s??"").replace(/\s+/g," ").trim();
let captureArmed=false,manualCaptureSession=true,lastAllToolsTestReport=null,lastSerialized="",lastCapture=0,lastSentAt=0,lastMinuteKey="",hookMessages=0,hookReadyAt=0,lastEventFingerprint="",lastStatsFingerprint="",lastChartNetwork={series:[],pressureBars:{},urls:[],at:0},lastKnownFid=null,lastUrlSeen=location.href,spaNavEpoch=0;

/** Limpa TODO o estado local de captura para impedir contaminação entre partidas. */
function wipeLocalCaptureState(reason,preserveFixtureId=null){
  const keepFid = preserveFixtureId && /^\d{5,}$/.test(String(preserveFixtureId)) ? String(preserveFixtureId) : null;
  lastSerialized="";
  lastCapture=0;
  lastSentAt=0;
  lastMinuteKey="";
  lastEventFingerprint="";
  lastStatsFingerprint="";
  lastChartNetwork={series:[],pressureBars:{},urls:[],at:0};
  lastKnownFid=keepFid;
  lastAutoFixture="";
  lastBackgroundAck=null;
  try{ window.__corneraiNetFixture=keepFid; }catch{}
  try{ window.__corneraiLatestState=null; }catch{}
  try{ console.log(PREFIX,"wipeLocalCaptureState:",reason||"fixture-change"); }catch{}
  try{
    const st=document.getElementById("cornerai-control-host")?.shadowRoot?.getElementById("status");
    if(st){ st.textContent="DADOS LIMPOS · NOVA PARTIDA"; st.style.color="#34d399"; setTimeout(()=>{ try{ if(st && st.textContent.indexOf("DADOS LIMPOS")===0){ st.textContent="CAPTURANDO…"; st.style.color=""; } }catch{} },2500); }
  }catch{}
}

function diagLog(level,code,message,extra){
  try{
    const entry={
      level:String(level||"INFO"),code:String(code||"CS"),message:String(message||"").slice(0,500),
      layer:"content",fixtureId:fixtureId(),url:location.href,epoch:Date.now(),at:new Date().toISOString(),
      extra:extra||undefined
    };
    chrome.runtime.sendMessage({type:"DIAG_LOG",payload:entry},()=>void chrome.runtime.lastError);
  }catch{}
}
function extractFidFromString(s){
  if(typeof CornerAILib!=="undefined"&&CornerAILib.extractFidFromString) return CornerAILib.extractFidFromString(s);
  try{
    const str=String(s||"");
    if(/^\d{5,12}$/.test(str.trim())) return str.trim();
    let m=str.match(/\/(?:fixture|partida|match|game|event)\/(\d{5,})/i);
    if(m) return m[1];
    m=str.match(/[?&#](?:fixture|fixtureId|matchId|match_id|gameId|game_id|eventId)=(\d{5,})/i);
    if(m) return m[1];
    m=str.match(/\/ws\/fixture\/(\d{5,})/i);
    if(m) return m[1];
    m=str.match(/\/(?:api\/)?fixtures?\/(\d{5,})/i);
    if(m) return m[1];
    m=str.match(/["'](?:fixture(?:Id)?|matchId|gameId)["']\s*[:=]\s*["']?(\d{5,})/i);
    if(m) return m[1];
    m=str.match(/sokkerpro\.com\/(?:fixture\/)?(\d{6,})(?:\/|$|\?)/i);
    if(m) return m[1];
    return null;
  }catch{return null}
}
const fixtureId=()=>{
 try{
   // v6.9.9.106: fixture resolution is deliberately conservative. SPA
   // performance entries, arbitrary links and global JSON can contain IDs from
   // previous matches and caused 19729326 to contaminate 19722621.
   const fromLoc=extractFidFromString(location.href);
   if(fromLoc) return String(fromLoc);

   const selectors=[
     "[data-fixture-id]","[data-match-id]","[data-game-id]",
     "meta[name=\"fixture-id\"]","meta[name=\"match-id\"]",
     "meta[property=\"game:id\"]"
   ];
   const candidates=[];
   for(const sel of selectors){
     for(const el of document.querySelectorAll(sel)){
       const v=el.getAttribute("data-fixture-id")||el.getAttribute("data-match-id")||
         el.getAttribute("data-game-id")||el.getAttribute("content")||"";
       if(/^\d{5,12}$/.test(String(v).trim())) candidates.push(String(v).trim());
     }
   }
   if(candidates.length){
     const uniq=[...new Set(candidates)];
     // Prefer the first DOM-declared fixture only when there is no conflict.
     if(uniq.length===1) return uniq[0];
     const current=lastKnownFid&&uniq.includes(String(lastKnownFid))?String(lastKnownFid):null;
     if(current) return current;
   }

   const canonical=document.querySelector('link[rel="canonical"]')?.href||"";
   const cm=extractFidFromString(canonical);
   if(cm) return String(cm);

   // A value explicitly established during THIS capture session is safe.
   if(lastKnownFid && /^\d{5,12}$/.test(String(lastKnownFid))) return String(lastKnownFid);

   // Do not consult performance resource history, arbitrary links or global
   // JSON/script blobs: those routinely survive SPA navigation.
   return null;
 }catch{return null}
};
function isFixturePage(){
 try{
  if(fixtureId()) return true; // network/DOM recovered id => treat as match page
  const u=new URL(location.href);
  if(u.searchParams.get("fixture")) return true;
  if(/\/(?:fixture|partida|match|game)\/\d+/i.test(u.pathname)) return true;
  // Heuristic: live scoreboard with teams + minute visible (SPA without /fixture/ in path)
  const hasScoreboard=!!document.querySelector(".scoreboard,[class*='scoreboard'],[class*='match-header'],.gs-match-info,[class*='live-score']");
  const hasStatRows=document.querySelectorAll(".stat-values-row,.statistics-row,[class*='stat-values-row']").length>=3;
  if(hasScoreboard && hasStatRows) return true;
  return false;
 }catch{return false}
}
function num(t){if(t==null)return null;const m=clean(t).replace(/\s/g,"").replace(/%/g,"").match(/-?\d+(?:[\.,]\d+)?/);return m?Number(m[0].replace(",",".")):null}
const labels={attacks:["ataques","attacks"],dangerous:["ataques perigosos","dangerous attacks"],shots:["total de chutes","finalizações","finalizacoes","shots","total shots"],shotsOn:["chutes a gol","chutes no alvo","no alvo","shots on target","shots on goal"],shotsOff:["chutes ao lado","ao lado","shots off target","shots off"],corners:["escanteios","cantos","corners"],xg:["xg","xg (expected goals)","expected goals","expected goals (xg)"],fouls:["faltas","fouls"],offsides:["impedimentos","offside","offsides"],yellow:["cartões amarelos","amarelos","yellow cards"],red:["cartões vermelhos","vermelhos","red cards"],subs:["substituições","substituicoes","substitutions","substituição","subs","trocas","alterações","alteracoes"],crosses:["cruzamentos","crosses","cross","cruzamento"],saves:["defesas do goleiro","defesas","saves"],passes:["passes certos","passes completos","accurate passes","completed passes","passes","passe"],passesFailed:["passes errados","passes falhados","passes incompletos","passes incompletos","inaccurate passes","failed passes","misplaced passes"],possession:["posse de bola","posse","possession"]};
function canonical(s){
 const l=clean(s).toLowerCase().replace(/\s+/g," ");
 // Exact labels always win. This prevents "Ataques perigosos" from being
 // incorrectly classified as plain "Ataques" and prevents partial-label collisions.
 for(const[k,v]of Object.entries(labels))if(v.some(x=>l===x))return k;
 // Fallback: longest alias first, so specific labels beat generic labels.
 const ranked=[];for(const[k,v]of Object.entries(labels))for(const x of v)ranked.push([k,x]);
 ranked.sort((a,b)=>b[1].length-a[1].length);
 for(const[k,x]of ranked)if(l.includes(x))return k;
 return null
}
function send(type,payload,meta){return new Promise(resolve=>{try{chrome.runtime.sendMessage({type,payload,meta},r=>{const err=chrome.runtime.lastError;if(err){try{lastCaptureError="send:"+err.message;lastDispatchResult={ok:false,error:err.message,type};}catch{}resolve({ok:false,error:err.message,swError:true});}else resolve(r||{ok:false,error:"empty_response"});})}catch(e){try{lastCaptureError="send_throw:"+e.message;}catch{}resolve({ok:false,error:e?.message||String(e)});}})}
function extractTeams(){
 // Rejeita textos longos / menus / contaminação de sidebar
 const isCleanName = (s) => {
   if(!s || typeof s !== "string") return false;
   const t = clean(s);
   if(t.length < 2 || t.length > 45) return false;
   // bloqueia menus e ruído típico da página
   if(/dashboard|favoritos|competi|vis[aã]o|todos|ao vivo|pr[oó]ximos|padr[aã]o|estat[ií]sticas|replays|assine|minist[eé]rio|gambling|privacy|cookie|terms|gdpr|about us|contact|leagues cup|concacaf|ofc champions|primera division|north & central|south america|escanteios|cart[oõ]es|escala[cç][oõ]es/i.test(t)) return false;
   if(/\d{2}:\d{2}/.test(t)) return false; // horários
   if((t.match(/\s/g)||[]).length > 5) return false; // nomes de time raramente têm >5 espaços
   return true;
 };
 const exact=[
   [".team-container-home .team-name",".team-container-away .team-name"],
   [".home-team .team-name",".away-team .team-name"],
   ["[data-team='home'] .team-name","[data-team='away'] .team-name"],
   ["[data-side='home'] .team-name","[data-side='away'] .team-name"],
   [".match-header .home .name",".match-header .away .name"],
   [".fixture-header .home",".fixture-header .away"],
   ["[class*='team-home'] [class*='name']","[class*='team-away'] [class*='name']"],
   ["[class*='home'] [class*='team-name']","[class*='away'] [class*='team-name']"]
 ];
 for(const[hs,as] of exact){
   const h=clean(document.querySelector(hs)?.textContent);
   const a=clean(document.querySelector(as)?.textContent);
   if(isCleanName(h) && isCleanName(a) && h.toLowerCase()!==a.toLowerCase()) return {home:h,away:a,confidence:"high"};
 }
 // Title é a fonte mais limpa
 const title=clean(document.title);
 // Padrões comuns no title: "Los Angeles FC 0 x 1 Querétaro" ou "LAFC vs Querétaro"
 let m = title.match(/^(.{2,40}?)\s+\d+\s*[xX\-]\s*\d+\s+(.{2,40}?)(?:\s*[·|•\-]|\s*$)/);
 if(m){
   const h=clean(m[1]), a=clean(m[2]);
   if(isCleanName(h)&&isCleanName(a)) return {home:h,away:a,confidence:"title"};
 }
 m = title.match(/^(.{2,40}?)\s+(?:x|vs|v)\.?\s+(.{2,40}?)(?:\s*[·|•\-]|\s*$)/i);
 if(m){
   const h=clean(m[1]), a=clean(m[2]);
   if(isCleanName(h)&&isCleanName(a)) return {home:h,away:a,confidence:"title-vs"};
 }
 // Último recurso: só os primeiros 800 chars do body (nunca 12000)
 const body=clean((document.body?.innerText||"").slice(0,800));
 m = body.match(/(.{2,40}?)\s+\d+\s*[xX\-]\s*\d+\s+(.{2,40}?)(?:\s|$)/);
 if(m){
   const h=clean(m[1]), a=clean(m[2]);
   if(isCleanName(h)&&isCleanName(a)) return {home:h,away:a,confidence:"body-short"};
 }
 return {home:"",away:"",confidence:"none"};
}
function detectMatchStatus(){
 // [FIX v6.9.9.90] Não varrer o body inteiro por "FT/finalizado" — sidebars, H2H e
 // listas de outros jogos contaminavam partidas AO VIVO como finished.
 const rawTitle=clean(document.title);
 const title=rawTitle.toLowerCase();

 // Texto restrito ao cabeçalho / placar da partida atual
 const headerEls=[...document.querySelectorAll(
   ".scoreboard,[class*='scoreboard'],[class*='match-header'],[class*='match-status'],"+
   ".gs-match-info,[class*='match-info'],[class*='live-score'],.fx-score,.match-score,"+
   "[class*='fixture-header'],[class*='game-header'],header,[role='banner']"
 )].slice(0,12);
 let headerText=title;
 for(const el of headerEls){
   try{ headerText+=" "+clean(el.textContent||"").slice(0,400); }catch{}
 }
 headerText=headerText.toLowerCase().slice(0,2500);

 // Relógio ao vivo: seletores primários + genéricos curtos
 const liveNodes=[...document.querySelectorAll(
   ".gs-live-min,.gs-match-min,.match-clock,.live-clock,[data-live-minute],"+
   "[class*='live-min'],[class*='match-minute'],[class*='gs-live'],"+
   "[class*='elapsed'],[class*='match-time']"
 )];
 const liveClock=liveNodes.some(e=>{
   const t=clean(e.textContent||"");
   if(t.length>18) return false;
   if(/escanteio|canto|corner|gol|goal|cart[aã]o|substit/i.test(t)) return false;
   if(/\b(?:ao vivo|live)\b/i.test(t)) return true;
   return /^\d{1,3}(?:\s*\+\s*\d{1,2})?\s*['′]?$/.test(t);
 });
 // Relógio via extractClock (mais robusto)
 const clockObj=(()=>{ try{return extractClock();}catch{return null;} })();
 const hasClock=!!(clockObj&&Number.isFinite(clockObj.minute)&&clockObj.minute>=0&&clockObj.minute<=130);
 const clockMin=hasClock?Number(clockObj.minute):null;

 // Marcadores explícitos de AO VIVO no header/título
 const explicitLive=/\b(?:ao vivo|ao-vivo|em andamento|in progress|live\s*match)\b/.test(headerText)
   || document.querySelector(".gs-live-min,[class*='live-badge'],[class*='is-live'],[data-live='true']");

 // Marcadores explícitos de FINAL no header/título (NÃO no body inteiro)
 const explicitFinished=/\b(?:finalizado|encerrado|fim de jogo|fim do jogo|partida encerrada|full\s*time|resultado final|após\s*prorrog|após\s*pênaltis)\b/.test(headerText)
   || /\bFT\b|\bF\.T\.?\b/.test(headerText.replace(/full\s*time/gi,"FT"));
 // "FT" isolado só conta se estiver no header curto, não em "soft" genérico
 const ftInTitle=/\b(?:FT|F\.T\.?)\b/.test(rawTitle);

 if(/\b(?:cancelad[oa]|adiad[oa]|postergad[oa]|abandonad[oa])\b/.test(headerText)) return"cancelled";
 if(/\b(?:não iniciado|nao iniciado|pré-jogo|pre-jogo|not started|scheduled|upcoming|a iniciar)\b/.test(headerText)&&!hasClock&&!explicitLive) return"not_started";

 // PRIORIDADE 1: relógio vivo ou marcador ao vivo → SEMPRE live
 // (mesmo que a página mencione "finalizado" em outro jogo na sidebar)
 if(explicitLive) return"live";
 if(liveClock||hasClock){
   // Só cede a finished se o header disser explicitamente FT/finalizado E o relógio sumiu
   if(explicitFinished && !liveClock && !hasClock) return"finished";
   return"live";
 }

 // PRIORIDADE 2: finished explícito no header da partida
 if(explicitFinished||ftInTitle) return"finished";

 // PRIORIDADE 3: página histórica típica — placar no título, sem relógio, 2º tempo presente
 const bodySlice=clean(document.body?.innerText||"").slice(0,1800).toLowerCase();
 const hasSecondHalf=/2[ºo]\s*tempo|second\s*half/i.test(bodySlice);
 const titleScore=/\b\d{1,2}\s*[xX×-]\s*\d{1,2}\b/.test(rawTitle);
 const score=extractScore();
 // Só finished se NÃO há nenhum sinal de live E há evidência de partida completa
 if((score||titleScore) && !liveClock && !hasClock && hasSecondHalf){
   const hasFullTimeEvents=/(?:^|\D)(?:9[0-9]|1[0-2][0-9])(?:\+\d{1,2})?['′]/m.test(bodySlice);
   if(hasFullTimeEvents||explicitFinished) return"finished";
 }

 // 9.2.1: clock legível (1–120) + placar sem marcador de FT ⇒ LIVE
 // Corrige partidas que ficavam "inactive/unknown" com minuto 64' e score 1x0.
 if(!explicitFinished && hasClock && clockMin!=null && clockMin>=1 && clockMin<=120){
   return"live";
 }
 if(!explicitFinished && liveClock && (score||titleScore)) return"live";

 return"unknown";
}
function extractTextTimelineEvents(){
 const text=String(document.body?.innerText||"").replace(/\u00a0/g," ");
 if(!text)return[];
 const out=[],seen=new Set();
 const section=/((?:1º|1o|primeiro)\s*(?:tempo|primeiro tempo)|detalhadosimples)([\s\S]{0,18000}?)(?=(?:2º|2o|segundo)\s*tempo|odds|classifica[cç][aã]o|fora do jogo|informa[cç][oõ]es do tempo|$)/i.exec(text);
 const chunks=[];
 if(section)chunks.push({period:1,text:section[2]});
 const second=/(?:2º|2o|segundo)\s*tempo([\s\S]{0,18000}?)(?=(?:jogador da partida|classifica[cç][aã]o|odds|fora do jogo|informa[cç][oõ]es do tempo|$))/i.exec(text);
 if(second)chunks.push({period:2,text:second[1]});
 for(const chunk of chunks){
   const re=/(\d{1,3})(?:\+(\d{1,2}))?['′]\s*([^\n\r]*?)(?=(?:\d{1,3}(?:\+\d{1,2})?['′])|$)/g;
   let m;
   while((m=re.exec(chunk.text))){
     const minute=Number(m[1]),extra=Number(m[2]||0),label=clean(m[3]);
     if(minute>130||!label)continue;
     let type=null;
     if(/escanteio|canto|corner/i.test(label))type="corner";
     else if(/(?:chute|shot|finaliza(?:ção|cao))[^\n]{0,24}(?:no|a|ao)?\s*(?:gol|alvo|target)|(?:no|on)\s+(?:gol|alvo|target)/i.test(label))type="shot_on";
     else if(/\b(?:gol|goal)\b|\b\d{1,2}\s*[-x]\s*\d{1,2}\b/i.test(label))type="goal";
     else if(/cart[aã]o\s+amarelo|yellow/i.test(label))type="yellow";
     else if(/cart[aã]o\s+vermelho|red/i.test(label))type="red";
     else if(/substitui|substitution/i.test(label))type="substitution";
     else if(/impedimento|offside/i.test(label))type="offsides";
     else if(/chute|finaliza|shot/i.test(label))type="shot";
     if(!type)continue;
     const key=`${fixtureId()||"unknown"}|text|${chunk.period}|${minute}|${extra}|${type}|${label}`;
     if(seen.has(key))continue;seen.add(key);
     // Text-only fallback deliberately keeps side unknown. It is not promoted to a team event
     // unless the DOM/network parser can resolve the team, preventing false Home/Away labels.
     const _teams=extractTeams(); const _side=sideFromLabel(label,_teams); out.push({eventId:key,fixtureId:(fixtureId()||(window.__corneraiNetFixture?String(window.__corneraiNetFixture):null)),minute,extraMinute:extra,period:chunk.period,type,label,side:_side||null,teamName:_side==="home"?_teams.home:(_side==="away"?_teams.away:""),confidence:_side?0.7:0.55,timestamp:Date.now(),source:"dom-text"});
   }
 }
 
 // 9.2.10: global scan — "8' 1º Escanteio" / "23' 2º Escanteio" outside section blocks
 try{
   const gre=/(\d{1,3})(?:\+(\d{1,2}))?['′]?\s*(?:(\d+)[ºo]?\s*)?(escanteio|canto|corner)\b/gi;
   let gm;
   while((gm=gre.exec(text))){
     const minute=Number(gm[1]), extra=Number(gm[2]||0);
     if(minute>130) continue;
     const ord=gm[3]?Number(gm[3]):null;
     const label=clean((ord?ord+"º ":"")+"Escanteio");
     const key=`${fixtureId()||"unknown"}|gcorner|${minute}+${extra}|${ord||""}`;
     if(seen.has(key)) continue; seen.add(key);
     const period=minute>45?2:1;
     out.push({eventId:key,fixtureId:(fixtureId()||null),minute,extraMinute:extra,period,type:"corner",label,side:null,teamName:"",confidence:0.6,timestamp:Date.now(),source:"dom-text-global"});
   }
 }catch{}
 return out;
}

function extractScore(){
 // SCORE HARDENED 12.6.23:
 // Nunca use document.title como primeira fonte: o title pode ficar stale durante
 // uma SPA transition e já foi responsável por exibir 1x1 enquanto o placar live
 // do jogo era 0x1. A ordem agora é: atributos explícitos -> widget visível ->
 // header do fixture -> title apenas como último recurso.
 const readPair=(root)=>{
   if(!root) return null;
   const ah=root.querySelector('[data-score-home],[data-home-score],.home-score,.score-home,[class*="home-score"]');
   const aa=root.querySelector('[data-score-away],[data-away-score],.away-score,.score-away,[class*="away-score"]');
   const hv=num(ah?.textContent ?? ah?.getAttribute?.('data-score-home') ?? ah?.getAttribute?.('data-home-score'));
   const av=num(aa?.textContent ?? aa?.getAttribute?.('data-score-away') ?? aa?.getAttribute?.('data-away-score'));
   if(hv!=null&&av!=null&&hv>=0&&av>=0&&hv<=30&&av<=30) return {home:hv,away:av,source:'dom-explicit'};
   const txt=clean(root.textContent||'');
   // Score must be close to a score marker; avoid odds/stat rows.
   const m=txt.match(/(?:placar|score|resultado)?\s*(\d{1,2})\s*[xX×]\s*(\d{1,2})(?:\s|$)/i);
   if(m){const h=Number(m[1]),a=Number(m[2]); if(h<=30&&a<=30)return{home:h,away:a,source:'dom-widget'};}
   return null;
 };
 const roots=[
   ...document.querySelectorAll('.fx-score,.match-score,.scoreboard,[class*="scoreboard"],[class*="match-header"],.gs-match-info,[class*="live-score"],[class*="fixture-header"],[class*="game-header"]')
 ];
   for(const root of roots){
     const pair=readPair(root);
     if(pair) return pair;
   }
   // Generic explicit data attributes are safer than broad class scanning.
   for(const root of document.querySelectorAll('[data-score],[data-score-home],[data-score-away]')){
     const pair=readPair(root);
     if(pair) return pair;
   }
   // Last DOM fallback: direct children of the score widget only.
   for(const root of document.querySelectorAll('.fx-score,.match-score,.score')){
     const candidates=[...root.querySelectorAll(':scope > span,:scope > b,:scope > strong,.score-number,.home-score,.away-score')];
     const ns=candidates.map(x=>num(x.textContent)).filter(x=>x!=null&&x>=0&&x<=30);
     if(ns.length>=2) return {home:ns[0],away:ns[ns.length-1],source:'dom-direct'};
   }
   // Title is deliberately last. It is not a live-authoritative source.
   const title=clean(document.title);
   const tm=title.match(/\b(\d{1,2})\s*[xX×]\s*(\d{1,2})\b/);
   if(tm) return {home:Number(tm[1]),away:Number(tm[2]),source:'title-fallback'};
   return null;
 }

function extractClock(){
  const candidates=[];
  const push=(minute,extra,score,src)=>{
    if(!Number.isFinite(minute)||minute<0||minute>130) return;
    // 0' só é válido no arranque — evita travar em zero
    extra=Math.max(0,Number(extra)||0);
    candidates.push({minute,extraMinute:extra,score,src});
  };
  const primary=document.querySelectorAll(".gs-live-min,.gs-match-min,.match-clock,.live-clock,[data-live-minute],[class*='live-min'],[class*='match-minute'],[class*='gs-live']");
  for(const e of primary){
    const t=clean(e.textContent);
    if(/escanteio|canto|corner|gol|goal|cart[aã]o|substit/i.test(t)) continue;
    const m=t.match(/^\s*(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?\s*$/)||t.match(/^\s*(\d{1,3})\s*['′]?\s*$/);
    if(m) push(Number(m[1]),Number(m[2]||0),100,"primary");
  }
  const header=document.querySelectorAll(".scoreboard,[class*='scoreboard'],[class*='match-header'],[class*='match-status'],.gs-match-info,[class*='match-info'],[class*='live-score']");
  for(const e of header){
    const t=clean(e.textContent).slice(0,240);
    if(/escanteio|1º escanteio|2º escanteio/i.test(t)&&t.length>40) continue;
    const m=t.match(/\b(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?/)||t.match(/\b(\d{1,3})\s*['′](?!\s*\d)/);
    if(m) push(Number(m[1]),Number(m[2]||0),80,"header");
  }
  const title=clean(document.title||"");
  let tm=title.match(/\b(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?/)||title.match(/\b(\d{1,3})\s*['′]/);
  if(tm) push(Number(tm[1]),Number(tm[2]||0),55,"title");
  // body short scan near score pattern "3 x 1" then minute
  try{
    const body=String(document.body?.innerText||"").slice(0,2500);
    const near=body.match(/(\d{1,2})\s*[xX×]\s*(\d{1,2})[^\n]{0,40}?(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?/)
      ||body.match(/(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?[^\n]{0,40}?(\d{1,2})\s*[xX×]\s*(\d{1,2})/)
      ||body.match(/\b(\d{2,3})\s*['′]\s*(?:2[ºo]|2o|HT|FT|ao vivo|live)/i);
    if(near){
      // pick the minute-like group
      const nums=near.slice(1).map(Number).filter(n=>Number.isFinite(n));
      const minuteCand=nums.find(n=>n>=1&&n<=130&&n!==Number(near[1])||true);
    }
  }catch{}
  if(!candidates.length){
    for(const e of document.querySelectorAll("[class*='minute'],[class*='elapsed'],[class*='timer'],[class*='clock']")){
      const t=clean(e.textContent);
      if(t.length>16) continue;
      if(/escanteio|canto|corner|gol|goal|cart[aã]o/i.test(t)) continue;
      if(e.closest&&e.closest(".timeline,.events,.event-list,[class*='timeline'],[class*='incident']")) continue;
      const m=t.match(/^\s*(\d{1,3})\s*\+\s*(\d{1,2})\s*['′]?\s*$/)||t.match(/^\s*(\d{1,3})\s*['′]?\s*$/);
      if(m) push(Number(m[1]),Number(m[2]||0),35,"generic");
    }
  }
  if(!candidates.length) return null;
  // descartar 0' se existir candidato >0
  const nonZero=candidates.filter(x=>x.minute>0);
  const pool=nonZero.length?nonZero:candidates;
  pool.sort((a,b)=>b.score-a.score||b.minute-a.minute||b.extraMinute-a.extraMinute);
  const best=pool[0];
  return {minute:best.minute,extraMinute:best.extraMinute,source:best.src};
}
function extractMinute(){const c=extractClock();return c?c.minute:null}
function pairFromEls(els){const v=[...els].map(x=>num(x.textContent)).filter(x=>x!=null);return v.length>=2?{home:v[0],away:v[v.length-1]}:null}
function extractRows(){
 const out={};
 const rows=document.querySelectorAll(".stat-values-row,.statistics-row,.stats-row,[class*='stat-values-row'],[class*='statistics'] tr,[data-stat],tr.stat-row");
 for(const row of rows){
   const label=clean(row.querySelector(".stat-label,.stat-name,[class*='stat-label'],th,td:first-child,[data-stat-label]")?.textContent||row.firstElementChild?.textContent||row.getAttribute("data-stat")||"");
   const k=canonical(label); if(!k)continue;
   const valueNodes=[...row.querySelectorAll(".stat-value,.stat-number,.value,.home-value,.away-value,[data-value]")];
   const values=valueNodes.map(x=>num(x.textContent)).filter(x=>x!=null);
   if(values.length>=2){out[k]={home:values[0],away:values[values.length-1]};continue}
   // Fallback for layouts where the row contains only text nodes.
   const nums=(clean(row.textContent).match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(",",".")));
   if(nums.length>=2)out[k]={home:nums[0],away:nums[nums.length-1]};
 }
 return out;
}
function normalizeStatKeyLabel(label){
 const n=clean(label).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"");
 return n.slice(0,70);
}
function extractExtendedRows(){
 const out={},known=new Set(Object.keys(labels));
 const rows=document.querySelectorAll(".stat-values-row,.statistics-row,.stats-row,[class*='stat-values-row'],[class*='statistics'] tr,tr.stat-row,[data-stat],[data-stat-label],.stat-row,.stat-item,.statistics-item");
 for(const row of rows){
   const label=clean(row.querySelector(".stat-label,.stat-name,[class*='stat-label'],[class*='stat-name'],th,td:first-child,[data-stat-label]")?.textContent||row.getAttribute("data-stat-label")||row.getAttribute("data-stat")||row.firstElementChild?.textContent||"");
   if(!label||label.length>100)continue;
   if(/^\d+(?:\+\d+)?['′]?$/.test(label)||/odds|odd|cot[aã]ção|quota|1x2|play with responsibility|responsibility|mercado|sele[cç][aã]o não identificada/i.test(label)||/[=|]{2,}/.test(label))continue;
   const nodes=[...row.querySelectorAll(".stat-value,.stat-number,.value,.home-value,.away-value,[data-value],td:not(:first-child),th:not(:first-child),[data-home-value],[data-away-value]")];
   let vals=nodes.map(x=>num(x.getAttribute("data-value")??x.textContent)).filter(x=>x!=null);
   const dh=num(row.getAttribute("data-home-value")), da=num(row.getAttribute("data-away-value"));
   if(dh!=null&&da!=null)vals=[dh,da];
   if(vals.length<2)vals=(clean(row.textContent).match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(",","."))).filter(Number.isFinite);
   if(vals.length<2)continue;
   const canonicalKey=canonical(label);
   if(canonicalKey)continue;
   const key=normalizeStatKeyLabel(label);if(!key||known.has(key)||key.length<2)continue;
   let eh=vals[0],ea=vals[vals.length-1];
   if(/xg|expected goals|gols esperados/i.test(label)){if(eh>10&&eh<=1000)eh/=100;if(ea>10&&ea<=1000)ea/=100;}
   out[key]={label:label.slice(0,100),home:eh,away:ea,source:"dom",timestamp:Date.now()};
 }
 return out;
}

/** Scan profundo para stats escondidos (rows colapsadas / texto sem classe). */
function extractHiddenStatPairs(){
  const out={};
  const patterns={
    shots:[/\b(?:total\s+de\s+)?(?:chutes?|finaliza[cç][oõ]es|shots?)\b/i],
    shotsOn:[/\b(?:chutes?\s+(?:a|no)\s+(?:gol|alvo)|shots?\s+on(?:\s+target)?)\b/i],
    shotsOff:[/\b(?:chutes?\s+(?:ao\s+lado|fora)|shots?\s+off(?:\s+target)?)\b/i],
    offsides:[/\b(?:impedimentos?|offsides?)\b/i],
    subs:[/\b(?:substitui[cç][oõ]es|substitutions?|trocas)\b/i],
    crosses:[/\b(?:cruzamentos?|crosses?)\b/i],
    passes:[/\b(?:passes?\s+(?:certos?|completos?)|accurate\s+passes|completed\s+passes)\b/i],
    passesFailed:[/\b(?:passes?\s+(?:errados?|falhados?|incompletos?)|inaccurate\s+passes|failed\s+passes)\b/i],
    fouls:[/\b(?:faltas?|fouls?)\b/i],
    saves:[/\b(?:defesas?(?:\s+do\s+goleiro)?|saves?)\b/i]
  };
  // 1) Linhas de texto "Label  3  5"
  const lines=String(document.body?.innerText||"").replace(/\u00a0/g," ").split(/\r?\n/).map(clean).filter(l=>l.length>2&&l.length<120);
  for(const line of lines){
    for(const [key,res] of Object.entries(patterns)){
      if(out[key]) continue;
      if(!res.some(r=>r.test(line))) continue;
      const nums=(line.match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(",","."))).filter(Number.isFinite);
      // Prefer last two integers as home/away
      const ints=nums.filter(n=>Number.isInteger(n)&&n>=0&&n<=300);
      if(ints.length>=2){
        out[key]={home:ints[ints.length-2],away:ints[ints.length-1]};
      }
    }
  }
  // 2) Elementos genéricos com label + dois valores
  const nodes=[...document.querySelectorAll("[class*='stat'],[class*='Stat'],[data-stat],li,div,span")].slice(0,400);
  for(const el of nodes){
    const t=clean(el.textContent||"");
    if(t.length<3||t.length>80) continue;
    for(const [key,res] of Object.entries(patterns)){
      if(out[key]) continue;
      if(!res.some(r=>r.test(t))) continue;
      const nums=(t.match(/\d+/g)||[]).map(Number).filter(n=>Number.isFinite(n)&&n>=0&&n<=300);
      if(nums.length>=2) out[key]={home:nums[0],away:nums[nums.length-1]};
    }
  }
  return out;
}
function extractStatsText(){
 const lines=String(document.body?.innerText||"").replace(/\u00a0/g," ").split(/\r?\n/).map(clean).filter(Boolean);
 if(!lines.length)return {};
 const teams=extractTeams(); if(!teams.home||!teams.away)return {};
 const start=lines.findIndex(x=>/dados separados por equipe/i.test(x));
 if(start<0)return {};
 const end=lines.findIndex((x,i)=>i>start&&/gr[aá]ficos hist[oó]ricos separados por equipe|alterações hist[oó]ricas por equipe|timeline unificada/i.test(x));
 const block=lines.slice(start+1,end>start?end:Math.min(lines.length,start+120));
 const teamIndex=block.findIndex(x=>x.toLowerCase()===teams.home.toLowerCase());
 const awayIndex=block.findIndex((x,i)=>i>0&&x.toLowerCase()===teams.away.toLowerCase());
 if(teamIndex<0||awayIndex<0)return {};
 // The visible "Dados separados por equipe" panel is NOT a two-column table.
 // Each team section is a vertical list: label -> single team value. The old
 // parser consumed the next metric as the away value, causing: attacks=84,
 // dangerous=0, shots=1, etc. Parse each section independently and map the
 // single value to the corresponding team.
 const parseSection=(arr)=>{
   const out={};
   for(let i=0;i<arr.length;i++){
     const k=canonical(arr[i]);
     if(!k)continue;
     const v=num(arr[i+1]);
     if(v!=null){out[k]=v;i+=1;}
   }
   return out;
 };
 const h=parseSection(block.slice(teamIndex+1,awayIndex));
 const a=parseSection(block.slice(awayIndex+1));
 const out={};
 for(const k of STAT_KEYS_LOCAL){
   if(Object.prototype.hasOwnProperty.call(h,k)||Object.prototype.hasOwnProperty.call(a,k)){
     out[k]={home:h[k]??null,away:a[k]??null};
   }
 }
 return out;
}
const STAT_KEYS_LOCAL=Object.keys(labels);


function extractXG(){
 const teams=extractTeams();
 const candidates=[];
 const toNum=v=>{const n=num(v);return Number.isFinite(n)?n:null};
 const normalize=(a,b,unit="xg")=>{
   if(a==null||b==null)return null;
   let h=a,w=b;
   if(unit==="percent") { h/=100; w/=100; }
   // xG is an expected-goals quantity, not a percentage. Values above 10 are
   // never accepted blindly; integer hundredths are only normalized when the
   // provider explicitly labels the unit as percent/hundredths.
   if(h<0||w<0||h>10||w>10)return null;
   return {home:Number(h),away:Number(w)};
 };
 const add=(home,away,score,method,raw,unit="xg",el=null)=>{
   const pair=normalize(home,away,unit); if(!pair)return;
   candidates.push({pair,score,method,rawHome:home,rawAway:away,unit,selector:el?.tagName||null});
 };
 // 1) Explicit data attributes are the strongest DOM evidence.
 for(const el of document.querySelectorAll('[data-home-xg][data-away-xg],[data-xg-home][data-xg-away]')){
   const h=toNum(el.getAttribute('data-home-xg')||el.getAttribute('data-xg-home'));
   const a=toNum(el.getAttribute('data-away-xg')||el.getAttribute('data-xg-away'));
   add(h,a,100,'explicit-attributes',{home:h,away:a},'xg',el);
 }
 for(const el of document.querySelectorAll('[data-xg],[data-expected-goals], [aria-label*="xG" i], [title*="xG" i]')){
   const raw=clean(el.getAttribute('data-xg')||el.getAttribute('data-expected-goals')||el.getAttribute('aria-label')||el.getAttribute('title')||el.textContent);
   const vals=(raw.match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(',','.'))).filter(Number.isFinite);
   if(vals.length>=2)add(vals[0],vals[1],96,'explicit-value',raw,'xg',el);
 }
 // 2) Exact statistic rows. Never use a broad parent container because it can
 // contain xG from a chart, historical card, or another fixture section.
 const rows=[...document.querySelectorAll('.stat-values-row,.statistics-row,.stats-row,tr.stat-row,[data-stat],[data-stat-label],.stat-row,.stat-item,.statistics-item')];
 for(const row of rows){
   const label=clean(row.querySelector('.stat-label,.stat-name,[class*="stat-label"],[class*="stat-name"],th,td:first-child,[data-stat-label]')?.textContent||row.getAttribute('data-stat-label')||row.getAttribute('data-stat')||row.firstElementChild?.textContent||'');
   if(!/^x\s*g$|^xg$|expected goals|gols esperados/i.test(label.trim()))continue;
   const nodes=[...row.querySelectorAll('.stat-value,.stat-number,.value,.home-value,.away-value,[data-value],[data-home-value],[data-away-value],td:not(:first-child),th:not(:first-child)')];
   let vals=nodes.map(x=>toNum(x.getAttribute('data-value')??x.textContent)).filter(v=>v!=null);
   const dh=toNum(row.getAttribute('data-home-value')),da=toNum(row.getAttribute('data-away-value'));
   if(dh!=null&&da!=null)vals=[dh,da];
   if(vals.length<2)vals=(clean(row.textContent).match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(',','.'))).filter(Number.isFinite);
   if(vals.length>=2)add(vals[0],vals[vals.length-1],94,'exact-stat-row',{label,values:vals.slice(0,4)},'xg',row);
 }
 // 3) Accessible text: accept only a compact, exact xG label with two values.
 for(const el of document.querySelectorAll('[aria-label],[role="img"],span,div,p')){
   const txt=clean(el.getAttribute('aria-label')||el.textContent); if(txt.length>160)continue;
   if(!/(?:^|\b)(?:xg|x\s*g|expected goals|gols esperados)(?:\b|:)/i.test(txt))continue;
   const vals=(txt.match(/-?\d+(?:[.,]\d+)?/g)||[]).map(x=>Number(x.replace(',','.'))).filter(Number.isFinite);
   if(vals.length===2)add(vals[0],vals[1],82,'accessible-text',txt,'xg',el);
 }
 // Prefer the most explicit candidate; if tied, prefer a candidate whose two
 // values are close to the live DOM and whose element is structurally small.
 candidates.sort((a,b)=>b.score-a.score);
 const best=candidates[0];
 if(!best)return null;
 // Multi-source provenance: keep top candidates for conflict detection downstream.
 const top=candidates.slice(0,5).map(c=>({
   home:c.pair.home,away:c.pair.away,score:c.score,method:c.method,
   confidence:Math.min(1,c.score/100),unit:c.unit||"xg"
 }));
 // Detect significant conflicts among high-scoring candidates.
 let conflict=null;
 if(top.length>=2){
   const a=top[0],b=top[1];
   const dh=Math.abs(a.home-b.home),da=Math.abs(a.away-b.away);
   if(dh>0.25||da>0.25) conflict={deltaHome:dh,deltaAway:da,primary:a.method,secondary:b.method};
 }
 return {
   ...best.pair,
   source:'dom',
   confidence:Math.min(1,best.score/100),
   method:best.method,
   rawHome:best.rawHome,rawAway:best.rawAway,unit:best.unit,
   candidateCount:candidates.length,
   candidates:top,
   conflict:conflict||null,
   teams:{home:teams.home,away:teams.away}
 };
}

function extractCornerIndicators(){
 const teams=extractTeams();
 const cleanNumText=v=>String(v??"").replace(/\u00a0/g," ").replace(/,/g,".").trim();
 const numbers=v=>(cleanNumText(v).match(/-?\d+(?:\.\d+)?%?/g)||[]).map(x=>x.endsWith("%")?Number(x.slice(0,-1)):Number(x));
 const norm=v=>clean(v).toLowerCase().replace(/\s+/g," ");
 const labelMap={attacks:["ataques","attacks"],dangerous:["ataques perigosos","dangerous attacks"],corners:["escanteios","cantos","corners"],shotsOn:["chutes no gol","chutes a gol","no alvo","shots on target"],shotsOff:["chutes ao lado","ao lado","shots off target"],xg:["xg","expected goals"],possession:["posse de bola","posse","possession"]};
 const isLabel=(text,label)=>{const n=norm(text);return n===label||n.startsWith(label+" ")||n.includes(" "+label+" ")||n.includes(label)};
 function rowFor(labelsWanted){
   let best=null;
   for(const el of document.querySelectorAll("div,section,li,tr,p,span")){
     const txt=clean(el.textContent); if(!txt||txt.length>260)continue;
     const n=norm(txt); const matches=labelsWanted.filter(l=>n===l||n.startsWith(l+" ")||n.includes(" "+l+" ")||n.includes(l)); if(!matches.length)continue;
     const exact=matches.some(l=>n===l);
     const prefix=matches.some(l=>n.startsWith(l+" "));
     const score=exact?0:(prefix?1:2);
     const nums=numbers(txt.replace(new RegExp(labelsWanted.map(x=>x.replace(/[.*+?^${}()|[\\]\\]/g,"\\$&")).join("|"),"ig")," "));
     if(nums.length>=2){ if(!best||score<best.score||(score===best.score&&txt.length<best.text.length))best={el,text:txt,nums,score}; }
   }
   return best;
 }
 const out={minute:extractMinute(),timestamp:Date.now(),source:"dom"};
 for(const [k,ls] of Object.entries(labelMap)){
   const r=rowFor(ls); if(!r)continue;
   let vals=r.nums.filter(v=>Number.isFinite(v));
   if(k==="possession")vals=vals.map(v=>v>100?null:v).filter(v=>v!=null);
   if(vals.length>=2)out[k]={home:vals[0],away:vals[1]};
 }
 // APPM is a rolling pressure-rate indicator. Capture each published window independently.
 const appm={};
 for(const win of ["1m","3m","5m","10m","Total"]){
   const r=rowFor([`appm ${win.toLowerCase()}`,`appm${win.toLowerCase()}`]);
   if(r){const vals=r.nums.filter(Number.isFinite);if(vals.length>=2)appm[win]={home:vals[0],away:vals[1]};else if(vals.length===1)appm[win]={home:vals[0],away:null};}
 }
 if(Object.keys(appm).length)out.appm=appm;
 // Pressure bar: prefer DOM .pressure-block, fallback texto de intervalo.
 const pressure={};
 try{
   const bars=extractPressureBars();
   for(const [k,v] of Object.entries(bars||{})){
     if(!v||v.empty) continue;
     const h=Number(v.home), a=Number(v.away), pct=Number(v.pct);
     if(Number.isFinite(pct)&&pct>=0&&pct<=100){
       const awayPct=Number.isFinite(h)&&Number.isFinite(a)&&(h+a)>0
         ? Number(((a/(h+a))*100).toFixed(1))
         : Number((100-pct).toFixed(1));
       pressure[k]={home:pct,away:awayPct,source:"pressure-block"};
     } else if(Number.isFinite(h)&&Number.isFinite(a)&&(h+a)>0){
       pressure[k]={home:Number(((h/(h+a))*100).toFixed(1)),away:Number(((a/(h+a))*100).toFixed(1)),source:"pressure-block-grow"};
     }
   }
 }catch{}
 for(const win of ["0-15","15-30","30-45","45-60","60-75","75-90"]){
   if(pressure[win]) continue;
   const r=rowFor([win,win.replace("-"," – ")]);
   if(r){const vals=r.nums.filter(v=>Number.isFinite(v)&&v>=0&&v<=100);if(vals.length>=2)pressure[win]={home:vals[0],away:vals[1],source:"text-row"};}
 }
 if(Object.keys(pressure).length)out.pressure=pressure;
 // Capture only explicit chart values. Never interpret SVG pixel coordinates (data-x/data-y)
 // as match minutes/values. The old parser turned 180 textual performance labels into minute=0/value=0.
 const points=[],seenPoints=new Set();
 for(const el of document.querySelectorAll("[data-minute][data-value],[data-minute][data-home-value][data-away-value]")){
   const minute=Number(el.getAttribute("data-minute")), value=Number(el.getAttribute("data-value"));
   const homeValue=Number(el.getAttribute("data-home-value")),awayValue=Number(el.getAttribute("data-away-value"));
   if(!Number.isFinite(minute)||minute<0||minute>130)continue;
   if(Number.isFinite(value)){const team=clean(el.getAttribute("data-team")||el.getAttribute("data-series")||el.getAttribute("data-name"));const key=`${minute}|${team}|${value}`;if(!seenPoints.has(key)){seenPoints.add(key);points.push({minute,value,team:team||null,explicit:true});}}
   else if(Number.isFinite(homeValue)&&Number.isFinite(awayValue)){const key=`${minute}|pair|${homeValue}|${awayValue}`;if(!seenPoints.has(key)){seenPoints.add(key);points.push({minute,homeValue,awayValue,explicit:true});}}
 }
 // Some layouts expose the performance values only as accessible text. Parse the numeric values
 // from that text instead of pretending the label itself is a zero-valued graph point.
 const teamNames=[teams.home,teams.away].filter(Boolean);
 for(const el of document.querySelectorAll("[aria-label],[title]")){
   const txt=clean(el.getAttribute("aria-label")||el.getAttribute("title")); if(!/minuto\s*\d+/i.test(txt)||!/pontos/i.test(txt))continue;
   const mm=txt.match(/Minuto\s*(\d{1,3})(?:\+(\d{1,2}))?/i); if(!mm)continue; const minute=Number(mm[1]); if(minute<0||minute>130)continue;
   const vals=[...txt.matchAll(/: ?(\d+(?:[.,]\d+)?)\s*pontos/gi)].map(m=>Number(m[1].replace(",","."))).filter(Number.isFinite); if(vals.length<2)continue;
   const key=`${minute}|text|${vals[0]}|${vals[1]}`; if(!seenPoints.has(key)){seenPoints.add(key);points.push({minute,homeValue:vals[0],awayValue:vals[1],teamNames,explicit:true,source:"aria-text"});}
 }
 if(points.length)out.performancePoints=points.slice(0,500);
 return out;
}
function extractTables(){const out={};for(const tr of document.querySelectorAll("tr")){const c=[...tr.querySelectorAll("th,td")].map(x=>clean(x.textContent));if(c.length<3)continue;const k=canonical(c[0]),h=num(c[1]),a=num(c[c.length-1]);if(k&&h!=null&&a!=null)out[k]={home:h,away:a}}return out}
function extractShotCards(){const out={};for(const line of document.querySelectorAll(".shot-line")){const l=clean(line.querySelector(".shot-label")?.textContent).toLowerCase(),v=[...line.querySelectorAll(".shot-num")].map(x=>num(x.textContent)).filter(x=>x!=null);if(v.length<2)continue;if(l.includes("gol")||l.includes("alvo"))out.shotsOn={home:v[0],away:v[1]};else if(l.includes("lado")||l.includes("fora"))out.shotsOff={home:v[0],away:v[1]}}return out}
function sideFromElement(el,teams){
  let node=el, depth=0;
  while(node&&depth<6){
    const s=String(node.getAttribute?.("data-side")||node.getAttribute?.("data-team")||node.className||"").toLowerCase();
    if(/\b(home|casa|mandante|home-team|team-home)\b/.test(s))return"home";
    if(/\b(away|fora|visitante|away-team|team-away)\b/.test(s))return"away";
    try{
      const t=clean(node.querySelector?.("[data-team-name],.team-name,[class*='team-name']")?.textContent||"");
      if(t&&teams.home&&t.toLowerCase()===teams.home.toLowerCase())return"home";
      if(t&&teams.away&&t.toLowerCase()===teams.away.toLowerCase())return"away";
    }catch{}
    node=node.parentElement; depth++;
  }
  return sideFromLabel(clean(el?.textContent||""),teams);
}
function sideFromLabel(label,teams){
  const txt=String(label||"").toLowerCase();
  const home=teams?.home?String(teams.home).toLowerCase():"";
  const away=teams?.away?String(teams.away).toLowerCase():"";
  if(home&&away){
    const hi=txt.indexOf(home), ai=txt.indexOf(away);
    if(hi>=0&&(ai<0||hi<=ai)) return "home";
    if(ai>=0) return "away";
  }
  if(home&&txt.includes(home))return"home";
  if(away&&txt.includes(away))return"away";
  return null;
}
function minuteFromText(t){const m=String(t).match(/(?:^|[^\d])(\d{1,3})(?:\+(\d{1,2}))?\s*(?:['′]|min(?:ute)?s?\b)/i);return m?{minute:Number(m[1]),extraMinute:Number(m[2]||0)}:null}
function minuteFromElement(el){
  if(!el) return null;
  const attrs=[
    el.getAttribute?.("data-minute"),el.getAttribute?.("data-event-minute"),
    el.getAttribute?.("data-time"),el.getAttribute?.("data-clock"),
    el.getAttribute?.("aria-label"),el.getAttribute?.("title")
  ].filter(Boolean).join(" ");
  const direct=minuteFromText(attrs);
  if(direct) return direct;
  const candidates=[];
  try{
    const root=el.closest?.(".timeline-item,.incident,.match-event,.event,.corner-event,.corner,.goal-event,.card-event")||el;
    const nodes=[root,...root.querySelectorAll?.("[data-minute],[data-event-minute],[data-time],[data-clock],time,.minute,.event-minute,.time,.clock")||[]];
    for(const n of nodes){
      const a=[n.getAttribute?.("data-minute"),n.getAttribute?.("data-event-minute"),n.getAttribute?.("data-time"),n.getAttribute?.("data-clock"),n.getAttribute?.("aria-label"),n.getAttribute?.("title"),n.textContent].filter(Boolean).join(" ");
      const m=minuteFromText(a); if(m) candidates.push(m);
    }
  }catch{}
  if(candidates.length) return candidates[0];
  return null;
}
function extractMatchEvents(){
 const teams=extractTeams(),out=[],seen=new Set();
 const nodes=[...document.querySelectorAll("[data-event-type],[data-type],.corner-event,.corner,.goal-event,.card-event,.substitution,.shot-event,.event,.timeline-item,.incident,.match-event")];
 for(const el of nodes){
  const text=clean(el.textContent); const typeAttr=String(el.getAttribute("data-event-type")||el.getAttribute("data-type")||"").toLowerCase();
  if(!/(corner|escante|canto|goal|gol|yellow|amarelo|red|vermelho|substitut|shot|chute|foul|falta|offside|impedimento)/i.test(text+" "+typeAttr))continue;
  const mt=minuteFromText(text)||minuteFromElement(el); if(!mt)continue;
  let type=""; const blob=(typeAttr+" "+text).toLowerCase();
  // Semantic priority is intentional: "Chute no Gol/Alvo" is a shot on target, never a goal.
  if(/corner|escante|canto/.test(blob))type="corner";
  else if(/(?:chute|shot|finaliza(?:ção|cao))[^\n]{0,24}(?:no|a|ao)?\s*(?:gol|alvo|target)|(?:no|on)\s+(?:gol|alvo|target)/.test(blob))type="shot_on";
  else if(/\b(?:goal|gol)\b|\b\d{1,2}\s*[-x]\s*\d{1,2}\b/.test(blob))type="goal";
  else if(/yellow|amarelo/.test(blob))type="yellow";
  else if(/red|vermelho/.test(blob))type="red";
  else if(/substitut/.test(blob))type="substitution";
  else if(/shot|chute|finaliza/.test(blob))type="shot_off";
  else if(/foul|falta/.test(blob))type="foul";
  else if(/offside|impedimento/.test(blob))type="offsides";
  else continue;
  let side=sideFromElement(el,teams)||sideFromLabel(text,teams);
  if(!side&&type!=="corner"&&type!=="goal")continue;
  // playerName: tenta data-attr e padrão "Nome 10'" / "10' Nome"
  let playerName=String(el.getAttribute("data-player")||el.getAttribute("data-player-name")||"").trim();
  if(!playerName){
    const pm=text.match(/(?:^|\n)\s*([A-ZÀ-Ü][A-Za-zÀ-ü.'\-]+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü.'\-]{1,20}){0,2})\s*(?:\d{1,3}(?:\+\d{1,2})?'|\d{1,3}')/);
    const pm2=text.match(/(\d{1,3}(?:\+\d{1,2})?')\s*([A-ZÀ-Ü][A-Za-zÀ-ü.'\-]+(?:\s+[A-ZÀ-Ü][A-Za-zÀ-ü.'\-]{1,20}){0,2})/);
    playerName=(pm&&pm[1])||(pm2&&pm2[2])||"";
    playerName=String(playerName).replace(/\s+/g," ").trim().slice(0,60);
    // Blacklist: labels de evento que o DOM trata como "nome"
    if(/corner|escante|gol|goal|cart|amarelo|vermelho|substit|chute|bloqueado|impedimento|offside|falta|foul|posse|ataque|finaliza|cruzamento|defesa|save|tiro|livre|penal/i.test(playerName)) playerName="";
    // Nomes muito curtos ou só números/símbolos não são jogadores
    if(playerName.length<3 || /^\d+$/.test(playerName)) playerName="";
  }
  const fid=fixtureId()||"unknown";
  const labelHash=text.toLowerCase().replace(/[^a-z0-9]+/g,"").slice(0,24)||"x";
  const id=`${fid}|${type}|${mt.minute>=46?2:1}|${mt.minute}|${mt.extraMinute}|${side||"unk"}|${labelHash}`;
  if(seen.has(id))continue; seen.add(id);
  out.push({
    eventId:id,fixtureId:fid,minute:mt.minute,extraMinute:mt.extraMinute,period:mt.minute>=46?2:1,
    teamName:side==="home"?teams.home:(side==="away"?teams.away:""),side:side||null,type,
    label:text.slice(0,180),playerName:playerName||null,
    playerId:playerName?("name:"+playerName.toLowerCase()):null,
    confidence:side?0.82:0.62,timestamp:Date.now()
  });
 }
 return out.sort((a,b)=>a.period-b.period||a.minute-b.minute||a.extraMinute-b.extraMinute);
}
function tryOpenStats(){return false}

function oddNum(v){const n=Number(String(v??"").replace(",","."));return Number.isFinite(n)&&n>=1.01&&n<=1000?n:null}
function oddFromText(v){const text=String(v??"").replace(/,/g,".");if(/\b\d{1,3}'(?:\+\d{1,2})?(?:[0-9.=|:;\s-]){6,}/.test(text))return null;const m=text.match(/\d+(?:\.\d+)?/g)||[];const nums=m.map(Number).filter(n=>n>=1.01&&n<=1000);return nums.length<=3?nums[nums.length-1]:null}
function oddsMarketType(t){const s=clean(t).toLowerCase();if(/escante|corner|canto/.test(s))return"corners";if(/gol|goals/.test(s))return"goals";if(/cart[aã]o|cards|amarelo|vermelho/.test(s))return"cards";if(/chute|finaliza|shot/.test(s))return"shots";if(/falta|fouls/.test(s))return"fouls";if(/impedimento|offside/.test(s))return"offsides";return"other"}
function extractOddsDOM(){
 const out=[],seen=new Set();
 const clock=extractClock(),minute=clock?.minute??null,extra=clock?.extraMinute||0,period=minute!=null&&minute>45?2:1;
 const push=(market,selection,odd,line,bookmaker,source)=>{
   if(odd==null||odd<1.01||odd>1000) return;
   market=clean(market||""); selection=clean(selection||"");
   if(!market&&!selection) return;
   if(/^(mais|menos)\s*de\s*\??$/i.test(selection)||/\?/.test(selection)) return;
   if(/^mercado$/i.test(market)&&!line) return;
   if(/oddsao vivo|play with responsibility|responsibility|mercado n[aã]o identificado/i.test(market+" "+selection)) return;
   if(/[=|]{2,}/.test(market+" "+selection)) return;
   if(/^(?:probabilidade|probability|fair|implied|chance)$/i.test(market)) return;
   if(/probabilidade|probability|fair probability|implied probability/i.test(selection)) return;
   const key=`${fixtureId()}|${market}|${selection}|${line||""}|${bookmaker||""}|${odd}|${minute??""}|${extra}`;
   if(seen.has(key)) return; seen.add(key);
   out.push({quoteId:key,fixtureId:fixtureId(),minute,extraMinute:extra,period,market:market||"Mercado",marketType:oddsMarketType(market+" "+selection),selection:selection||"Seleção",line:line==null?null:String(line),bookmaker:bookmaker||"Mercado",odds:odd,impliedProbability:Number((1/odd).toFixed(6)),source:source||"dom",timestamp:Date.now()});
 };
 // 1) atributos data-*
 const selectors="[data-odd],[data-odds],[data-price],[data-quota],[data-cotacao],[data-selection][data-line],[data-market] [data-odd],[data-market] [data-price]";
 for(const el of document.querySelectorAll(selectors)){
   const attr=el.getAttribute("data-odd")||el.getAttribute("data-odds")||el.getAttribute("data-price")||el.getAttribute("data-quota")||el.getAttribute("data-cotacao");
   const odd=oddNum(attr); if(odd==null) continue;
   const parent=el.closest("[data-market],[data-market-name],[data-bet],[data-market-type]")||el.parentElement;
   const market=el.getAttribute("data-market")||parent?.getAttribute?.("data-market")||parent?.getAttribute?.("data-market-name")||parent?.querySelector?.("[data-market-name],.market-name")?.textContent||"";
   const selection=el.getAttribute("data-selection")||el.getAttribute("data-outcome")||el.getAttribute("aria-label")||el.getAttribute("title")||"";
   const line=el.getAttribute("data-line")||parent?.getAttribute?.("data-line")||null;
   const bookmaker=el.getAttribute("data-bookmaker")||parent?.getAttribute?.("data-bookmaker")||"";
   if(!el.hasAttribute("data-odd")&&!el.hasAttribute("data-odds")&&!el.hasAttribute("data-price")&&!el.hasAttribute("data-quota")&&!el.hasAttribute("data-cotacao")) continue;
   push(market,selection,odd,line,bookmaker,"dom-attr");
 }
 // 2) texto: "Mais de 8.5 1.85" / Over-Under de escanteios
 const textRoot=document.body?.innerText||"";
 const cornerRe=/(?:escanteios?|corners?|cantos?)[^\n]{0,40}?(?:mais\s*de|over|\+|acima)\s*([0-9]+(?:[.,][0-9]+)?)[^\n]{0,20}?(?:@\s*)?([1-9]\d?(?:[.,]\d{1,3})?)/gi;
 let m;
 while((m=cornerRe.exec(textRoot))){
   const line=m[1].replace(",",".");
   push("Escanteios - Total","Mais de "+line,oddNum(m[2]),line,"SokkerPRO","dom-text");
 }
 const underRe=/(?:escanteios?|corners?|cantos?)[^\n]{0,40}?(?:menos\s*de|under|abaixo)\s*([0-9]+(?:[.,][0-9]+)?)[^\n]{0,20}?(?:@\s*)?([1-9]\d?(?:[.,]\d{1,3})?)/gi;
 while((m=underRe.exec(textRoot))){
   const line=m[1].replace(",",".");
   push("Escanteios - Total","Menos de "+line,oddNum(m[2]),line,"SokkerPRO","dom-text");
 }
 // 3) classes odd/quota com contexto de mercado
 for(const el of document.querySelectorAll("[class*='odd'],[class*='quota'],[class*='price'],[class*='cotacao'],button,span")){
   const cls=String(el.className||"");
   if(!/odd|quota|price|cota|bet|market/i.test(cls)&&el.tagName!=="BUTTON") continue;
   const t=clean(el.textContent||"");
   if(!/^\d{1,2}(?:[.,]\d{1,3})?$/.test(t)) continue;
   const odd=oddNum(t); if(odd==null||odd<1.2||odd>50) continue;
   const parent=el.closest("[class*='market'],[class*='bet'],[class*='row'],li,tr")||el.parentElement;
   const ctx=clean((parent?.textContent||"").slice(0,120));
   if(!/escante|corner|canto|gol|over|under|mais|menos/i.test(ctx)) continue;
   const lineM=ctx.match(/(?:mais\s*de|menos\s*de|over|under)\s*([0-9]+(?:[.,][0-9]+)?)/i);
   const line=lineM?lineM[1].replace(",","."):null;
   const selection=/menos|under/i.test(ctx)?"Menos de "+(line||"?"):/mais|over/i.test(ctx)?"Mais de "+(line||"?"):ctx.slice(0,40);
   push(/escante|corner|canto/i.test(ctx)?"Escanteios - Total":"Mercado",selection,odd,line,"SokkerPRO","dom-class");
 }
 // 4) 1X2 ao vivo: escolhe o melhor trio (overround ~1.0–1.35), evita H2H histórico
 const oneXtwo=/(?:^|\n|\s)(?:1\s*[x×]?\s*2|1x2)?\s*1\s+([1-9]\d?(?:[.,]\d{1,3})?)\s+X\s+([1-9]\d?(?:[.,]\d{1,3})?)\s+2\s+([1-9]\d?(?:[.,]\d{1,3})?)/gi;
 const triples=[];
 while((m=oneXtwo.exec(textRoot))){
   const o1=oddNum(m[1]), ox=oddNum(m[2]), o2=oddNum(m[3]);
   if(o1==null||ox==null||o2==null) continue;
   const sum=1/o1+1/ox+1/o2;
   if(sum<0.95||sum>1.45) continue; // descarta trios incoerentes / históricos poluídos
   triples.push({o1,ox,o2,sum,idx:m.index});
 }
 if(triples.length){
   // prefere overround mais próximo de 1.08 e ocorrência mais recente no texto
   triples.sort((a,b)=>Math.abs(a.sum-1.08)-Math.abs(b.sum-1.08)||b.idx-a.idx);
   const best=triples[0];
   push("Resultado Final","1 (Casa)",best.o1,null,"SokkerPRO","dom-1x2");
   push("Resultado Final","X (Empate)",best.ox,null,"SokkerPRO","dom-1x2");
   push("Resultado Final","2 (Fora)",best.o2,null,"SokkerPRO","dom-1x2");
 }
 // 5) Odd justa (mercado separado — não mistura overround com book)
 const fairRe=/(?:odd\s*justa|fair\s*odd)\s*([1-9]\d?(?:[.,]\d{1,3})?)/gi;
 const fairCtx=textRoot.slice(0,12000);
 let fm; const fairs=[];
 while((fm=fairRe.exec(fairCtx))) fairs.push(oddNum(fm[1]));
 // pega o último bloco de 3 odd justas 1/X/2 (não EV+ 1X/12/X2)
 if(fairs.length>=3){
   const block=fairs.slice(0,3);
   const fsum=block.reduce((a,o)=>a+1/o,0);
   if(fsum>=0.9&&fsum<=1.2){
     push("Resultado Final (Odd Justa)","1 (Casa)",block[0],null,"SokkerPRO-Fair","dom-fair");
     push("Resultado Final (Odd Justa)","X (Empate)",block[1],null,"SokkerPRO-Fair","dom-fair");
     push("Resultado Final (Odd Justa)","2 (Fora)",block[2],null,"SokkerPRO-Fair","dom-fair");
   }
 }
 // 6) Escanteios Over/Under — odds reais de apostas (1.15–6.5), nunca minuto/placar
 const isSaneCornerOdd=(odd,line)=>{
   if(odd==null||!Number.isFinite(odd)) return false;
   if(odd<1.15||odd>6.5) return false; // 87/89/9.50 falsos
   const ln=Number(line);
   if(!Number.isFinite(ln)||ln<6||ln>14) return false; // evita 2.5 (gols)
   if(Math.abs(odd-ln)<0.08) return false; // "Mais de 9.5 · 9.50" = linha colada
   return true;
 };
 const ouCorner=/(?:^|\n|\s)(?:over|mais\s*de)\s*([0-9]+(?:[.,][0-9]+)?)\s+(?:@\s*)?([1-9](?:[.,]\d{1,3})?)/gi;
 while((m=ouCorner.exec(textRoot))){
   const line=m[1].replace(",",".");
   const odd=oddNum(m[2]);
   if(!isSaneCornerOdd(odd,line)) continue;
   push("Escanteios - Total","Mais de "+line,odd,line,"SokkerPRO","dom-corner-ou");
 }
 const uuCorner=/(?:^|\n|\s)(?:under|menos\s*de)\s*([0-9]+(?:[.,][0-9]+)?)\s+(?:@\s*)?([1-9](?:[.,]\d{1,3})?)/gi;
 while((m=uuCorner.exec(textRoot))){
   const line=m[1].replace(",",".");
   const odd=oddNum(m[2]);
   if(!isSaneCornerOdd(odd,line)) continue;
   push("Escanteios - Total","Menos de "+line,odd,line,"SokkerPRO","dom-corner-ou");
 }
 // 7) Tabela H2H: "Over 9 Under 10" + par de odds decimais sane
 const hdr=textRoot.match(/over\s*([0-9]+(?:[.,][0-9]+)?)\s*under\s*([0-9]+(?:[.,][0-9]+)?)/i);
 if(hdr){
   const overLine=hdr[1].replace(",","."), underLine=hdr[2].replace(",",".");
   const after=textRoot.slice(hdr.index+hdr[0].length, hdr.index+hdr[0].length+120);
   // só pares tipo 2.62 1.44 (ambos < 7)
   const cells=after.match(/\b([1-6](?:[.,]\d{1,3})?)\s*[=]?\s*([1-6](?:[.,]\d{1,3})?)\b/);
   if(cells){
     const o1=oddNum(cells[1]), o2=oddNum(cells[2]);
     if(isSaneCornerOdd(o1,overLine)) push("Escanteios - Total","Mais de "+overLine,o1,overLine,"SokkerPRO","dom-h2h-ou");
     if(isSaneCornerOdd(o2,underLine)) push("Escanteios - Total","Menos de "+underLine,o2,underLine,"SokkerPRO","dom-h2h-ou");
   }
 }
 
 // 9.2.9: text fallback — decimal odds near 1/X/2 or Casa/Empate/Fora
 try{
   const body=(document.body?.innerText||"").slice(0,60000);
   const blocks=body.split(/\n+/).map(s=>s.trim()).filter(Boolean);
   for(let i=0;i<blocks.length;i++){
     const line=blocks[i];
     // "1 1.85" / "X 3.40" / "2 4.20" or "Casa 1.85"
     let m=line.match(/^(1|X|2|Casa|Empate|Fora|Home|Draw|Away)\s+(\d{1,2}[.,]\d{2,3})$/i);
     if(m){
       const sel=m[1], odd=oddNum(m[2]);
       push("Resultado Final", sel, odd, null, "DOM-text", "dom-text");
       continue;
     }
     // "1.85 3.40 4.20" after a market header
     m=line.match(/^(\d{1,2}[.,]\d{2,3})\s+(\d{1,2}[.,]\d{2,3})\s+(\d{1,2}[.,]\d{2,3})$/);
     if(m){
       const prev=(blocks[i-1]||"").toLowerCase();
       if(/1x2|resultado|match result|vencedor|moneyline/i.test(prev)||i>0){
         push("Resultado Final","1",oddNum(m[1]),null,"DOM-text","dom-text");
         push("Resultado Final","X",oddNum(m[2]),null,"DOM-text","dom-text");
         push("Resultado Final","2",oddNum(m[3]),null,"DOM-text","dom-text");
       }
     }
   }
 }catch{}
 return out;
}

function classifyStatStatus(value, opts={}){
  // Classification states for recovery pipeline:
  // UNKNOWN  - element not found / never observed
  // MISSING  - key expected but value absent after capture
  // ZERO     - explicit zero observed in DOM
  // RECOVERED- value recovered from secondary source / previous snapshot
  // CONFIRMED- value present with high confidence from primary DOM
  if(value==null || (typeof value==="object" && value.home==null && value.away==null)){
    return opts.expected ? "MISSING" : "UNKNOWN";
  }
  const h = value.home, a = value.away;
  const bothZero = (h===0||h===0.0) && (a===0||a===0.0);
  if(bothZero) return opts.explicitZero ? "ZERO" : "ZERO";
  if(opts.recovered) return "RECOVERED";
  if(opts.confidence!=null && opts.confidence>=0.85) return "CONFIRMED";
  if(opts.confidence!=null && opts.confidence>=0.55) return "RECOVERED";
  return "CONFIRMED";
}


const CHART_TAB_ALIASES={
  macd_xg:["macd xg","macd-xg","macd"],
  xg:["xg","expected goals","gols esperados"],
  ai_analysis:["analise de ia","análise de ia","analise ia","análise ia","ai analysis","ia"],
  standard:["grafico padrao","gráfico padrão","grafico padrão","gráfico padrao","standard chart","padrao","padrão"],
  pressure_bar:["barra de pressao","barra de pressão","pressure bar","pressao","pressão"],
  dangerous_attacks:["ataques perigosos","dangerous attacks","perigosos"],
  attacks:["ataques","attacks"]
};

function classifyChartTab(label){
  const n=normChart(label);
  if(!n)return "unknown";
  // More specific first
  const order=["macd_xg","dangerous_attacks","pressure_bar","ai_analysis","standard","xg","attacks"];
  for(const id of order){
    const aliases=CHART_TAB_ALIASES[id]||[];
    if(aliases.some(a=>n===a||n.includes(a))) return id;
  }
  return "unknown";
}
function normChart(s){
  return String(s??"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/\s+/g," ").trim();
}

function discoverChartTabs(){
  const out=[],seen=new Set();
  // SokkerPRO real tabs: .slide-navigation .slide-btn
  const preferred=[...document.querySelectorAll(".slide-navigation .slide-btn, .slide-navigation-container .slide-btn, button.slide-btn")];
  const fallback=[...document.querySelectorAll("button,[role='tab'],[role='button']")];
  const els=preferred.length?preferred:fallback;
  for(const el of els){
    const label=clean(el.textContent||el.getAttribute("aria-label")||el.title||"");
    if(!label||label.length>48)continue;
    const id=classifyChartTab(label);
    if(id==="unknown")continue;
    const st=String(el.getAttribute("style")||"");
    const active=el.matches("[aria-selected='true'],.active,.selected")||/active|selected|current/i.test(String(el.className||""))||/will-change/i.test(st);
    if(seen.has(id))continue; seen.add(id);
    out.push({id,label,active,tag:el.tagName,cls:String(el.className||"").slice(0,80)});
  }
  return out.slice(0,20);
}

function extractVisibleChartSeries(){
  const series=[],seen=new Set();
  const push=(p)=>{const key=JSON.stringify(p);if(seen.has(key))return;seen.add(key);series.push(p)};

  // 0) Chart.js instances on #line-chart canvases (SokkerPRO standard/xg charts)
  try{
    const canvases=[...document.querySelectorAll("canvas#line-chart, canvas.line-chart-canvas, .line-chart-canvas canvas, canvas")];
    for(const c of canvases){
      let ch=null;
      try{if(typeof Chart!=="undefined"&&Chart.getChart) ch=Chart.getChart(c);}catch{}
      if(!ch) try{ch=c.__chartjs__||c.chart||null;}catch{}
      if(!ch||!ch.data) continue;
      const labels=ch.data.labels||[];
      (ch.data.datasets||[]).forEach((d,di)=>{
        const name=clean(d.label||("dataset-"+di));
        (d.data||[]).forEach((v,i)=>{
          let minute=null,value=null,home=null,away=null;
          if(v!=null&&typeof v==="object"){
            minute=Number(v.x??v.minute??labels[i]);
            value=Number(v.y??v.value);
          }else{
            minute=Number(labels[i]??i);
            value=Number(v);
          }
          if(Number.isFinite(value)) push({minute:Number.isFinite(minute)?minute:i,value,series:name,src:"chartjs"});
        });
      });
    }
  }catch{}

  // 1) Explicit data attributes
  for(const el of document.querySelectorAll("[data-minute],[data-x][data-y],[data-point],[data-value]")){
    const minute=Number(el.getAttribute("data-minute")??el.getAttribute("data-x")??el.getAttribute("data-point"));
    const value=Number(el.getAttribute("data-value")??el.getAttribute("data-y"));
    const home=Number(el.getAttribute("data-home-value")??el.getAttribute("data-home"));
    const away=Number(el.getAttribute("data-away-value")??el.getAttribute("data-away"));
    const name=clean(el.getAttribute("data-series")||el.getAttribute("data-team")||el.getAttribute("data-name")||"");
    if(Number.isFinite(minute)&&minute>=0&&minute<=130){
      if(Number.isFinite(value)) push({minute,value,series:name||null,src:"attr"});
      else if(Number.isFinite(home)||Number.isFinite(away)) push({minute,home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null,series:name||null,src:"attr"});
    }
  }

  // 2) SVG circles / rects with numeric cx/cy (normalized later by chart bounds if available)
  for(const el of document.querySelectorAll("svg circle[cx][cy], svg rect[x][y][data-value], svg circle[data-value]")){
    const minute=Number(el.getAttribute("data-minute")??el.getAttribute("data-x")??el.getAttribute("cx"));
    const value=Number(el.getAttribute("data-value")??el.getAttribute("data-y")??el.getAttribute("cy"));
    if(Number.isFinite(minute)&&Number.isFinite(value)&&el.hasAttribute("data-value"))
      push({minute,value,series:clean(el.getAttribute("data-series")||"")||null,src:"svg-node"});
  }

  // 3) SVG polyline / polygon points="x,y x,y ..."
  for(const el of document.querySelectorAll("svg polyline[points], svg polygon[points]")){
    const raw=el.getAttribute("points")||"";
    const pts=raw.trim().split(/[\s]+/).map(p=>{const [x,y]=p.split(",").map(Number);return {x,y}}).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
    if(pts.length<2||pts.length>200) continue;
    const name=clean(el.getAttribute("data-series")||el.getAttribute("class")||"polyline");
    // Keep raw pixel series; consumer can scale. Tag as pixel space.
    pts.forEach((p,i)=>push({index:i,x:p.x,y:p.y,series:name,src:"polyline"}));
  }

  // 4) Embedded JSON in script tags (chart configs)
  for(const sc of document.querySelectorAll("script[type='application/json'],script[type='application/ld+json']")){
    const t=String(sc.textContent||"");
    if(t.length<20||t.length>200000) continue;
    if(!/minute|series|datasets|pressure|xg|macd/i.test(t)) continue;
    try{
      const j=JSON.parse(t);
      const walk=(node,depth=0)=>{
        if(!node||depth>8)return;
        if(Array.isArray(node)){
          // array of {minute,value} or [minute,value]
          if(node.length&&node.length<=200){
            if(typeof node[0]==="object"&&node[0]&&("minute" in node[0]||"x" in node[0])){
              for(const p of node){
                const minute=Number(p.minute??p.x??p.m);
                const value=Number(p.value??p.y??p.v);
                if(Number.isFinite(minute)&&Number.isFinite(value)&&minute>=0&&minute<=130) push({minute,value,src:"json"});
              }
            }
          }
          node.slice(0,50).forEach(x=>walk(x,depth+1));
          return;
        }
        if(typeof node==="object"){
          for(const k of Object.keys(node).slice(0,40)) walk(node[k],depth+1);
        }
      };
      walk(j);
    }catch{}
  }

  // 5) Highcharts / Chart.js global leftovers
  try{
    const charts=window.Highcharts?.charts||[];
    for(const ch of charts){
      if(!ch) continue;
      for(const s of (ch.series||[])){
        const name=clean(s.name||"");
        for(const pt of (s.points||[]).slice(0,200)){
          const minute=Number(pt.x??pt.category);
          const value=Number(pt.y);
          if(Number.isFinite(value)) push({minute:Number.isFinite(minute)?minute:null,value,series:name||null,src:"highcharts"});
        }
      }
    }
  }catch{}
  try{
    if(Array.isArray(window.Chart?.instances)||typeof window.Chart!=="undefined"){
      const instances=window.Chart?.instances||{};
      for(const key of Object.keys(instances||{})){
        const ch=instances[key];
        const ds=ch?.data?.datasets||[];
        const labels=ch?.data?.labels||[];
        ds.forEach((d,di)=>{
          (d.data||[]).forEach((v,i)=>{
            const value=Number(Array.isArray(v)?v[1]:v);
            const minute=Number(Array.isArray(v)?v[0]:labels[i]);
            if(Number.isFinite(value)) push({minute:Number.isFinite(minute)?minute:i,value,series:clean(d.label||"dataset-"+di),src:"chartjs"});
          });
        });
      }
    }
  }catch{}

  return series.slice(0,800);
}

function extractPressureBars(){
  const bars={};
  // Real SokkerPRO DOM (from saved HTML):
  // .pressure-block > .pressure-block-header > .pressure-pct + .pressure-interval
  // .pressure-bar > .pressure-seg.seg-green (home flex-grow) + .seg-red (away flex-grow)
  const blocks=document.querySelectorAll(".pressure-block");
  for(const block of blocks){
    const interval=clean(block.querySelector(".pressure-interval")?.textContent||"");
    const im=interval.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
    if(!im)continue;
    const key=im[1]+"-"+im[2];
    const pctTxt=clean(block.querySelector(".pressure-pct")?.textContent||"");
    const pct=pctTxt==="-"?null:Number(String(pctTxt).replace("%","").replace(",","."));
    const green=block.querySelector(".pressure-seg.seg-green, .seg-green");
    const red=block.querySelector(".pressure-seg.seg-red, .seg-red");
    const readGrow=el=>{
      if(!el) return null;
      const direct=Number(el.style.flexGrow);
      if(Number.isFinite(direct)&&direct>0) return direct;
      const st=el.getAttribute("style")||"";
      const m=st.match(/flex-grow\s*:\s*([\d.]+)/i);
      return m?Number(m[1]):null;
    };
    let home=readGrow(green);
    let away=readGrow(red);
    // Fallback: dominant pct on the right is often the larger side; use flex if available
    if(home==null&&away==null&&Number.isFinite(pct)){
      // Without colors mapping, store dominant only under home and complement away
      home=pct; away=Math.max(0,100-pct);
    }
    if(block.querySelector(".pressure-bar-empty")||pctTxt==="-"){
      bars[key]={home:null,away:null,empty:true};
    }else{
      bars[key]={home,away,pct:Number.isFinite(pct)?pct:null};
    }
  }
  return bars;
}

function detectActiveChartFromSlides(){
  // Visible .slide panel title / canvas / pressure-grid
  const slides=[...document.querySelectorAll(".slide, .chart-container, .pressure-chart, .standard-chart-container, .macd-wrapper")];
  for(const slide of slides){
    const st=String(slide.getAttribute("style")||"");
    if(/display\s*:\s*none/i.test(st)) continue;
    if(slide.offsetParent===null&&slide.tagName!=="BODY") continue;
    if(slide.querySelector(".pressure-grid, .pressure-block")) return {id:"pressure_bar",label:"BARRA DE PRESSÃO"};
    if(slide.querySelector(".macd-wrapper, .macd-faixa, .macd-head")) return {id:"macd_xg",label:"MACD XG"};
    const title=clean(slide.querySelector(".chart-title-center")?.textContent||"");
    if(/xg/i.test(title)) return {id:"xg",label:title||"XG"};
    if(/padr[aã]o|standard/i.test(title)) return {id:"standard",label:title||"Padrão"};
    if(/ia|an[aá]lise/i.test(title)) return {id:"ai_analysis",label:title||"ANÁLISE DE IA"};
    if(slide.querySelector("canvas#line-chart, canvas")){
      // generic visible line chart
      if(/ataque perigos|dangerous/i.test(slide.innerText||"")) return {id:"dangerous_attacks",label:"ATAQUES PERIGOSOS"};
      if(/\bataques\b/i.test(slide.innerText||"")) return {id:"attacks",label:"ATAQUES"};
    }
  }
  return null;
}

function extractCharts(){
  const tabs=discoverChartTabs();
  let active=tabs.find(t=>t.active)||null;
  const fromSlide=detectActiveChartFromSlides();
  if(fromSlide) active={id:fromSlide.id,label:fromSlide.label,active:true};
  const activeId=active?.id||fromSlide?.id||null;
  const series=extractVisibleChartSeries();
  const pressureBars=extractPressureBars();
  const main=document.querySelector("main,[role='main'],.content,#content")||document.body;
  const panelText=clean(main?.innerText||"").slice(0,4000);
  const hasMacd=activeId==="macd_xg"||/macd/i.test(panelText)||tabs.some(t=>t.id==="macd_xg");
  const hasAi=activeId==="ai_analysis"||/an[aá]lise de ia|ai analysis/i.test(panelText)||tabs.some(t=>t.id==="ai_analysis");
  const uniq=[],seenTab=new Set();
  for(const t of tabs){if(seenTab.has(t.id))continue;seenTab.add(t.id);uniq.push(t);}
  const net=lastChartNetwork||{series:[],pressureBars:{},urls:[],at:0};
  if(Array.isArray(net.series)) for(const p of net.series) series.push(p);
  const mergedPressure={...pressureBars,...(net.pressureBars||{})};
  // Pressure bars as series (always, alongside any chartjs series)
  for(const [k,v] of Object.entries(mergedPressure)){
    const m=String(k).match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/)||String(k).match(/(\d{1,2})-(\d{1,2})/);
    if(!m) continue;
    if(v&&v.empty&&v.home==null&&v.away==null) continue;
    const mid=(Number(m[1])+Number(m[2]))/2;
    series.push({minute:mid,home:v?.home??null,away:v?.away??null,interval:m[1]+"-"+m[2],series:"pressure",src:"pressure-block"});
  }
  // Limpeza de séries svg-path / svg-poly: agrupa por minuto e série, descarta ruído
  const cleaned=[];
  const byKey=new Map();
  for(const p of series){
    const src=String(p.src||"");
    if(src==="svg-path"||src==="svg-poly"){
      const minute=Number(p.minute);
      if(!Number.isFinite(minute)||minute<0||minute>130) continue;
      const value=Number(p.value);
      // Valores normalizados 0–1 do SVG ou valores “de dados” plausíveis
      if(!Number.isFinite(value)) continue;
      if(value<-2||value>100) continue;
      const seriesName=String(p.series||"svg");
      const bucket=Math.round(minute);
      const key=`${src}|${seriesName}|${bucket}`;
      const prev=byKey.get(key);
      // Mantém o ponto mais “central” do minuto (menos extremo)
      if(!prev||Math.abs(value-0.5)<Math.abs(Number(prev.value)-0.5)){
        byKey.set(key,{...p,minute:bucket,value:Number(value.toFixed(4)),src:src,series:seriesName});
      }
      continue;
    }
    cleaned.push(p);
  }
  for(const v of byKey.values()) cleaned.push(v);
  // Dedupe final
  const dedup=[],seenS=new Set();
  for(const p of cleaned){
    const key=(p.src||"")+"|"+(p.series||"")+"|"+(p.minute??"")+"|"+(p.value??"")+"|"+(p.home??"")+"|"+(p.away??"");
    if(seenS.has(key)) continue; seenS.add(key); dedup.push(p);
  }
  series.length=0; for(const p of dedup) series.push(p);
  const sources=[...new Set(series.map(s=>s.src).filter(Boolean))];
  if(net.activeLabel&&!active?.label){ /* keep */ }
  return {
    schema:"cornerai-charts-1",
    tabs:uniq,
    activeId,
    activeLabel:active?.label||fromSlide?.label||net.activeLabel||null,
    seriesCount:Math.max(series.length, Object.keys(mergedPressure||{}).length),
    series:series.slice(0,400),
    pressureBars:mergedPressure,
    pressureIntervals:Object.keys(mergedPressure||{}).length,
    networkUrls:Array.isArray(net.urls)?net.urls.slice(0,10):[],
    signals:{hasMacd,hasAi,tabCount:uniq.length,sources,networkAt:net.at||0,pressureBlocks:Object.keys(mergedPressure).length},
    capturedAt:Date.now()
  };
}

function build(){
 const teams=extractTeams(),status=detectMatchStatus(),clock=extractClock(),domEvents=extractMatchEvents();
 const textEvents=extractTextTimelineEvents();
 const _seenEv=new Set(domEvents.map(e=>`${e.type}|${e.minute}|${e.extraMinute||0}|${e.side||""}`));
 for(const te of textEvents){
   const k=`${te.type}|${te.minute}|${te.extraMinute||0}|${te.side||""}`;
   if(_seenEv.has(k)) continue;
   const clash=domEvents.some(e=>e.type===te.type&&e.minute===te.minute&&(e.extraMinute||0)===(te.extraMinute||0)&&e.side);
   if(clash&&!te.side) continue;
   _seenEv.add(k); domEvents.push(te);
 }
 // Finished pages: avoid two failure modes —
 //  (1) stale early clock (e.g. 2') → prefer latest event minute
 //  (2) mid-game freeze (e.g. 83') on a completed match → keep last live minute
 //     but mark display as FT so UI/diagnostics don't look like the game stopped at 83'.
 const latestEvent=domEvents.slice().sort((a,b)=>(Number(b.minute)-Number(a.minute))||((Number(b.extraMinute)||0)-(Number(a.extraMinute)||0)))[0];
 let effectiveClock=clock;
 let lastLiveMinute=clock?.minute??null;
 let lastLiveExtra=clock?.extraMinute||0;
 if(status==="finished"){
   const eventMin=latestEvent?Number(latestEvent.minute):null;
   const eventExtra=latestEvent?Number(latestEvent.extraMinute||0):0;
   const domMin=clock?.minute!=null?Number(clock.minute):null;
   // Prefer the higher of DOM vs latest event (never regress to a stale early clock)
   let m=domMin, ex=clock?.extraMinute||0;
   if(eventMin!=null && (m==null || eventMin>m || (eventMin===m && eventExtra>ex))){
     m=eventMin; ex=eventExtra;
   }
   // If finished and clock is absurdly early (<30) but we have late events, trust events
   if((m==null || m<30) && eventMin!=null && eventMin>=45){ m=eventMin; ex=eventExtra; }
   effectiveClock={minute:m,extraMinute:ex};
   lastLiveMinute=m;
   lastLiveExtra=ex;
 }
 // 9.2.10: merge timeline text events into matchEvents (corners often only in free text)
 let mergedEvents=Array.isArray(domEvents)?domEvents.slice():[];
 if(Array.isArray(textEvents)&&textEvents.length){
   const seenE=new Set(mergedEvents.map(e=>`${e.type}|${e.minute}|${e.extraMinute||0}|${e.side||""}`));
   for(const e of textEvents){
     const k=`${e.type}|${e.minute}|${e.extraMinute||0}|${e.side||""}`;
     if(seenE.has(k)) continue; seenE.add(k); mergedEvents.push(e);
   }
 }
 const snap={version:VERSION,fixtureId:fixtureId(),url:location.href,home:teams.home,away:teams.away,teamConfidence:teams.confidence,minute:effectiveClock?.minute??null,extraMinute:effectiveClock?.extraMinute||0,score:extractScore(),liveStatus:status,dataMode:status==="finished"?"historical":status==="live"?"live":"unknown",matchEvents:mergedEvents,historicalTextEvents:textEvents,lastLiveMinute,lastLiveExtra,clockDisplay:status==="finished"?"FT":null};
 snap.cornerIndicators=extractCornerIndicators();
 const rowStats=extractRows(),textStats=extractStatsText(),tableStats=extractTables(),shotStats=extractShotCards();
 for(const src of [textStats,tableStats,shotStats])for(const [k,v] of Object.entries(src))if(v&&rowStats[k]==null)rowStats[k]=v;
 // Derive substitutions / cards / offsides from timeline events when the stats row is absent.
 if(Array.isArray(domEvents) && domEvents.length){
   let sh=0,sa=0,yh=0,ya=0,rh=0,ra=0,oh=0,oa=0;
   for(const e of domEvents){
     const t=String(e.type||"").toLowerCase();
     const label=String(e.label||"").toLowerCase();
     const side=e.side==="away"?"away":(e.side==="home"?"home":null);
     if(!side) continue;
     if(t==="substitution"||t==="subs"||/substitui|substitution/.test(label)){ if(side==="home") sh++; else sa++; }
     else if(t==="yellow"||t==="yellow_card"||t==="card_yellow"||/amarelo|yellow/.test(label)){ if(side==="home") yh++; else ya++; }
     else if(t==="red"||t==="red_card"||t==="card_red"||t==="second_yellow"||/vermelho|red card|expuls/.test(label)){ if(side==="home") rh++; else ra++; }
     else if(t==="offsides"||t==="offside"||/impedimento|offside/.test(label)){ if(side==="home") oh++; else oa++; }
   }
   if(rowStats.subs==null && (sh>0||sa>0)) rowStats.subs={home:sh,away:sa,derivedFromEvents:true};
   if(rowStats.yellow==null && (yh>0||ya>0)) rowStats.yellow={home:yh,away:ya,derivedFromEvents:true};
   if(rowStats.red==null && (rh>0||ra>0)) rowStats.red={home:rh,away:ra,derivedFromEvents:true};
   if(rowStats.offsides==null && (oh>0||oa>0)) rowStats.offsides={home:oh,away:oa,derivedFromEvents:true};
   // Explicit zeros only when match is late/finished and we saw a timeline but no cards
   if(rowStats.red==null && (status==="finished"||(Number(effectiveClock?.minute)||0)>=70) && domEvents.length>=5){
     rowStats.red={home:rh,away:ra,derivedFromEvents:true,explicitZero:rh===0&&ra===0};
   }
   if(rowStats.subs==null && (status==="finished"||(Number(effectiveClock?.minute)||0)>=60) && domEvents.length>=8){
     rowStats.subs={home:sh,away:sa,derivedFromEvents:true,explicitZero:sh===0&&sa===0};
   }
 }

 // [v6.9.9.83] Derive shots = shotsOn + shotsOff when total shots row is hidden
 if(rowStats.shots==null && rowStats.shotsOn && rowStats.shotsOff){
   const onH=Number(rowStats.shotsOn.home), onA=Number(rowStats.shotsOn.away);
   const offH=Number(rowStats.shotsOff.home), offA=Number(rowStats.shotsOff.away);
   if([onH,onA,offH,offA].every(Number.isFinite)){
     rowStats.shots={home:onH+offH,away:onA+offA,derivedFromParts:true};
   }
 }
 // Deep text scan for remaining MISSING canonical stats (SokkerPRO sometimes hides rows)
 try{
   const deep=extractHiddenStatPairs();
   for(const [k,v] of Object.entries(deep)){
     if(rowStats[k]==null && v) rowStats[k]={...v,source:"deep-text"};
   }
 }catch{}

 // xG gets its own strict extractor. Generic numeric rows are intentionally
 // not allowed to win over an exact xG-labelled source.
 const xg=extractXG();
 if(xg?.home!=null&&xg?.away!=null){ rowStats.xg={home:xg.home,away:xg.away}; snap.xgMeta=xg; }
 else if(snap.cornerIndicators?.xg?.home!=null&&snap.cornerIndicators?.xg?.away!=null){
   const ih=Number(snap.cornerIndicators.xg.home),ia=Number(snap.cornerIndicators.xg.away);
   // Zero-only indicator is not strong enough to claim xG when the strict extractor found nothing.
   if(!(ih===0&&ia===0)){
     rowStats.xg=snap.cornerIndicators.xg;
     snap.xgMeta={home:ih,away:ia,source:'dom',confidence:.72,method:'indicator-fallback'};
   }
 }
 // Light imputation: when xG is still missing, estimate from shots profile.
 // Conservative coefficients — never overrides real xG.
 if((!rowStats.xg || rowStats.xg.home==null || rowStats.xg.away==null) && rowStats.shotsOn){
   const onH=Number(rowStats.shotsOn?.home), onA=Number(rowStats.shotsOn?.away);
   const offH=Number(rowStats.shotsOff?.home??rowStats.shots?.home), offA=Number(rowStats.shotsOff?.away??rowStats.shots?.away);
   if(Number.isFinite(onH)&&Number.isFinite(onA)){
     const impH=Number((onH*0.22 + (Number.isFinite(offH)?offH*0.03:0)).toFixed(2));
     const impA=Number((onA*0.22 + (Number.isFinite(offA)?offA*0.03:0)).toFixed(2));
     if(impH>0||impA>0){
       rowStats.xg={home:impH,away:impA};
       snap.xgMeta={home:impH,away:impA,source:'imputed',confidence:0.42,method:'shots-imputation-v1'};
     }
   }
 }
 snap.extendedStats=extractExtendedRows();
 // Keep every canonical provider metric, including rows whose CSS label differs.
 Object.assign(snap,rowStats);
 // Explicit per-stat classification (UNKNOWN/ZERO/MISSING/RECOVERED/CONFIRMED)
 const STAT_KEYS_LOCAL=["attacks","dangerous","shots","shotsOn","shotsOff","corners","xg","fouls","offsides","yellow","red","subs","crosses","saves","passes","passesFailed","possession"];
 const statMeta={};
 for(const k of STAT_KEYS_LOCAL){
   const v=rowStats[k];
   const isXg=k==="xg";
   const conf=isXg&&snap.xgMeta?Number(snap.xgMeta.confidence||0): (v&&v.home!=null&&v.away!=null?0.9:0);
   const recovered=isXg&&snap.xgMeta&&snap.xgMeta.method==="indicator-fallback";
   const explicitZero=v&&v.home===0&&v.away===0;
   statMeta[k]={
     status:classifyStatStatus(v,{expected:true,confidence:conf,recovered,explicitZero}),
     home:v?.home??null,
     away:v?.away??null,
     confidence:conf,
     source:isXg&&snap.xgMeta?String(snap.xgMeta.source||"dom"):"dom",
     method:isXg&&snap.xgMeta?String(snap.xgMeta.method||"row"):"row"
   };
 }
 // Mark xG multi-source conflict if present
 if(snap.xgMeta?.conflict){
   statMeta.xg.conflict=snap.xgMeta.conflict;
   if(statMeta.xg.status==="CONFIRMED") statMeta.xg.status="RECOVERED";
 }
 snap.statMeta=statMeta;
 snap.charts=extractCharts();
 snap.odds=extractOddsDOM();
 return snap}
function isCriticalWindow(minute,extra){
  const m=Number(minute); if(!Number.isFinite(m)) return false;
  const e=Number(extra)||0;
  // Janela A maximizada: 28' → fim do 1º tempo (inclui todos acréscimos)
  if(m>=28 && m<=45) return true;
  if(m===45) return true;
  // Janela B maximizada: 78' → FT + prorrogação
  if(m>=78 && m<=90) return true;
  if(m===90) return true;
  if(m>90 && m<=130) return true;
  return false;
}
function captureMinInterval(snap){
  if(snap?.liveStatus==="live"&&isCriticalWindow(snap.minute,snap.extraMinute)) return 220;
  if(snap?.liveStatus==="live") return 1200;
  return 750;
}
function captureHeartbeatMs(snap){
  if(snap?.liveStatus==="live"&&isCriticalWindow(snap.minute,snap.extraMinute)) return 700;
  if(snap?.liveStatus==="live") return 6500;
  return 25000;
}
function capturePulseMs(snap){
  if(snap?.liveStatus==="live"&&isCriticalWindow(snap.minute,snap.extraMinute)) return 450;
  if(snap?.liveStatus==="live") return 1400;
  return 1400;
}
let __lastPulseMs=1000;
function retunePulse(snap){
  const ms=capturePulseMs(snap);
  if(ms===__lastPulseMs) return;
  __lastPulseMs=ms;
  if(!captureArmed) return;
  clearInterval(capturePulseTimer);
  capturePulseTimer=setInterval(()=>capture(false),ms);
}
let lastCaptureAttempt=0,lastCaptureSuccess=0,lastCaptureError=null,lastDispatchAt=0,lastDispatchResult=null;

/** 9.2.2 — caminho direto: monta snapshot mínimo e envia DOM_SNAPSHOT sem throttling/gates. */
async function forceIngestSnapshot(reason="force"){
  try{
    captureArmed=true;
    manualCaptureSession=true;
    lastCaptureAttempt=Date.now();
    lastCapture=Date.now();
    const snap=typeof build==="function"?build():{};
    if(!snap||typeof snap!=="object") return {ok:false,reason:"no_build"};
    if(!snap.fixtureId) snap.fixtureId=fixtureId();
    if(!snap.url) snap.url=location.href;
    // Garantir liveStatus a partir do relógio
    try{
      const m=Number(snap.minute);
      if((!snap.liveStatus||snap.liveStatus==="unknown"||snap.liveStatus==="inactive") && Number.isFinite(m) && m>=1 && m<=120){
        snap.liveStatus="live";
        snap.dataMode="live";
      }
    }catch{}
    const meta={url:location.href,captureReason:String(reason||"force"),capturedAt:Date.now(),forceIngest:true};
    const r=await send("DOM_SNAPSHOT",snap,meta);
    lastBackgroundAck=r||null;
    lastDispatchResult=r||null;
    lastDispatchAt=Date.now();
    if(r?.ok||r?.accepted){
      lastCaptureSuccess=Date.now();
      lastCaptureError=null;
      return {ok:true,force:true,fixtureId:snap.fixtureId||null,ack:r};
    }
    lastCaptureError=r?.error||r?.reason||"force_ingest_rejected";
    return {ok:false,force:true,reason:lastCaptureError,ack:r||null,fixtureId:snap.fixtureId||null};
  }catch(e){
    lastCaptureError=e?.message||String(e);
    return {ok:false,force:true,error:lastCaptureError};
  }
}

async function capture(force=false){
 if(!captureArmed&&!force)return {ok:false,skipped:true,reason:"not_armed"};
 const now=Date.now();
 lastCaptureAttempt=now; lastCaptureError=null;
 let probeMin=null,probeExtra=0,probeLive=null;
 try{const clk=typeof extractClock==="function"?extractClock():null;if(clk){probeMin=clk.minute;probeExtra=clk.extraMinute||0}}catch{}
 const provisional={liveStatus:probeLive||"live",minute:probeMin,extraMinute:probeExtra};
 const minGap=captureMinInterval(provisional);
 if(!force&&now-lastCapture<minGap)return {ok:false,skipped:true,reason:"throttled"};
 lastCapture=now;
 try{
  const snap=build();
  const useful=!!(snap.fixtureId||snap.home||snap.away||snap.score||snap.matchEvents.length||Object.keys(snap).some(k=>labels[k]));
  if(!useful){lastCaptureError="empty_snapshot";return {ok:false,reason:"empty_snapshot"};}
  if(snap.fixtureId&&lastKnownFid&&String(snap.fixtureId)!==String(lastKnownFid)){
   wipeLocalCaptureState("fixture-change:"+lastKnownFid+"→"+snap.fixtureId);
   try{window.__corneraiNetFixture=String(snap.fixtureId)}catch{}
   try{chrome.runtime.sendMessage({type:"FIXTURE_CHANGED",fixtureId:String(snap.fixtureId),previousFixtureId:String(lastKnownFid||""),url:location.href})}catch{}
  }
  if(snap.fixtureId)lastKnownFid=String(snap.fixtureId);
  retunePulse(snap);
  snap.captureWindow=isCriticalWindow(snap.minute,snap.extraMinute)?"critical":(snap.liveStatus==="live"?"normal":"idle");
  const historical=snap.liveStatus==="finished",eventFingerprint=snap.matchEvents.map(e=>e.eventId||e.signature).sort().join("¦"),statsFingerprint=JSON.stringify({stats:Object.fromEntries(STAT_KEYS_LOCAL.filter(k=>snap[k]!=null).map(k=>[k,snap[k]])),extended:snap.extendedStats||{}}),serial=JSON.stringify(snap),clock=snap.minute!=null?`${snap.liveStatus}|${snap.minute}|${snap.extraMinute||0}`:historical?"finished|historical":"unknown";
  const unchanged=serial===lastSerialized;
  const heartbeatWindow=captureHeartbeatMs(snap),heartbeatDue=now-lastSentAt>=heartbeatWindow||clock!==lastMinuteKey,semanticChange=!unchanged||eventFingerprint!==lastEventFingerprint||statsFingerprint!==lastStatsFingerprint,criticalForce=snap.liveStatus==="live"&&snap.captureWindow==="critical"&&(now-lastSentAt>=heartbeatWindow);
  if(!force&&snap.liveStatus==="finished"&&unchanged)return {ok:false,skipped:true,reason:"finished_unchanged"};
  if(!force&&!semanticChange&&!heartbeatDue&&!criticalForce)return {ok:false,skipped:true,reason:"no_change"};
  lastSerialized=serial;lastSentAt=now;lastMinuteKey=clock;lastEventFingerprint=eventFingerprint;lastStatsFingerprint=statsFingerprint;
  const meta={url:location.href,captureReason:force?"force":semanticChange?"semantic-change":"heartbeat",capturedAt:now};
  lastDispatchAt=Date.now();
  const dispatch=async(attempt=0)=>{
   try{
    const r=await send("DOM_SNAPSHOT",snap,meta);lastBackgroundAck=r||null;lastDispatchResult=r||null;
    if(r?.ok||r?.rejected||attempt>=2){
      if(!r?.ok&&!r?.rejected){try{await send("NETWORK_TELEMETRY",null,{url:location.href,error:"DOM snapshot dispatch failed after retries"})}catch{}}
      return r;
    }
    try{await send("NETWORK_TELEMETRY",null,{url:location.href,count:0,retry:attempt+1})}catch{}
    await new Promise(resolve=>setTimeout(resolve,250*(attempt+1)));
    return dispatch(attempt+1);
   }catch(e){
    if(attempt>=2){lastCaptureError=e?.message||String(e);return null;}
    await new Promise(resolve=>setTimeout(resolve,250*(attempt+1)));return dispatch(attempt+1);
   }
  };
  const ack=await dispatch();
  if(ack?.ok||ack?.accepted){lastCaptureSuccess=Date.now();return {ok:true,fixtureId:snap.fixtureId||null,ack};}
  lastCaptureError=ack?.error||ack?.reason||"dispatch_failed";
  return {ok:false,fixtureId:snap.fixtureId||null,reason:lastCaptureError,ack};
 }catch(e){lastCaptureError=e?.message||String(e);try{await send("NETWORK_TELEMETRY",null,{url:location.href,error:lastCaptureError})}catch{}return {ok:false,error:lastCaptureError};}
}
function injectHook(){
 if(document.documentElement.dataset.corneraiHookInjected)return true;
 const existing=document.documentElement.querySelector('script[data-cornerai^="4.58"]');
 if(existing)return true;
 const s=document.createElement("script");
 s.src=chrome.runtime.getURL("page-hook.js");
 s.dataset.cornerai="4.58";
 s.onload=()=>{s.remove();document.documentElement.dataset.corneraiHookInjected="1"};
 s.onerror=()=>{s.remove()};
 (document.head||document.documentElement).appendChild(s);
 return true;
}
function parseChartNetworkSample(sample,url){
  const out={series:[],pressureBars:{},url:String(url||"").slice(0,400),activeLabel:null,encrypted:false};
  if(!sample||typeof sample!=="string"||sample.length<8) return out;
  let data=null;
  try{data=JSON.parse(sample)}catch{return out}
  // Resposta criptografada da API m4 (__m4) — não extrai séries, mas registra URL/tipo
  if(data&&data.__m4===1&&data.d){
    out.encrypted=true;
    const u=String(url||"").toLowerCase();
    if(/\/x7\b/.test(u)) out.activeLabel=out.activeLabel||"MACD XG / x7";
    if(/projecao|grafic/.test(u)) out.activeLabel=out.activeLabel||"PROJEÇÃO";
    return out;
  }
  // Direct structured scrape from page-hook
  if(data&&typeof data==="object"){
    if(Array.isArray(data.series)&&data.series.length){
      for(const p of data.series) out.series.push(p);
    }
    if(data.pressureBars&&typeof data.pressureBars==="object"){
      out.pressureBars={...out.pressureBars,...data.pressureBars};
    }
    if(data.activeLabel) out.activeLabel=String(data.activeLabel);
    if(out.series.length||Object.keys(out.pressureBars).length){
      // still walk below for nested extras, but we already have primary data
    }
  }
  const push=(p)=>{if(p)out.series.push(p)};
  const walk=(node,depth=0)=>{
    if(!node||depth>10)return;
    if(Array.isArray(node)){
      if(node.length&&node.length<=300){
        const first=node[0];
        if(typeof first==="number"&&node.length>=2&&node.length<=130){
          // possible y-series indexed by minute
          node.forEach((v,i)=>{const value=Number(v);if(Number.isFinite(value))push({minute:i,value,src:"net-array"})});
        } else if(first&&typeof first==="object"){
          for(const p of node){
            if(!p||typeof p!=="object")continue;
            const minute=Number(p.minute??p.m??p.x??p.time??p.t??p.periodStart??p.from);
            const value=Number(p.value??p.y??p.v??p.xg??p.pressure??p.attacks??p.dangerous);
            const home=Number(p.home??p.homeValue??p.h);
            const away=Number(p.away??p.awayValue??p.a);
            if(Number.isFinite(minute)&&minute>=0&&minute<=130){
              if(Number.isFinite(value)) push({minute,value,src:"net-obj"});
              else if(Number.isFinite(home)||Number.isFinite(away)) push({minute,home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null,src:"net-obj"});
            }
            // pressure interval keys
            const label=String(p.interval??p.period??p.label??p.name??"");
            const im=label.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
            if(im&&(Number.isFinite(home)||Number.isFinite(away))){
              out.pressureBars[im[1]+"-"+im[2]]={home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null};
            }
          }
        }
      }
      node.slice(0,80).forEach(x=>walk(x,depth+1));
      return;
    }
    if(typeof node==="object"){
      // object map of intervals "0-15": {home,away}
      for(const [k,v] of Object.entries(node)){
        const im=String(k).match(/^(\d{1,2})\s*[-–]\s*(\d{1,2})$/);
        if(im&&v&&typeof v==="object"){
          const home=Number(v.home??v.h??v[0]);
          const away=Number(v.away??v.a??v[1]);
          if(Number.isFinite(home)||Number.isFinite(away))
            out.pressureBars[im[1]+"-"+im[2]]={home:Number.isFinite(home)?home:null,away:Number.isFinite(away)?away:null};
        }
      }
      for(const k of Object.keys(node).slice(0,60)) walk(node[k],depth+1);
    }
  };
  walk(data);
  out.series=out.series.slice(0,500);
  return out;
}

window.addEventListener("message",e=>{
 if(e.source!==window||e.origin!==location.origin||e.data?.source!==MARK)return;
 if(e.data?.type==="HOOK_READY"){hookReadyAt=Date.now();send("HOOK_READY",{version:e.data?.payload?.version||"unknown",url:location.href});return}
 if(e.data?.type==="HOOK_HEARTBEAT"){
   hookReadyAt=Date.now();
   hookMessages++;
   try{send("HOOK_HEARTBEAT",{version:e.data?.payload?.version||VERSION,seq:e.data?.payload?.seq||0,reason:e.data?.payload?.reason||"tick",lastActivityAt:e.data?.payload?.lastActivityAt||Date.now(),ts:Date.now()})}catch{}
   return;
 }
 if(e.data?.type==="PAGE_ERROR"||e.data?.type==="PAGE_REJECTION"||e.data?.type==="PAGE_VUE_ERROR"){
   hookMessages++;
   const p=e.data.payload||{};
   diagLog("ERROR",e.data.type,p.message||e.data.type,{source:p.source,lineno:p.lineno,stack:p.stack,info:p.info});
   return;
 }
 if(e.data?.type==="PAGE_LONG_TASK"){
   const p=e.data.payload||{};
   if(Number(p.duration)>200) diagLog("WARNING","PAGE_LONG_TASK",`longtask ${p.duration}ms`,p);
   return;
 }
 if(e.data?.type==="CHART_PAYLOAD"){
   if(!manualCaptureSession||!captureArmed) return;
   hookMessages++;
   const parsed=parseChartNetworkSample(e.data.sample,e.data.url);
   const hasData=parsed.series.length||Object.keys(parsed.pressureBars).length;
   // Isolamento RÍGIDO: networkUrls só guarda URLs que contêm o fixtureId atual.
   // URLs de livescores / team / season sem fixtureId são ignoradas no cache.
   const curFid=fixtureId();
   const rawUrl=String(parsed.url||e.data.url||"");
   const urlFid=extractFidFromString(rawUrl);
   const sameFixture=!!curFid && !!urlFid && String(curFid)===String(urlFid);
   if((hasData||parsed.encrypted||parsed.url) && sameFixture){
     const prevSeries=Array.isArray(lastChartNetwork.series)?lastChartNetwork.series:[];
     const mergedSeries=(parsed.series.length>=prevSeries.length?parsed.series:prevSeries).slice(0,800);
     lastChartNetwork={
       series:mergedSeries,
       pressureBars:{...(lastChartNetwork.pressureBars||{}),...parsed.pressureBars},
       urls:[...new Set([...(lastChartNetwork.urls||[]),parsed.url].filter(Boolean))].slice(-20),
       activeLabel:parsed.activeLabel||lastChartNetwork.activeLabel||null,
       encrypted:!!(parsed.encrypted||lastChartNetwork.encrypted),
       at:Date.now()
     };
   }
   // Sinaliza rede quando o hook intercepta m4/m2 (mesmo criptografado)
   try{
     const u=String(e.data.url||"");
     if(/m[24]\.sokkerpro\.com|page-scrape:\/\/charts/i.test(u)){
       send("NETWORK_TELEMETRY",{count:1,url:u.slice(0,400)});
     }
   }catch{}
   return;
 }
 // --- Binary WS + connection health (v6.0.0) ---
 if(e.data?.type==="HISTORICAL_BOOTSTRAP"){
   if(!manualCaptureSession||!captureArmed) return;
   hookReadyAt=Date.now();
   try{send("HISTORICAL_BOOTSTRAP",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="SITE_STORAGE_SCAN"){
   if(!manualCaptureSession||!captureArmed) return;
   hookReadyAt=Date.now();
   try{send("SITE_STORAGE_SCAN",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="WS_RECONNECT_BOOTSTRAP"){
   if(!manualCaptureSession||!captureArmed) return;
   hookReadyAt=Date.now();
   try{send("WS_RECONNECT_BOOTSTRAP",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="BINARY_WS_DECODED"){
   if(!manualCaptureSession||!captureArmed) return;
   hookMessages++;
   hookReadyAt=Date.now();
   try{send("BINARY_WS_DECODED",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="BINARY_WS_UNKNOWN"){
   if(!manualCaptureSession||!captureArmed) return;
   hookMessages++;
   hookReadyAt=Date.now();
   try{send("BINARY_WS_UNKNOWN",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="WS_OPEN"){
   if(!manualCaptureSession||!captureArmed) return;
   try{send("WS_OPEN",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="WS_CLOSE"){
   if(!manualCaptureSession||!captureArmed) return;
   try{send("WS_CLOSE",e.data.payload||{})}catch{}
   return;
 }
 if(e.data?.type==="CHART_SERIES") {
   if(!manualCaptureSession||!captureArmed) return;
   hookMessages++;
   try{
     const p=e.data.payload||{};
     const cur=fixtureId(); const pf=p.fixtureId||cur;
     if(!pf||!cur||String(pf)===String(cur)){
       const parsed={series:Array.isArray(p.series)?p.series:[],pressureBars:p.pressureBars&&typeof p.pressureBars==="object"?p.pressureBars:{},url:String(p.url||"page-scrape://charts"),activeLabel:p.activeLabel||null,at:Date.now()};
       lastChartNetwork={series:[...(lastChartNetwork.series||[]),...parsed.series].slice(-1000),pressureBars:{...(lastChartNetwork.pressureBars||{}),...parsed.pressureBars},urls:[...(lastChartNetwork.urls||[]),parsed.url].filter(Boolean).slice(-20),activeLabel:parsed.activeLabel||lastChartNetwork.activeLabel||null,at:Date.now()};
       try{window.__corneraiLatestChart=lastChartNetwork}catch{}
     }
   }catch{}
   return;
 }
 if(e.data?.type==="PAGE_RESOURCE_ERROR") { const p=e.data.payload||{}; const tag=String(p.tag||"").toUpperCase(); const mediaNoise=tag==="IMG"||tag==="VIDEO"; diagLog(mediaNoise?"WARNING":"WARNING",mediaNoise?"PAGE_MEDIA_RESOURCE_MISS":"PAGE_RESOURCE_MISS",p.url||"resource failed",p); return; }
 if(e.data?.type==="PAGE_WS") { const p=e.data.payload||{}; if(p.event==="error"||p.event==="close") diagLog("WARNING","PAGE_WS_"+String(p.event).toUpperCase(),`WebSocket ${p.event}: ${p.url||""}`,p); return; }
 if(e.data?.type!=="NETWORK_PAYLOAD")return;
 hookMessages++;const p=e.data.payload;if(p?.hookTest)return;
 try{
   const ep=String(p?.__endpoint||p?.url||"");
   const raw=p?.__rawText||p?.body||p?.text||"";
   if(/preodds|\/odds|market/i.test(ep) || /"odds"|cotacao|bookmaker|1x2/i.test(String(raw).slice(0,2000))){
     const text=typeof raw==="string"?raw:JSON.stringify(raw||"");
     let data=null; try{data=JSON.parse(text)}catch{}
     const found=[];
     const walk=(node,depth)=>{
       if(!node||depth>8) return;
       if(Array.isArray(node)){ node.forEach(x=>walk(x,depth+1)); return; }
       if(typeof node!=="object") return;
       const odd=Number(node.odds??node.price??node.cotacao??node.quota??node.odd);
       if(Number.isFinite(odd)&&odd>=1.01&&odd<=500){
         found.push({market:String(node.market||node.marketName||node.group||"Mercado").slice(0,80),selection:String(node.selection||node.name||node.outcome||node.label||"").slice(0,80),odds:odd,line:node.line??node.handicap??null,bookmaker:String(node.bookmaker||node.book||"network").slice(0,40),source:"network-preodds"});
       }
       for(const v of Object.values(node)) walk(v,depth+1);
     };
     if(data) walk(data,0);
     if(!found.length){
       const re=/(\d{1,2}[.,]\d{2,3})/g; let m; const nums=[];
       while((m=re.exec(text.slice(0,8000))) && nums.length<30){ const o=parseFloat(m[1].replace(",",".")); if(o>=1.2&&o<=50) nums.push(o); }
       if(nums.length>=3){
         found.push({market:"Resultado Final",selection:"1",odds:nums[0],line:null,bookmaker:"network",source:"network-text"});
         found.push({market:"Resultado Final",selection:"X",odds:nums[1],line:null,bookmaker:"network",source:"network-text"});
         found.push({market:"Resultado Final",selection:"2",odds:nums[2],line:null,bookmaker:"network",source:"network-text"});
       }
     }
     if(found.length){ lastNetworkOdds=found.slice(0,80); }
   }
 }catch{}
 const netFid=p?.__fixtureId||p?.fixtureId||extractFidFromString(p?.__endpoint||"");
 if(netFid){ try{window.__corneraiNetFixture=String(netFid)}catch{} if(p&&!p.fixtureId) p.fixtureId=String(netFid); }
 // Manual activation is mandatory. Network evidence never starts a session.
 if(!manualCaptureSession||!captureArmed) return;
 send("HOOK_SNAPSHOT",p,{url:p?.__endpoint||location.href,fixtureId:netFid||fixtureId()})
});
// [FIX v6.9.9.67] Fila de escrita coalescida por frame — no máx. 1 write por chave por rAF,
// evita que updates concorrentes (captura + Auto-Gemini + monitor) piquem a UI.
const CorneraiRenderQueue=(()=>{
  // Prioridade: 0=crítica (placar/minuto/status), 1=alta (stats), 2=normal
  let pending=new Map(), scheduled=false, gen=0;
  function flush(){
    scheduled=false;
    const batch=pending; pending=new Map();
    // Ordena por prioridade ascendente (menor número = mais prioritário)
    const ordered=[...batch.entries()].sort((a,b)=>(a[1].prio||2)-(b[1].prio||2));
    for(const[key,item]of ordered){
      try{item.fn()}catch(err){console.error("[CornerAI] render fail:",key,err)}
    }
  }
  return{
    enqueue(key,applyFn,prio=2){
      // Mantém a função de maior prioridade (menor número) para a mesma chave
      const prev=pending.get(key);
      if(prev && (prev.prio||2) <= prio) return;
      pending.set(key,{fn:applyFn,prio:prio|0,ts:performance.now()});
      if(!scheduled){scheduled=true;requestAnimationFrame(flush)}
    },
    bumpGeneration(){gen++; return gen;},
    getGeneration(){return gen;}
  };
})();

function mountAlwaysVisibleDashboard(){
  // Painel flutuante COMPLETO + persistente: ferramentas da extensão,
  // arraste pelo cabeçalho, remonta se o SokkerPRO remover o host.
  const HOST_ID="cornerai-always-visible-host";
  const POS_KEY="cornerai_panel_pos_v1";
  const MIN_KEY="cornerai_panel_minimized_v1";

  function loadPos(){try{return JSON.parse(localStorage.getItem(POS_KEY)||"null")}catch{return null}}
  function savePos(left,top){try{localStorage.setItem(POS_KEY,JSON.stringify({left,top}))}catch{}}
  function isMinimized(){try{return localStorage.getItem(MIN_KEY)==="1"}catch{return false}}
  function setMinimized(v){try{localStorage.setItem(MIN_KEY,v?"1":"0")}catch{}}

  function buildPanel(){
    let host=document.getElementById(HOST_ID);
    if(host && host.isConnected){
      if(!isMinimized()) host.style.display="";
      return host;
    }
    if(host && !host.isConnected){ try{host.remove()}catch{} }

    // Remove toolbars legados (versões antigas injetavam barra no topo da página)
    try{
      document.querySelectorAll(
        '#cornerai-toolbar,#cornerai-topbar,#cornerai-control-bar,'+
        '[data-cornerai-toolbar],[id^="cornerai-bar"],[class*="cornerai-toolbar"]'
      ).forEach(el=>{ if(el && el.id!==HOST_ID) try{el.remove()}catch{} });
    }catch{}

    host=document.createElement("div");
    host.id=HOST_ID;
    host.setAttribute("data-cornerai-version",VERSION);
    host.setAttribute("data-cornerai-ignore","1");
    // Isolamento total: fixed 0x0 + contain — zero impacto no layout da página SokkerPRO
    host.style.cssText=[
      "all:initial","position:fixed","inset:auto","left:0","top:0","width:0","height:0",
      "z-index:2147483647","pointer-events:none","overflow:visible",
      "contain:strict","isolation:isolate"
    ].join(";");
    // Começa minimizado: a ativação da extensão nunca cobre a partida nem altera o layout.
  // O usuário pode expandir pelo FAB ou pelo comando SHOW_PANEL.
  const initialMinimized=true;
  if(initialMinimized){ try{ localStorage.setItem(MIN_KEY,"1"); }catch{} }
  host.style.display=(isMinimized()?"none":"");

    const shadow=host.attachShadow({mode:"open"});
    const style=document.createElement("style");
    style.textContent=`:host{all:initial}
.shell{pointer-events:auto;contain:layout style paint;position:fixed;left:14px;top:72px;width:min(360px,calc(100vw - 20px));max-height:calc(100vh - 24px);overflow:auto;z-index:2147483647;font-family:Inter,Segoe UI,Arial,sans-serif}
.panel{color:#edf2f7;background:linear-gradient(145deg,rgba(13,18,27,.98),rgba(8,11,17,.98));border:1px solid rgba(72,84,104,.72);border-radius:16px;box-shadow:0 18px 65px rgba(0,0,0,.48),0 0 0 1px rgba(255,255,255,.025);overflow:hidden;backdrop-filter:blur(18px)}
.head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid #202735;cursor:grab;user-select:none;-webkit-user-select:none;touch-action:none;gap:6px}
.head.dragging{cursor:grabbing}
.brand{display:flex;align-items:center;gap:9px;min-width:0}
.logo{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-weight:900;font-size:12px;background:linear-gradient(135deg,#765cff,#4c7cff);color:#fff;flex:0 0 auto}
.title{font-weight:800;font-size:12px;color:#edf2f7}
.version{font-size:8px;color:#687487;margin-left:4px}
.status{font-size:8px;color:#6ee7a1;margin-top:2px}
.head-actions{display:flex;gap:4px;flex:0 0 auto}
.close,.mini{border:0;background:#111720;color:#8b96a8;border-radius:7px;width:26px;height:26px;cursor:pointer;font-size:13px}
.body{padding:10px 11px 12px;max-height:min(78vh,720px);overflow:auto}
.telemetry{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.telemetry div{background:#0a0f17;border:1px solid #1e2735;border-radius:10px;padding:7px 6px;text-align:center}
.telemetry b{display:block;font-size:13px;font-weight:800;color:#e8eef8}
.telemetry span{font-size:8px;letter-spacing:.06em;color:#6b7688;text-transform:uppercase}
.match{padding:10px 11px;border:1px solid #222c39;border-radius:11px;background:#0a0f17;margin-bottom:10px}
.match small{display:block;color:#657287;font-size:8px;letter-spacing:.08em;text-transform:uppercase}
.teams{font-size:12px;font-weight:800;margin-top:4px;color:#edf2f7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{display:flex;gap:8px;margin-top:6px;color:#758195;font-size:10px;flex-wrap:wrap}
.meta b{color:#c5d0e0;font-weight:700}
.section{margin:0 0 8px;font-size:8px;letter-spacing:.1em;color:#667288;text-transform:uppercase}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px}
.actions button{min-height:34px;border:1px solid #283242;border-radius:9px;background:#0d131c;color:#dfe6ef;font-size:10px;font-weight:700;cursor:pointer;padding:6px 8px}
.actions button:hover{border-color:#526078;background:#111925}
.actions button.primary{border-color:#3153a4;background:#16254a}
.actions button.danger{border-color:#59323a;color:#ffb4bd}
.actions button.accent{border-color:#2d5a45;background:#0f241c;color:#8dffc3}
.actions button.wide{grid-column:1/-1}
.actions button:disabled{opacity:.45;cursor:not-allowed}
.hint{font-size:9px;color:#6a768a;margin:2px 0 8px;line-height:1.35}
.footer{display:flex;justify-content:space-between;gap:8px;margin-top:6px;color:#657185;font-size:8px;flex-wrap:wrap}
.footer b{color:#aeb8c7}
.drag-hint{font-size:8px;color:#59667a;white-space:nowrap}
.fab{pointer-events:auto;position:fixed;right:14px;bottom:18px;z-index:2147483647;width:52px;height:52px;border-radius:15px;border:1px solid rgba(72,84,104,.72);background:linear-gradient(135deg,#765cff,#4c7cff);color:#fff;font-weight:900;font-size:17px;cursor:pointer;box-shadow:0 12px 40px rgba(80,91,255,.35);display:none}
.fab.show{display:grid;place-items:center}
@media(max-width:600px){.shell{left:8px;top:64px;width:calc(100vw - 16px)}.telemetry{grid-template-columns:repeat(2,1fr)}}`;

    const shell=document.createElement("div");
    shell.className="shell";
    const pos=loadPos();
    if(pos && Number.isFinite(pos.left) && Number.isFinite(pos.top)){
      shell.style.left=Math.max(4,pos.left)+"px";
      shell.style.top=Math.max(4,pos.top)+"px";
    }

    const panel=document.createElement("div");
    panel.className="panel";
    panel.innerHTML=`
<div class="head">
  <div class="brand">
    <div class="logo">C</div>
    <div>
      <div class="title">CornerAI <span class="version">${VERSION}</span></div>
      <div class="status" id="status">PAINEL ATIVO</div>
    </div>
  </div>
  <span class="drag-hint">↕ ARRASTE</span>
  <div class="head-actions">
    <button class="mini" id="minimize" title="Minimizar">—</button>
    <button class="close" id="close" title="Minimizar">×</button>
  </div>
</div>
<div class="body">
  <div class="telemetry">
    <div><b id="tIA">0</b><span>IA</span></div>
    <div><b id="tQ">0</b><span>Qualidade</span></div>
    <div><b id="tCov">0</b><span>Cobertura</span></div>
    <div><b id="tMenus">0</b><span>Menus</span></div>
  </div>
  <div class="match">
    <small>PARTIDA ATUAL</small>
    <div class="teams" id="teams">Aguardando captura</div>
    <div class="meta">
      <span><b id="score">— × —</b></span>
      <span id="minute">—'</span>
      <span id="modeTag">—</span>
      <span id="fixtureLine">Fixture —</span>
    </div>
    <div class="meta">
      <span id="source">Fonte —</span>
      <span id="eventsLine">0 eventos</span>
      <span id="snapLine">0 snapshots</span>
    </div>
  </div>

  <div class="section">Captura</div>
  <div class="actions">
    <button class="primary" id="capture" title="Forçar captura agora">↻ Capturar</button>
    <button class="primary" id="arm" title="Armar captura nesta aba">◉ Armar</button>
    <button id="menus" title="Varredura de menus">◎ Menus</button>
    <button class="danger" id="clear" title="Limpar dados da partida">× Limpar</button>
  </div>

  <div class="section">Análise</div>
  <div class="actions">
    <button class="primary" id="dashboard" title="Dashboard completo">◈ Dashboard</button>
    <button id="diagnostics" title="Diagnóstico / erro raiz">◉ Diagnóstico</button>
    <button class="accent" id="skillExport" title="Exportar skill pack para o bridge">⇪ Skill → Bridge</button>
    <button id="skillCopy" title="Copiar JSON da skill">⧉ Copiar Skill</button>
    <button id="pushWebhook" title="Enviar analyst ao webhook">☁ Enviar IA</button>
    <button id="runGemini" title="Rodar Auto-Gemini agora">✦ Gemini</button>
  </div>

  <div class="section">Lote / histórico</div>
  <div class="actions">
    <button id="batchScan" title="Detectar fixtures na página">▣ Detectar jogos</button>
    <button id="openPopup" title="Abrir popup completo da extensão">☰ Controles</button>
    <button class="wide" id="openSkillPage" title="Abrir página /skill do bridge">↗ Abrir /skill no bridge</button>
  </div>
  <p class="hint" id="actionHint">Painel completo · arraste pelo cabeçalho · × só minimiza (botão C restaura)</p>
  <div class="footer">
    <span>Snap <b id="snapshots">0</b></span>
    <span>Evt <b id="events">0</b></span>
    <span>Menus <b id="menuCount">0</b></span>
    <span id="bridgeHint">Bridge —</span>
  </div>
</div>`;

    shell.appendChild(panel);

    const fab=document.createElement("button");
    fab.className="fab"+(isMinimized()?" show":"");
    fab.id="cornerai-fab";
    fab.title="Mostrar painel CornerAI";
    fab.textContent="C";

    shadow.append(style,shell,fab);
    const root=document.documentElement||document.body;
    if(root) root.appendChild(host);
    else document.addEventListener("DOMContentLoaded",()=>{const r=document.documentElement||document.body; if(r) r.appendChild(host);},{once:true});

    window.__corneraiControlHost=host;
    const $=id=>panel.querySelector("#"+id);
    const send=(type,extra={})=>new Promise(resolve=>{
      try{chrome.runtime.sendMessage({type,...extra},r=>resolve(r||{}))}
      catch(e){resolve({ok:false,error:e.message})}
    });
    const setHint=(t)=>{const el=$("actionHint"); if(el) el.textContent=t};

    const activeState=s=>{
      if(!s)return;
      CorneraiRenderQueue.enqueue("panel-state",()=>{
        const setText=(id,val)=>{const el=$(id);if(el&&el.textContent!==String(val))el.textContent=String(val)};
        setText("teams",(s.home&&s.away)?`${s.home} × ${s.away}`:(s.fixtureId?`Fixture ${s.fixtureId}`:"Aguardando captura"));
        setText("score",`${s.score?.home??"—"} × ${s.score?.away??"—"}`);
        setText("minute",s.minute==null?"—'":`${s.minute}${s.extraMinute?`+${s.extraMinute}`:""}'`);
        setText("modeTag",s.liveStatus==="finished"?"HISTÓRICO":s.liveStatus==="live"?"AO VIVO":String(s.dataMode||"IDLE").toUpperCase());
        setText("fixtureLine",s.fixtureId?`Fixture ${s.fixtureId}`:"Fixture —");
        setText("source",`Fonte ${s.lastSnapshotSource||"—"}`);
        setText("eventsLine",`${s.eventCount||s.cornerEventCount||0} eventos`);
        setText("snapLine",`${s.snapshotCount||0} snapshots`);
        setText("snapshots",String(s.snapshotCount||s.statTimeline?.length||0));
        setText("events",String(s.eventCount||s.cornerEventCount||0));
        setText("menuCount",String(s.menuCapture?.uniqueMenus||0));
        setText("tIA",Math.round(Number(s.intelligence?.readiness||0)));
        setText("tQ",Math.round(Number(s.quality?.score||0)));
        setText("tCov",Number(s.capture?.observedMinutes?.length||0));
        setText("tMenus",String(s.menuCapture?.uniqueMenus||0));
        const stEl=$("status");
        let statusTxt="PAINEL ATIVO";
        let statusColor="";
        if(s.liveStatus==="live"){ statusTxt="CAPTURA AO VIVO"; statusColor="#34d399"; }
        else if(s.liveStatus==="finished"){ statusTxt="PARTIDA FINALIZADA"; statusColor="#94a3b8"; }
        else if(!s.fixtureId && !s.home){ statusTxt="AGUARDANDO PARTIDA"; statusColor="#64748b"; }
        else if(s.fixtureId && !s.home){ statusTxt="INICIANDO CAPTURA…"; statusColor="#60a5fa"; }
        if(stEl){
          // Não sobrescreve o feedback temporário de wipe
          if(!(stEl.textContent||"").startsWith("DADOS LIMPOS")){
            stEl.textContent=statusTxt;
            stEl.style.color=statusColor;
          }
        }
      },0);
    };

    const expand=()=>{
      setMinimized(false);
      host.style.display="";
      fab.classList.remove("show");
      shell.style.display="";
    };
    const minimize=()=>{
      setMinimized(true);
      shell.style.display="none";
      fab.classList.add("show");
      host.style.display="";
    };

    // —— Ações (paridade com popup) ——
    $("dashboard").addEventListener("click",()=>send("OPEN_DASHBOARD_WINDOW"));
    $("diagnostics").addEventListener("click",()=>send("OPEN_DIAGNOSTICS_WINDOW"));
    $("capture").addEventListener("click",async()=>{
      setHint("Capturando…");
      const r=await send("FORCE_CAPTURE_REQUEST");
      setHint(r?.ok?"Captura solicitada":(r?.error||"Falha na captura"));
      $("status").textContent=r?.ok?"CAPTURA SOLICITADA":"FALHA NA CAPTURA";
    });
    $("arm").addEventListener("click",async()=>{
      setHint("Armando captura nesta aba…");
      const r=await send("ARM_ACTIVE_GAME");
      setHint(r?.ok?`Armado · fixture ${r.fixtureId||""}`:(r?.error||"Falha ao armar"));
    });
    $("menus").addEventListener("click",async()=>{
      setHint("Varredura de menus…");
      const r=await send("MENU_SWEEP",{options:{allowClicks:false,maxOpen:0,waitMs:300}});
      setHint(r?.ok?"Menus capturados (passivo)":(r?.error||"Falha nos menus"));
    });
    $("clear").addEventListener("click",async()=>{
      if(!confirm("Limpar todos os dados da partida atual?")) return;
      const r=await send("RESET_STATE");
      if(r?.state) activeState(r.state);
      setHint(r?.ok?"Dados limpos":"Falha ao limpar");
    });
    $("skillExport").addEventListener("click",async()=>{
      setHint("Exportando skill pack para o bridge…");
      const r=await send("EXPORT_SKILL_PACK");
      if(r?.bridgeOk){ setHint("Skill gravada no bridge · /skill atualizado"); $("bridgeHint").textContent="Bridge OK"; }
      else setHint(r?.bridgeErr||r?.error||"Falha no export (bridge ligado?)");
    });
    $("skillCopy").addEventListener("click",async()=>{
      setHint("Preparando JSON…");
      const r=await send("EXPORT_SKILL_PACK");
      const text=r?.pasteText||JSON.stringify(r?.json||r?.pack||{},null,2);
      try{
        await navigator.clipboard.writeText(text);
        setHint("JSON da skill copiado · cole no chat");
      }catch{
        setHint("Não foi possível copiar (permissão do clipboard)");
      }
    });
    $("pushWebhook").addEventListener("click",async()=>{
      setHint("Enviando analyst…");
      const r=await send("PUSH_ANALYST",{reason:"panel"});
      setHint(r?.ok?"Analyst enviado":(r?.error||"Falha no webhook"));
    });
    $("runGemini").addEventListener("click",async()=>{
      setHint("Rodando Gemini…");
      const r=await send("RUN_GEMINI",{reason:"panel"});
      setHint(r?.ok?"Gemini ok":(r?.error||"Gemini indisponível / sem API key"));
    });
    $("batchScan").addEventListener("click",async()=>{
      setHint("Detectando fixtures na página…");
      const r=await send("SCAN_PAGE_FIXTURES");
      if(!r?.ok){ setHint(r?.error||"Falha ao detectar"); return; }
      setHint(`${r.count||0} jogo(s) detectado(s) · abra o popup → Coleta em lote para iniciar`);
    });
    $("openPopup").addEventListener("click",()=>{
      // Abre o popup da extensão via action (nem sempre permitido); fallback: instrução
      setHint("Clique no ícone da extensão na barra do Chrome para o popup completo (Gemini, alertas, lote…)");
      try{chrome.runtime.sendMessage({type:"SHOW_PANEL"})}catch{}
    });
    $("openSkillPage").addEventListener("click",()=>{
      window.open("http://127.0.0.1:8080/skill","_blank","noopener");
    });
    $("minimize").addEventListener("click",minimize);
    $("close").addEventListener("click",minimize);
    fab.addEventListener("click",expand);

    if(!window.__corneraiPanelMsgBound){
      window.__corneraiPanelMsgBound=true;
      chrome.runtime.onMessage.addListener(m=>{
        if(m.type==="STATE_UPDATE"&&m.state){window.__corneraiLatestState=m.state;activeState(m.state)}
        if(m.type==="SHOW_PANEL"){expand()}
      });
    }
    chrome.runtime.sendMessage({type:"REQUEST_STATE"},r=>{if(r){window.__corneraiLatestState=r;activeState(r)}});

    // Drag
    const head=panel.querySelector(".head");
    let drag=false,dx=0,dy=0,pointerId=null;
    const onMove=e=>{
      if(!drag||e.pointerId!==pointerId)return;
      if(!(e.buttons&1)){stopDrag();return}
      const x=Math.max(4,Math.min(window.innerWidth-shell.offsetWidth-4,e.clientX-dx));
      const y=Math.max(4,Math.min(window.innerHeight-shell.offsetHeight-4,e.clientY-dy));
      shell.style.left=x+"px"; shell.style.top=y+"px";
    };
    const stopDrag=()=>{
      if(!drag)return;
      drag=false; pointerId=null; head.classList.remove("dragging");
      document.removeEventListener("pointermove",onMove,true);
      document.removeEventListener("pointerup",stopDrag,true);
      document.removeEventListener("pointercancel",stopDrag,true);
      savePos(parseFloat(shell.style.left)||14, parseFloat(shell.style.top)||72);
    };
    head.addEventListener("pointerdown",e=>{
      if(e.button!==0||e.target.closest("button"))return;
      const rect=shell.getBoundingClientRect();
      dx=e.clientX-rect.left; dy=e.clientY-rect.top;
      drag=true; pointerId=e.pointerId;
      head.classList.add("dragging");
      document.addEventListener("pointermove",onMove,true);
      document.addEventListener("pointerup",stopDrag,true);
      document.addEventListener("pointercancel",stopDrag,true);
      try{head.setPointerCapture(e.pointerId)}catch{}
      e.preventDefault();
    });

    if(isMinimized()){ shell.style.display="none"; fab.classList.add("show"); host.style.display=""; }
    return host;
  }

  function ensureMounted(){
    try{
      // Só remonta se o host sumiu de verdade — não reanexa a cada tick (isso luta com o SPA e "apaga" a UI)
      const host=document.getElementById(HOST_ID);
      if(!host || !host.isConnected){ buildPanel(); return; }
      if(host.style.display==="none" && !isMinimized()) host.style.display="";
      // NÃO mover host de parent se já está no documento (evita reflow / sumiço da partida)
    }catch(err){ console.error("[CornerAI] panel ensure failed",err); }
  }

  if(document.documentElement||document.body) ensureMounted();
  else document.addEventListener("DOMContentLoaded",ensureMounted,{once:true});

  // Watchdog leve: 8s, sem MutationObserver no documentElement (causava flash/sumiço)
  if(!window.__corneraiPanelWatchdog){
    window.__corneraiPanelWatchdog=setInterval(ensureMounted,8000);
  }
}

mountAlwaysVisibleDashboard();

// [FIX v6.9.9.77] Observer ultra-leve: debounce alto, ignora próprio host,
// NÃO observa attributes/characterData — evita flash/sumiço da UI do SokkerPRO.
function __corneraiIsOwnMutation(mutations){
  for(const m of mutations){
    const nodes=[m.target,...(m.addedNodes||[]),...(m.removedNodes||[])];
    for(const n of nodes){
      const el=n&&n.nodeType===1?n:(n&&n.parentElement);
      if(!el) continue;
      if(el.id==="cornerai-always-visible-host") return true;
      if(el.closest && (el.closest('[data-cornerai-ignore="1"]') || el.closest('#cornerai-always-visible-host'))) return true;
    }
  }
  return false;
}
let __corneraiObsPaused=false;
const observer=new MutationObserver((mutations)=>{
  if(!captureArmed || __corneraiObsPaused) return;
  if(__corneraiIsOwnMutation(mutations)) return;
  // Debounce alto (3.5s) — SPA do SokkerPRO dispara dezenas de mutações por segundo
  clearTimeout(window.__corneraiTimer);
  window.__corneraiTimer=setTimeout(()=>{ try{capture(false)}catch{} },3500);
});
function observeBody(){
  if(!document.body) return false;
  try{
    observer.observe(document.body,{
      childList:true,
      subtree:true,
      characterData:false,
      attributes:false
    });
  }catch{}
  return true;
}
// Performance guard: do NOT observe the entire fixture DOM before capture is armed.
// SokkerPRO hydrates the match page with a high volume of mutations; an eager
// body-wide observer caused measurable load/interaction delays. The observer is
// attached lazily by startCaptureSession() only after explicit capture consent.
injectHook();
let capturePulseTimer=null,preflightActive=false;
async function prepareCaptureSession(reason="start"){
  if(preflightActive) return {ok:false,error:"preflight_already_active"};
  preflightActive=true;
  // Pré-voo determinístico: jamais iniciar uma nova sessão com buffers da anterior.
  try{ clearInterval(capturePulseTimer); }catch{}
  capturePulseTimer=null;
  captureArmed=false;
  try{ observer.disconnect(); }catch{}
  __corneraiObsPaused=true;
  const fidBeforeWipe=fixtureId();
  wipeLocalCaptureState("preflight:"+reason,fidBeforeWipe);
  let fid=fidBeforeWipe||fixtureId();
  // Em páginas SPA o fixture pode chegar alguns instantes depois via WebSocket/page-hook.
  // Nunca abortar a sessão porque o ID ainda não apareceu no DOM no primeiro instante.
  if(!fid){
    const deadline=Date.now()+1200;
    while(!fid && Date.now()<deadline){
      await new Promise(resolve=>setTimeout(resolve,180));
      fid=fixtureId();
    }
  }
  if(!fid) { __corneraiObsPaused=false; preflightActive=false; return {ok:false,error:"fixture_not_found_after_wait"}; }
  try{ window.__corneraiNetFixture=String(fid); lastKnownFid=String(fid); }catch{}
  // 9.2.4: only RESET background when fixture changed — avoid wiping acceptedSnapshots
  try{
    const st=await send("REQUEST_STATE");
    const same=st && String(st.fixtureId||"")===String(fid) && st.capture && st.capture.armed;
    if(!same){
      const r=await send("RESET_CAPTURE_SESSION",null,{fixtureId:String(fid),url:location.href,reason});
      if(r?.ok===false){ __corneraiObsPaused=false; preflightActive=false; return r; }
    } else {
      // re-affirm arm flags without wiping counters
      try{ await send("REARM_SESSION",null,{fixtureId:String(fid),url:location.href}); }catch{}
    }
  }catch(e){
    diagLog("WARNING","PRECAPTURE_RESET_FALLBACK","background reset unavailable; local isolation retained",{error:String(e?.message||e)});
  }
  // Fast path: não bloquear a primeira captura com estabilização/menu prime.
  // Enriquecimentos seguem em paralelo depois que a sessão já estiver armada.
  preflightActive=false;
  return {ok:true,fixtureId:String(fid)};
}
async function startCaptureSession(){
  clearInterval(capturePulseTimer);
  __lastPulseMs=2000;
  // CRITICAL FIX: arm the local gate BEFORE the first forced capture.
  captureArmed=true;
  try{ window.__corneraiActivationDiag?.start?.("startCaptureSession"); }catch{}
  try{
    if(document.body) observer.observe(document.body,{childList:true,subtree:true,characterData:false,attributes:false});
  }catch{}
  __corneraiObsPaused=false;
  // 9.2.1: AWAIT first snapshot so DOM_SNAPSHOT actually lands before ARM responds.
  // Previous code fired capture(true) without await — race left acceptedSnapshots=0.
  let firstResult=null;
  try{
    // 9.2.2: primary path is forceIngestSnapshot (no throttle / no semantic skip)
    firstResult=await forceIngestSnapshot("session-start");
    if(!firstResult?.ok){
      diagLog("WARNING","FORCE_INGEST_FAIL",String(firstResult?.reason||firstResult?.error||"unknown"),firstResult||{});
      await new Promise(r=>setTimeout(r,300));
      firstResult=await capture(true);
    }
    if(!firstResult?.ok){
      await new Promise(r=>setTimeout(r,400));
      firstResult=await forceIngestSnapshot("session-retry");
    }
  }catch(e){
    lastCaptureError=e?.message||String(e);
    diagLog("ERROR","FIRST_CAPTURE_THROW",lastCaptureError);
  }
  try{ window.__corneraiLastFirstCapture=firstResult||null; }catch{}
  setTimeout(()=>{
    try{ send("MENU_PRIME",null,{fixtureId:String(lastKnownFid||fixtureId()||""),url:location.href}); }catch{}
  },250);
  capturePulseTimer=setInterval(()=>{
    try{ capture(false); }catch{}
  },__lastPulseMs);
  clearInterval(captureWatchdogTimer);
  captureWatchdogTimer=setInterval(()=>{
    if(!captureArmed) return;
    const age=Date.now()-Math.max(lastCaptureSuccess||0,lastCapture||0,lastCaptureAttempt||0);
    if(age>5000){ try{ capture(true); }catch{} }
  },2500);
  return firstResult;
}


let autoArmTimer=null,lastAutoFixture="",lastBackgroundAck=null,fixtureContextMisses=0,captureWatchdogTimer=null;
async function autoArmCapture(forceReArm){
  try{
    if(!manualCaptureSession) return;
    // v6.9.9.106: auto-capture is now enabled only on actual fixture pages.
    // This is passive: no menu sweep/H2H is performed before the first snapshot.
    // CRITICAL: never arm heavy capture on live-list / home pages — observers can blank the match list UI
    const pageLooksLikeFixture=isFixturePage();
    const fid=fixtureId();
    // SPA do SokkerPRO pode desmontar temporariamente placar/estatísticas durante
    // atualização. Não desligue a sessão por uma leitura transitória do DOM.
    // Só abandona após várias verificações consecutivas sem fixture identificável.
    if(!pageLooksLikeFixture && !fid){
      if(captureArmed){
        fixtureContextMisses++;
        if(fixtureContextMisses<4) return;
        captureArmed=false;
        clearInterval(capturePulseTimer); capturePulseTimer=null;
        try{observer.disconnect()}catch{}
        wipeLocalCaptureState("left-fixture-page");
      }
      return;
    }
    fixtureContextMisses=0;
    if(!fid){ if(captureArmed) return; return; }
    const sf=String(fid);
    // Troca de fixture detectada mesmo com captureArmed=true
    if(captureArmed && lastAutoFixture && lastAutoFixture!==sf){
      wipeLocalCaptureState("autoArm-fixture-switch:"+lastAutoFixture+"→"+sf);
      captureArmed=false;
      manualCaptureSession=true;
      clearInterval(capturePulseTimer);
      capturePulseTimer=null;
    }
    // 9.2.4: never re-prepare/reset an already-armed same fixture (was wiping BG snapshots)
    if(captureArmed && lastAutoFixture===sf) return;
    if(captureArmed && lastKnownFid===sf && !forceReArm) return;
    lastAutoFixture=sf;
    lastKnownFid=sf;
    const pre=await prepareCaptureSession("auto-arm:"+sf);
    if(!pre?.ok){ return; }
    lastAutoFixture=sf;
    lastKnownFid=sf;
    await startCaptureSession();
  }catch{}
}
setTimeout(()=>autoArmCapture(false),180);
autoArmTimer=setInterval(()=>{ if(manualCaptureSession) autoArmCapture(false); },2500);

// [v6.9.9.90] Watcher de navegação SPA — re-arma captura sem precisar de F5
(function installSpaNavWatcher(){
  let navTimer=null;
  const onNav=(why)=>{
    const href=location.href;
    if(href===lastUrlSeen && why!=="force") return;
    lastUrlSeen=href;
    // A SPA navigation can reuse the same document. Never carry the previous
    // match's network fixture into the newly visible match.
    try{window.__corneraiNetFixture=null;}catch{}
    try{if(lastChartNetwork?.urls) lastChartNetwork.urls=[];}catch{}
    spaNavEpoch++;
    try{ console.log(PREFIX,"SPA nav detected:",why,href); }catch{}
    // Cancela arm anterior e reavalia após o SPA estabilizar o DOM
    if(navTimer) clearTimeout(navTimer);
    navTimer=setTimeout(()=>{
      try{
        const fid=fixtureId();
        if(fid && lastKnownFid && String(fid)!==String(lastKnownFid)){
          wipeLocalCaptureState("spa-nav:"+why);
          manualCaptureSession=true;
          captureArmed=false;
          clearInterval(capturePulseTimer);
          capturePulseTimer=null;
        }
        if(manualCaptureSession) autoArmCapture(true);
      }catch{}
    },450);
  };
  try{
    const _ps=history.pushState, _rs=history.replaceState;
    history.pushState=function(){ const r=_ps.apply(this,arguments); onNav("pushState"); return r; };
    history.replaceState=function(){ const r=_rs.apply(this,arguments); onNav("replaceState"); return r; };
    window.addEventListener("popstate",()=>onNav("popstate"));
    window.addEventListener("hashchange",()=>onNav("hashchange"));
  }catch{}
  // Poll leve de URL (cobre routers que não usam History API clássica)
  setInterval(()=>{ if(location.href!==lastUrlSeen) onNav("url-poll"); },1200);
})();

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
 if(msg?.type==="GET_LAST_PAGE_TOOL_TEST"){
   sendResponse({ok:!!lastAllToolsTestReport,report:lastAllToolsTestReport||null});
   return true;
 }
 if(msg?.type==="GET_FIXTURE_ID"){
   const fid=fixtureId();
   sendResponse({ok:!!fid,fixtureId:fid?String(fid):null});
   return true;
 }
 if(msg?.type==="GET_CAPTURE_CONTEXT"){
   const fid=fixtureId();
   const fixturePage=isFixturePage();
   sendResponse({ok:true,fixtureId:fid?String(fid):null,isFixturePage:!!fixturePage,url:location.href,teams:extractTeams()});
   return true;
 }
 if(msg?.type==="AUTO_ARM_CAPTURE"){
   (async()=>{
     try{
       manualCaptureSession=true;
       const fid=fixtureId();
       if(!fid||!isFixturePage()){sendResponse({ok:false,error:"Não é uma página de partida."});return;}
       const sf=String(fid);
       // Idempotente: ativação/refresh pode disparar mais de um evento.
       // Não reinicializar observers nem a sessão se esta mesma partida já está armada.
       if(captureArmed && lastAutoFixture===sf){
         const first=await capture(false);
         sendResponse({ok:true,fixtureId:sf,alreadyArmed:true,first:first||null});
         return;
       }
       const pre=await prepareCaptureSession("auto-active:"+sf);
       if(!pre?.ok){sendResponse({ok:false,error:pre?.error||"Falha no pré-voo"});return;}
       lastAutoFixture=sf;
       lastKnownFid=sf;
       const first=await startCaptureSession();
       sendResponse({ok:true,fixtureId:String(fid),first:first||null});
     }catch(e){sendResponse({ok:false,error:e?.message||String(e)})}
   })();
   return true;
 }
 if(msg?.type==="ARM_CAPTURE"){
   manualCaptureSession=true;
   const fid=fixtureId();
   if(!(fid && isFixturePage())){
     sendResponse({ok:false,error:fid?"Abra a página da partida (não a lista ao vivo)":"Nenhuma partida aberta"});
     return true;
   }
   if(msg?.probeOnly){sendResponse({ok:true,fixtureId:String(fid),probe:true});return true;}
   (async()=>{
     try{
       const pre=await prepareCaptureSession("manual-arm:"+fid);
       if(!pre?.ok){sendResponse({ok:false,error:pre?.error||"Falha no pré-voo"});return;}
       const first=await startCaptureSession();
       lastAutoFixture=String(fid);
       lastKnownFid=String(fid);
       // 9.2.2: hard force a minimal snapshot if first capture failed
       if(!first?.ok){
         try{ await forceIngestSnapshot("arm-fallback"); }catch(e){ lastCaptureError=e?.message||String(e); }
       }
       sendResponse({ok:true,fixtureId:String(fid),preflight:true,firstCapture:first||null,lastCaptureError:lastCaptureError||null,lastDispatchResult:lastDispatchResult||null,lastCapture,lastCaptureAttempt,lastCaptureSuccess});
     }catch(e){
       sendResponse({ok:false,error:e?.message||String(e)});
     }
   })();
   return true;
 }
 if(msg?.type==="STOP_CAPTURE"){
   captureArmed=false;
   manualCaptureSession=false;
   clearInterval(capturePulseTimer);
   capturePulseTimer=null;
   clearInterval(captureWatchdogTimer); captureWatchdogTimer=null;
   wipeLocalCaptureState("STOP_CAPTURE");
   sendResponse({ok:true});
   return true;
 }
 if(msg?.type==="COLLECT_DIAGNOSTICS"){
   const snap=build();
   let activationDiag=null;
   try{ activationDiag=window.__corneraiActivationDiag?.report?.()||null; }catch{}
   sendResponse({ok:true,version:VERSION,url:location.href,fixtureId:fixtureId(),readyState:document.readyState,title:document.title,status:snap.liveStatus||detectMatchStatus(),backgroundAck:lastBackgroundAck,dataMode:snap.dataMode||"unknown",teams:extractTeams(),score:snap.score||extractScore(),minute:snap.minute??extractMinute(),statRows:document.querySelectorAll(".stat-values-row,.statistics-row,.stats-row,[class*='stat-values-row'],tr.stat-row,[data-stat],.stat-row,.statistics-item,.stat-item").length,hookMessages,hookReadyAt,hookActive:hookReadyAt>0,matchEvents:snap.matchEvents.length,cornerEvents:snap.matchEvents.filter(e=>e.type==="corner").length,bodyLength:(document.body?.innerText?.length||document.documentElement?.innerText?.length||document.body?.textContent?.length||0),capture:{lastCapture,lastSentAt,lastMinuteKey,unchangedHash:!!lastSerialized,backgroundAck:lastBackgroundAck,armed:captureArmed,manualConsent:manualCaptureSession,activeFixture:lastKnownFid,lastCaptureAttempt,lastCaptureSuccess,lastCaptureError,lastDispatchAt,lastDispatchResult},snapshot:snap,activationDiag,pageDiag:(()=>{try{return window.__corneraiPageDiag?{startedAt:window.__corneraiPageDiag.startedAt||0,errors:(window.__corneraiPageDiag.errors||[]).slice(-20),rejections:(window.__corneraiPageDiag.rejections||[]).slice(-20),network:(window.__corneraiPageDiag.network||[]).slice(-20),longTasks:(window.__corneraiPageDiag.longTasks||[]).slice(-20),resourceErrors:(window.__corneraiPageDiag.resourceErrors||[]).slice(-20),ws:(window.__corneraiPageDiag.ws||[]).slice(-20),chartMutations:Number(window.__corneraiPageDiag.chartMutations||0)}:null}catch{return null}})(),chunkStats:(()=>{try{return window.__corneraiChunkStats||{buffered:0,flushed:0,overflow:0,complete:0,timeout:0,note:"no-active-chunks"};}catch{return {buffered:0,flushed:0,overflow:0,complete:0,timeout:0,note:"unavailable"};}})(),menuSweep:(()=>{try{return window.__corneraiMenuSweep||null;}catch{return null}})()});
   return true;
 }
 if(msg?.type==="SHOW_PANEL"){
   try{localStorage.setItem("cornerai_panel_minimized_v1","0")}catch{}
   const h=document.getElementById("cornerai-always-visible-host");
   if(h){
     h.style.display="";
     h.dataset.corneraiView="controls";
     try{
       const shell=h.shadowRoot&&h.shadowRoot.querySelector(".shell");
       const fab=h.shadowRoot&&h.shadowRoot.querySelector(".fab");
       if(shell) shell.style.display="";
       if(fab) fab.classList.remove("show");
     }catch{}
   } else {
     try{mountAlwaysVisibleDashboard()}catch{}
   }
   sendResponse({ok:true});
   return true;
 }
 if(msg?.type==="RUN_ALL_TOOLS_TEST"){
  (async()=>{
    const started=Date.now();
    const beforeAck=lastBackgroundAck; const beforeSent=lastSentAt; const beforeSuccess=lastCaptureSuccess;
    const results=[];
    const add=(id,label,status,detail,extra={})=>results.push({id,label,status,detail,...extra});
    const yes=v=>v!==null&&v!==undefined&&v!==""&&v!==0;
    let auditFixture="";
    try{
      if(!captureArmed) captureArmed=true;
      manualCaptureSession=true;
      try{await prepareCaptureSession("all-tools-test")}catch{}
      captureArmed=true;
      const first=await capture(true);
      add("dom-capture","📡 Captura DOM",first?.ok?"PASS":"FAIL",first?.ok?"snapshot gerado e enviado":"capture falhou: "+(first?.reason||first?.error||"sem retorno"),{evidence:{attempt:lastCaptureAttempt,success:lastCaptureSuccess,dispatch:lastDispatchResult}});
      try{await new Promise(r=>setTimeout(r,250));}catch{}
      const snap=build();
      auditFixture=String(snap.fixtureId||fixtureId()||lastKnownFid||"");
      add("fixture","🆔 Fixture",yes(snap.fixtureId||auditFixture)?"PASS":"FAIL",yes(snap.fixtureId||auditFixture)?String(snap.fixtureId||auditFixture):"fixture não encontrado");
      add("teams","👥 Times",snap.home&&snap.away?"PASS":"FAIL",snap.home&&snap.away?`${snap.home} × ${snap.away}`:"times não identificados");
      add("score-clock","⏱️ Placar/Relógio",snap.score&&snap.minute!=null?"PASS":"AGUARDANDO",snap.minute!=null?`${snap.minute}' · ${snap.score?.home??"?"}×${snap.score?.away??"?"}`:"relógio/placar incompleto");
      const statKeys=Object.keys(snap.statMeta||{}).filter(k=>snap.statMeta?.[k]?.status&&snap.statMeta[k].status!=="MISSING");
      add("statistics","📊 Estatísticas",statKeys.length?"PASS":"FAIL",statKeys.length?`${statKeys.length} métricas com status`:"nenhuma métrica estruturada");
      add("events","⚽ Eventos",Array.isArray(snap.matchEvents)?"PASS":"FAIL",`${Array.isArray(snap.matchEvents)?snap.matchEvents.length:0} eventos`);
      const cornerPool=(Array.isArray(snap.cornerEvents)&&snap.cornerEvents.length)?snap.cornerEvents:(Array.isArray(snap.matchEvents)?snap.matchEvents.filter(e=>{const t=String(e.type||e.kind||e.event||"").toLowerCase();return t.includes("corner")||t.includes("escante");}):[]);
      const cSideH=cornerPool.filter(e=>e.side==="home"||e.side==="H"||e.side==="C").length; const cSideA=cornerPool.filter(e=>e.side==="away"||e.side==="A"||e.side==="V").length;
      const cAlign=CornerAILib.evaluateCornerAlign({statsHome:snap.corners?.home,statsAway:snap.corners?.away,eventsHome:cSideH,eventsAway:cSideA,liveMinute:Number(snap.minute||0),isLive:true,hasEventChannel:Number(window.__corneraiHookMessages||0)>0});
      add("corners","🚩 Escanteios",cAlign.ok?(cAlign.timelinePending?"AGUARDANDO":"PASS"):"REVIEW",cAlign.detail);
      add("xg","✖️ xG",snap.xg?"PASS":"AGUARDANDO",snap.xg?`${snap.xg?.home??"?"}×${snap.xg?.away??"?"} · conf ${snap.xgMeta?.confidence??"—"}`:"xG não exposto no snapshot");
      const odds=Array.isArray(snap.odds)?snap.odds.length:Object.keys(snap.odds||{}).length;
      add("odds","💰 Odds",odds>0?"PASS":"AGUARDANDO",`${odds} cotações/mercados`);
      const charts=snap.charts||{}; const chartN=Math.max(Number(charts.series?.length||0),Number(charts.seriesCount||0),Number(charts.pressureIntervals||0),Object.keys(charts.pressureBars||{}).length); add("charts","📈 Gráficos",chartN>0?"PASS":"AGUARDANDO",`${chartN} séries/pressão`);
      // 9.2.7: prefer structured snapshot / statMeta over raw DOM text flags
      const sm=snap.statMeta||{};
      const st=v=>String(sm?.[v]?.status||"");
      const hasStat=k=>["CONFIRMED","ZERO"].includes(st(k)) || (snap[k]!=null && snap[k]!=="");
      const text=(document.body?.innerText||"").toLowerCase();
      const checks=[
        ["h2h","🤝 H2H", !!(window.__corneraiH2H?.captured || window.__corneraiH2H?.matches?.length || /h2h|confront|frente a frente/.test(text)), "sinal H2H"],
        ["lineups","🧑‍🤝‍🧑 Escalações", /escala|line.?up|formação/.test(text), "sinal escalação"],
        ["rank","🏆 Ranking", /ranking|classificação|standings/.test(text), "sinal ranking"],
        ["cards","🟨 Cartões", hasStat("yellow")||hasStat("red")||/cart[aã]ões|amarelo|vermelho/.test(text), "cartões no snapshot/DOM"],
        ["possession","🔵 Posse", hasStat("possession")||snap.possession!=null||/posse|possession/.test(text), "posse no snapshot"],
        ["attacks","🔥 Ataques", hasStat("attacks")||hasStat("dangerous")||snap.attacks!=null||/ataques|attacks/.test(text), "ataques no snapshot"],
        ["shots","🎯 Finalizações", hasStat("shots")||hasStat("shotsOn")||snap.shots!=null||/finaliza|chutes|shots/.test(text), "finalizações no snapshot"],
        ["substitutions","🔄 Substituições", hasStat("subs")||/substitui|substitution/.test(text), "substituições"]
      ];
      for(const [id,label,ok,detail] of checks) add(id,label,ok?"PASS":"AGUARDANDO",ok?detail:"nenhum sinal visível no momento");
      try{window.dispatchEvent(new CustomEvent("cornerai-menu-sweep",{detail:{fixtureId:String(auditFixture),allowClicks:true,maxOpen:18,waitMs:650,preferIds:["ao_vivo","estatisticas","escanteios","xg","graficos","h2h","odds","dicas","escalacoes","rank","eventos","finalizacoes","ataques","cartoes","substituicoes","jogadores","posse","pre_jogo","pre_odds","macd_xg","grafico_xg","analise_ia","grafico_padrao","barra_pressao","ataques_perigosos"]}}));}catch{}
      try{window.dispatchEvent(new CustomEvent("cornerai-h2h-poll",{detail:{force:true,type:"H2H_SWEEP"}}));}catch{}
      const menuBefore=window.__corneraiMenuSweep?.discovered||0;
      await new Promise(r=>setTimeout(r,1600));
      const menu=window.__corneraiMenuSweep||{};
      add("menus","🧭 Menus",Number(menu.lastResult?.discovered||menu.discovered||menuBefore)>0?"PASS":"FAIL",`${menu.lastResult?.opened||0} abertos · ${menu.lastResult?.discovered||menu.discovered||menuBefore||0} descobertos`,{evidence:menu.lastResult||null});
      // Re-evaluate H2H after sweep with real capture state
      try{
        const h2=window.__corneraiH2H||{};
        const h2ok=!!(h2.captured||(h2.matches&&h2.matches.length)||(h2.tables&&h2.tables.length)||(h2.rows&&h2.rows>0));
        if(h2ok){
          const prev=results.find(x=>x.id==="h2h");
          if(prev){ prev.status="PASS"; prev.detail=`${h2.matches?.length||0} jogos · ${h2.tables?.length||0} tabelas`; }
          else add("h2h","🤝 H2H","PASS",`${h2.matches?.length||0} jogos · ${h2.tables?.length||0} tabelas`);
        }
      }catch{}
      const ack=lastBackgroundAck;
      add("dispatch","📨 Envio/Bridge",ack?.ok?"PASS":(lastDispatchAt>beforeSent?"AGUARDANDO":"FAIL"),ack?.ok?`background aceitou · ${ack.acceptedSnapshots??"?"} snapshot(s)`:"sem confirmação do background");
      const toolElapsed=Date.now()-started;
      const finalReport={schema:"cornerai-all-tools-test-2",version:VERSION,startedAt:started,finishedAt:Date.now(),durationMs:toolElapsed,fixtureId:String(auditFixture),armed:!!captureArmed,results,summary:{total:results.length,pass:results.filter(x=>x.status==="PASS").length,fail:results.filter(x=>x.status==="FAIL").length,pending:results.filter(x=>x.status==="AGUARDANDO").length},capture:{beforeAck,afterAck:ack,beforeSuccess,afterSuccess:lastCaptureSuccess,lastCaptureAttempt,lastCaptureError,lastDispatchAt,lastDispatchResult},menuSweep:menu.lastResult||null};
      lastAllToolsTestReport=finalReport;
      sendResponse({ok:true,version:VERSION,report:finalReport});
    }catch(e){
      const err=String(e?.message||e);
      const report={
        schema:"cornerai-all-tools-test-2",version:VERSION,startedAt:started,finishedAt:Date.now(),
        durationMs:Date.now()-started,fixtureId:String(auditFixture||""),armed:!!captureArmed,
        results:[{id:"isolation",label:"🛡️ Isolamento",status:"FAIL",detail:err}],
        summary:{total:1,pass:0,fail:1,pending:0},rejected:true,error:err
      };
      lastAllToolsTestReport=report;
      sendResponse({ok:false,error:err,report});
    }
  })();
  return true;
 }
 if(msg?.type==="FORCE_CAPTURE"){
   (async()=>{
     try{
       captureArmed=true;
       manualCaptureSession=true;
       let r=await capture(true);
       if(!r?.ok){ r=await forceIngestSnapshot("force-capture"); }
       sendResponse({ok:true,sweep:false,h2h:false,capture:r||null,lastCapture,lastCaptureError,lastDispatchResult});
     }catch(e){sendResponse({ok:false,error:e?.message||String(e)})}
   })();
   return true;
 }
 if(msg?.type==="CAPTURE_HEARTBEAT"){
   try{
     if(!captureArmed && isFixturePage()){
       manualCaptureSession=true;
       const fid=fixtureId();
       if(fid){
         captureArmed=true;
         try{ observer.observe(document.body,{childList:true,subtree:true,characterData:false,attributes:false}); }catch{}
         if(!capturePulseTimer) capturePulseTimer=setInterval(()=>{try{capture(false)}catch{}},Math.max(550,Number(__lastPulseMs||1000)));
       }
     }
     const result=capture(false);
     sendResponse({ok:true,result,armed:captureArmed,fixtureId:fixtureId(),lastCapture,lastSentAt});
   }catch(e){ sendResponse({ok:false,error:e?.message||String(e),fixtureId:fixtureId()}); }
   return true;
 }
 // Bridge: ensure sibling content scripts (h2h-capture / menu-capture) wake up
 // even when chrome.tabs.sendMessage response is claimed by this listener.
 if(msg?.type==="H2H_POLL"||msg?.type==="H2H_CAPTURE"||msg?.type==="H2H_SWEEP"){
   try{window.dispatchEvent(new CustomEvent("cornerai-h2h-poll",{detail:{force:true,type:msg.type}}));}catch{}
   // Do not claim async response here — let h2h-capture answer when possible.
   // Still return false so other listeners can respond.
 }
 if(msg?.type==="MENU_SWEEP"){
   try{window.dispatchEvent(new CustomEvent("cornerai-menu-sweep",{detail:msg.options||{}}));}catch{}
 }
 if(msg?.type==="PING_CONTENT"){
   sendResponse({ok:true,version:VERSION,fixtureId:fixtureId(),url:location.href,hookActive:hookReadyAt>0});return true;
 }
 // [BATCH] lista fixtures visíveis na página atual (livescores / resultados / calendário)
 if(msg?.type==="SCAN_FIXTURE_LINKS"){
   try{
     const found=new Map();
     const scoreRe=/(\d{1,2})\s*[xX×:-]\s*(\d{1,2})/;
     const minRe=/\b(\d{1,3})(?:\s*[+'′]\s*(\d{1,2}))?\s*['′]?\b/;
     const enrich=(label,el)=>{
       const txt=((label||"")+" "+(el?.textContent||"")).replace(/\s+/g," ").trim();
       let home=null,away=null,scoreH=null,scoreA=null,minute=null,live=false;
       const sm=txt.match(scoreRe);
       if(sm){ scoreH=+sm[1]; scoreA=+sm[2]; }
       // "TeamA 1x0 TeamB" or "TeamA vs TeamB"
       const vs=txt.match(/^(.{2,40}?)\s+(?:\d{1,2}\s*[xX×:-]\s*\d{1,2}|vs\.?|×)\s+(.{2,40?}?)(?:\s|$)/i);
       if(vs){ home=vs[1].replace(scoreRe,"").trim(); away=vs[2].replace(scoreRe,"").trim(); }
       const mm=txt.match(/(?:^|\s)(\d{1,3})\s*['′](?:\s*\+\s*(\d{1,2}))?/);
       if(mm && +mm[1]<=130){ minute=+mm[1]; live=true; }
       if(/\b(live|ao\s*vivo|1º|2º|HT|1T|2T)\b/i.test(txt)) live=true;
       return {home,away,scoreH,scoreA,minute,live,label:txt.slice(0,120)};
     };
     const add=(id,url,label,el)=>{
       const fid=String(id||"").replace(/\D/g,"");
       if(!/^\d{5,}$/.test(fid)) return;
       const meta=enrich(label,el);
       const prev=found.get(fid);
       const row={
         fixtureId:fid,
         url:url||(prev&&prev.url)||`https://sokkerpro.com/fixture/${fid}`,
         label:(meta.label||label||"").replace(/\s+/g," ").trim().slice(0,120),
         home:meta.home||prev?.home||null,
         away:meta.away||prev?.away||null,
         score: (meta.scoreH!=null||meta.scoreA!=null)?{home:meta.scoreH,away:meta.scoreA}:(prev?.score||null),
         minute:meta.minute??prev?.minute??null,
         live: !!(meta.live||prev?.live)
       };
       found.set(fid,row);
     };
     document.querySelectorAll("a[href]").forEach(a=>{
       const href=a.href||a.getAttribute("href")||"";
       const id=extractFidFromString(href);
       if(id) add(id, href.startsWith("http")?href:null, a.textContent||a.title||"", a);
     });
     document.querySelectorAll("[data-fixture-id],[data-match-id],[data-game-id]").forEach(el=>{
       const id=el.getAttribute("data-fixture-id")||el.getAttribute("data-match-id")||el.getAttribute("data-game-id");
       add(id, null, el.textContent||"", el);
     });
     // Cards / rows that mention fixture in class or nearby links
     document.querySelectorAll("[class*='match'],[class*='fixture'],[class*='event'],[class*='game'],tr,li").forEach(el=>{
       const html=el.innerHTML||"";
       const id=extractFidFromString(html)||extractFidFromString(el.getAttribute("href")||"");
       if(id) add(id, null, el.textContent||"", el);
     });
     const self=fixtureId();
     if(self) add(self, location.href, document.title||"", document.body);
     const list=[...found.values()].sort((a,b)=>Number(b.live)-Number(a.live)||String(a.label).localeCompare(String(b.label)));
     sendResponse({ok:true,count:list.length,fixtures:list,url:location.href,title:document.title||"",scannedAt:Date.now()});
   }catch(e){
     sendResponse({ok:false,error:e?.message||String(e),fixtures:[]});
   }
   return true;
 }
});
console.log(PREFIX,"v"+VERSION+" content script instalado · auto-arm SPA + wipe on fixture change",location.href);

// --- Stability telemetry v6.9.9.90 ---
let __swFailStreak=0;
async function probeSW(){
  const t0=Date.now();
  const r=await new Promise(resolve=>{
    try{
      chrome.runtime.sendMessage({type:"PING_BACKGROUND"},res=>{
        if(chrome.runtime.lastError) resolve({ok:false,error:chrome.runtime.lastError.message});
        else resolve({ok:true,res,ms:Date.now()-t0});
      });
    }catch(e){resolve({ok:false,error:e?.message||String(e)});}
  });
  if(!r.ok){
    __swFailStreak++;
    if(__swFailStreak>=2) diagLog("CRITICAL","SW_UNREACHABLE",r.error||"no response",{streak:__swFailStreak,ms:Date.now()-t0});
  } else {
    __swFailStreak=0;
  }
  return r;
}
async function sampleHealth(){
  try{
    const mem=performance.memory||{};
    const used=mem.usedJSHeapSize||0;
    const limit=mem.jsHeapSizeLimit||1;
    let storageLocalBytes=null, storageQuotaBytes=null;
    try{
      if(chrome.storage.local.getBytesInUse) storageLocalBytes=await chrome.storage.local.getBytesInUse(null);
      storageQuotaBytes=Number(chrome.storage.local.QUOTA_BYTES)||null;
    }catch{}
    const payload={
      heapMB:+(used/1e6).toFixed(1),
      heapRatio:+(used/Math.max(1,limit)).toFixed(3),
      storageLocalBytes,
      storageQuotaBytes,
      captureArmed:!!captureArmed,
      hookMessages,
      fixtureId:fixtureId()
    };
    chrome.runtime.sendMessage({type:"DIAG_HEALTH_SAMPLE",payload},()=>void chrome.runtime.lastError);
    if(payload.heapRatio>0.75) diagLog("WARNING","MEM_HEAP_HIGH","Heap >75%",payload);
  }catch{}
}
setInterval(()=>{ try{probeSW();}catch{} },8000);
setInterval(()=>{ try{ if(captureArmed) sampleHealth(); }catch{} },30000);
window.addEventListener("error",(ev)=>{
  try{ if(/cornerai|extension/i.test(String(ev.filename||""))||/cornerai/i.test(String(ev.message||""))) diagLog("ERROR","CS_ONERROR",ev.message,{source:ev.filename,lineno:ev.lineno}); }catch{}
},true);
window.addEventListener("unhandledrejection",(ev)=>{
  try{ diagLog("ERROR","CS_REJECTION",ev.reason?.message||String(ev.reason)); }catch{}
});

})();
