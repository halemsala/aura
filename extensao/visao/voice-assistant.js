/* NATIVE_TTS_REMOVED 12.8.14 — only local 8099 Piper/Neural */
'use strict';
/**
 * KANTEIRO VOICE ASSISTANT — cliente do sidepanel (otimizado).
 * - Escuta contínua automática via VAD (Web Audio API), sem push-to-talk.
 * - Consome resposta em streaming (NDJSON): toca cada frase assim que pronta.
 * - Wake word opcional ("jarvis") configurável.
 * - Sessão de conversa isolada por partida (fixtureId do sidepanel).
 *
 * Requer: python3 bridge/jarvis_voice_server.py rodando em 127.0.0.1:8099
 */
const AURA_VOICE_PROFILE = {
  id: 'aura-natural-technical',
  label: 'Kanteiro Neural · Hercules / Humberto · masculino',
  lang: 'pt-BR',
  // Perfil obrigatório: português brasileiro e preferência masculina.
  // O navegador/Windows pode oferecer nomes diferentes por versão, por isso
  // usamos pistas de nome sem aceitar pt-PT como fallback silencioso.
  preferredNames: ['Humberto', 'Hercules', 'Nicolau', 'Donato'],
  maleHints: ['daniel', 'luciano', 'antonio', 'antônio', 'gustavo', 'felipe', 'rafael', 'ricardo', 'male', 'masculino', 'brazil', 'brasil'],
  avoidHints: ['helia', 'helena', 'francisca', 'luciana', 'maria', 'female', 'feminina', 'portugal', 'pt-pt'],
  baseRate: 0.96,
  basePitch: 0.84,
  volume: 1.0,
};

const JARVIS_VOICE = {
  baseUrl: 'http://127.0.0.1:8099',
  active: false,          // modo "sempre ouvindo" ligado/desligado
  speaking: false,        // true durante gravação de fala detectada
  processing: false,      // true durante STT->LLM->TTS
  audioCtx: null,
  analyser: null,
  micStream: null,
  mediaRecorder: null,
  chunks: [],
  silenceStart: null,
  speechStart: null,
  vadLoopId: null,
  requireWakeWord: false,
  wakeWord: 'kanteiro',
  audioQueue: [],
  playingQueue: false,
  neuralTextQueue: [],
  neuralBusy: false,
  mood: 'medio',
  voiceId: 'kanteiro-neural-humberto',
  preferNeural: true,
};

// ---------- Configurações persistidas ----------
function voiceLoadSettings() {
  try {
    JARVIS_VOICE.requireWakeWord = localStorage.getItem('kanteiro_wake_required') === '1';
    JARVIS_VOICE.wakeWord = localStorage.getItem('kanteiro_wake_word') || 'kanteiro';
    // Interação contínua: sem necessidade de botão de aprovação nem wake word obrigatória
    if (localStorage.getItem('kanteiro_wake_required') == null) {
      localStorage.setItem('kanteiro_wake_required', '0');
    }
    JARVIS_VOICE.requireWakeWord = localStorage.getItem('kanteiro_wake_required') === '1';
    JARVIS_VOICE.mood = localStorage.getItem('kanteiro_mood') || 'medio';
    JARVIS_VOICE.voiceId = localStorage.getItem('kanteiro_voice_id') || 'auto';
  } catch (_) {}
}

// ---------- Sessão (isolada por partida) ----------
function voiceCurrentSessionId() {
  try {
    if (window.lastFixture) return 'fixture:' + String(window.lastFixture);
  } catch (_) {}
  if (!JARVIS_VOICE._fallbackSession) {
    JARVIS_VOICE._fallbackSession = 'sidepanel:' + Math.random().toString(36).slice(2, 10);
  }
  return JARVIS_VOICE._fallbackSession;
}

// ---------- UI helpers ----------
function voiceSetStatus(text, kind) {
  const el = document.getElementById('voiceStatus');
  if (!el) return;
  if (!text) { el.hidden = true; el.textContent = ''; return; }
  el.hidden = false;
  el.textContent = text;
  el.className = 'voice-status' + (kind ? ' ' + kind : '');
}

function voiceSetMicVisual(state) {
  const btn = document.getElementById('btnVoiceMic');
  if (!btn) return;
  btn.classList.remove('listening', 'active-idle', 'speaking-user', 'processing');
  if (state) btn.classList.add(state);
}

function voiceAppendMessage(role, text) {
  // O sidepanel usa addBubble; o nome antigo appendChatMessage não existe
  // nessa versão e criava mensagens fora do layout principal.
  if (typeof window.addBubble === 'function') {
    window.addBubble(role === 'user' ? 'user' : 'ai', String(text || ''), { markdown: role !== 'user' });
    return;
  }
  if (typeof window.appendChatMessage === 'function') {
    window.appendChatMessage(role, text);
    return;
  }
  const box = document.getElementById('chatMessages');
  if (!box) return;
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (role === 'user' ? 'user' : 'ai');
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ---------- WAV encode ----------
async function blobToWavBase64(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  try {
    const decoded = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
    const wavBuffer = encodeWav(decoded, 16000);
    const bytes = new Uint8Array(wavBuffer);
    let binary = '';
    // Evita o loop byte a byte, que é caro em falas longas.
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  } finally {
    await audioCtx.close().catch(() => {});
  }
}

function encodeWav(audioBuffer, targetSampleRate = 16000) {
  const numChannels = 1;
  const sourceRate = audioBuffer.sampleRate || targetSampleRate;
  const source = audioBuffer.getChannelData(0);
  const ratio = sourceRate / targetSampleRate;
  const sampleCount = Math.max(1, Math.floor(source.length / ratio));
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeStr(8, 'WAVE'); writeStr(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true); view.setUint32(24, targetSampleRate, true);
  view.setUint32(28, targetSampleRate * numChannels * 2, true);
  view.setUint16(32, numChannels * 2, true); view.setUint16(34, 16, true);
  writeStr(36, 'data'); view.setUint32(40, sampleCount * 2, true);
  let offset = 44;
  for (let i = 0; i < sampleCount; i++, offset += 2) {
    const pos = Math.min(source.length - 1, i * ratio);
    const left = Math.floor(pos);
    const frac = pos - left;
    const a = source[left] || 0;
    const b = source[Math.min(source.length - 1, left + 1)] || a;
    const s = Math.max(-1, Math.min(1, a + (b - a) * frac));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

// ---------- Fila de reprodução (streaming por frase) ----------
function voiceEnqueueAudio(base64, format='mp3') {
  JARVIS_VOICE.audioQueue.push({base64,format});
  voicePlayNextInQueue();
}

function voicePlayNextInQueue() {
  if (JARVIS_VOICE.playingQueue) return;
  const next = JARVIS_VOICE.audioQueue.shift();
  if (!next) return;
  JARVIS_VOICE.playingQueue = true;
  const audio = new Audio('data:' + (next.format === 'wav' ? 'audio/wav' : 'audio/mpeg') + ';base64,' + next.base64);
  audio.onended = () => { JARVIS_VOICE.playingQueue = false; voicePlayNextInQueue(); };
  audio.onerror = () => { JARVIS_VOICE.playingQueue = false; voicePlayNextInQueue(); };
  audio.play().catch(() => { JARVIS_VOICE.playingQueue = false; voicePlayNextInQueue(); });
}

// ---------- FAST VOICE: SpeechSynthesis do navegador/Windows ----------
// Não espera XTTS. A primeira frase começa a falar assim que o LLM a entrega.
JARVIS_VOICE.speechQueue = [];
JARVIS_VOICE.speakingBrowser = false;

function voiceListAvailable() {
  if (!('speechSynthesis' in window)) return [];
  return (speechSynthesis.getVoices() || []).filter((v) => v && v.lang);
}

function voicePickPtVoice() {
  const voices = voiceListAvailable();
  if (!voices.length) return null;
  const isPtBr = (v) => /^pt[-_]BR$/i.test(String(v?.lang || ''));
  const isPt = (v) => /^pt([-_]|$)/i.test(String(v?.lang || ''));
  const norm = (v) => String(v?.name || '').toLowerCase();
  const hints = (v, list) => list.some((hint) => norm(v).includes(hint));
  const selectVal = document.getElementById('voiceVoiceSelect')?.value;
  if (JARVIS_VOICE.voiceId && JARVIS_VOICE.voiceId !== 'auto') {
    const selected = voices.find((v) => v.voiceURI === JARVIS_VOICE.voiceId);
    const manual = selectVal && selectVal === JARVIS_VOICE.voiceId;
    if (selected && (isPtBr(selected) || manual)) return selected;
    JARVIS_VOICE.voiceId = 'auto';
    try { localStorage.setItem('kanteiro_voice_id', 'auto'); } catch (_) {}
  }
  const ptBr = voices.filter(isPtBr);
  // local-only: não selecionar vozes explicitamente remotas.
  const pool = ptBr.filter((voice) => voice.localService !== false);
  if (!pool.length) return null;
  const preferred = AURA_VOICE_PROFILE.preferredNames.map((name) => name.toLowerCase());
  return pool.slice().sort((a, b) => {
    const am = hints(a, AURA_VOICE_PROFILE.maleHints);
    const bm = hints(b, AURA_VOICE_PROFILE.maleHints);
    if (am !== bm) return am ? -1 : 1;
    const aa = hints(a, AURA_VOICE_PROFILE.avoidHints);
    const ba = hints(b, AURA_VOICE_PROFILE.avoidHints);
    if (aa !== ba) return aa ? 1 : -1;
    const ai = preferred.findIndex((name) => norm(a).includes(name));
    const bi = preferred.findIndex((name) => norm(b).includes(name));
    const ap = ai < 0 ? 999 : ai;
    const bp = bi < 0 ? 999 : bi;
    if (ap !== bp) return ap - bp;
    if (a.localService !== b.localService) return a.localService ? -1 : 1;
    return String(a.name).localeCompare(String(b.name));
  })[0] || null;
}

function voiceProfileLabel() {
  const v = voicePickPtVoice();
  if (v) return `${AURA_VOICE_PROFILE.label} · ${v.name} · ${v.lang}`;
  return `${AURA_VOICE_PROFILE.label} · Edge TTS · pt-BR-HumbertoNeural`;
}

function voiceRefreshVoiceSelect() {
  const select = document.getElementById('voiceVoiceSelect');
  if (!select) return;
  const current = JARVIS_VOICE.voiceId || 'auto';
  const voices = voiceListAvailable()
    .filter((v) => /^pt/i.test(v.lang))
    .sort((a, b) => String(a.name).localeCompare(String(b.name)));
  select.innerHTML = '';
  const auto = document.createElement('option');
  auto.value = 'auto';
  auto.textContent = 'Jarvis BR · HumbertoNeural · masculino';
  select.appendChild(auto);
  voices.forEach((v) => {
    const option = document.createElement('option');
    option.value = v.voiceURI;
    option.textContent = `${v.name} · ${v.lang}${v.localService ? '' : ' · online'}`;
    select.appendChild(option);
  });
  select.value = [...select.options].some((o) => o.value === current) ? current : 'auto';
  if (select.value !== current) {
    JARVIS_VOICE.voiceId = 'auto';
    try { localStorage.setItem('kanteiro_voice_id', 'auto'); } catch (_) {}
  }
}

function initVoiceVoiceControl() {
  const select = document.getElementById('voiceVoiceSelect');
  if (!select) return;
  voiceRefreshVoiceSelect();
  if ('speechSynthesis' in window) {
    speechSynthesis.addEventListener?.('voiceschanged', voiceRefreshVoiceSelect);
    setTimeout(voiceRefreshVoiceSelect, 600);
  }
  select.addEventListener('change', () => {
    JARVIS_VOICE.voiceId = select.value || 'auto';
    try { localStorage.setItem('kanteiro_voice_id', JARVIS_VOICE.voiceId); } catch (_) {}
    voiceSetStatus('Voz selecionada: ' + voiceProfileLabel(), 'ready');
    setTimeout(() => { if (!JARVIS_VOICE.active) voiceSetStatus('', null); }, 2200);
  });
}

function previewAuraVoice() {
  voiceStopBrowserSpeech();
  voiceSetStatus('▶ Prévia: ' + voiceProfileLabel(), 'speaking');
  voiceSpeakNeural('Hálem, estou online. Dados no ar, risco no radar.');
}

function voiceCleanForSpeech(raw) {
  // Texto para TTS: só resposta ao usuário — sem markdown, sem asteriscos, números arredondados.
  let s = String(raw || '');
  // remove blocos de código e markdown residual
  s = s.replace(/```[\s\S]*?```/g, ' ');
  s = s.replace(/`[^`]*`/g, ' ');
  s = s.replace(/\*\*([^*]+)\*\*/g, '$1');
  s = s.replace(/\*([^*]+)\*/g, '$1');
  s = s.replace(/__([^_]+)__/g, '$1');
  s = s.replace(/_([^_]+)_/g, '$1');
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  s = s.replace(/\[[^\]]*\]/g, ' ');
  // remove símbolos que o TTS soletra (asterisco, bullet, etc.)
  s = s.replace(/[*#>`~|_^=]+/g, ' ');
  s = s.replace(/https?:\/\/\S+/g, 'link');
  // arredonda números longos: 0.72345 -> 72 por cento se parecer prob; senão 1 casa ou inteiro
  s = s.replace(/\b0\.(\d{2,})\b/g, (_, dec) => {
    const n = Number('0.' + dec);
    if (!Number.isFinite(n)) return _;
    if (n > 0 && n < 1) return String(Math.round(n * 100)) + ' por cento';
    return String(Math.round(n * 10) / 10);
  });
  s = s.replace(/\b(\d+)\.(\d{3,})\b/g, (_, a, b) => {
    const n = Number(a + '.' + b);
    if (!Number.isFinite(n)) return a + '.' + b;
    // inteiros grandes ou taxas: 1 casa se < 100, senão inteiro
    if (Math.abs(n) >= 100) return String(Math.round(n));
    return String(Math.round(n * 10) / 10).replace('.', ',');
  });
  s = s.replace(/\b(\d+)\.(\d{1,2})\b/g, (_, a, b) => a + ',' + b); // pt-BR
  s = s.replace(/\s+/g, ' ').trim();
  // não falar eco de meta
  if (/^(usuário|user|você disse|pergunta:)/i.test(s)) return '';
  return s;
}

/** Nunca sintetiza fala do usuário — só respostas do assistente. */
function voiceSpeakAssistantOnly(text, meta) {
  if (meta && meta.role === 'user') return Promise.resolve(false);
  const clean = voiceCleanForSpeech(text);
  if (!clean) return Promise.resolve(false);
  // evita eco se o texto for igual à última pergunta do usuário
  if (JARVIS_VOICE._lastUserText && clean.toLowerCase() === String(JARVIS_VOICE._lastUserText).toLowerCase()) {
    return Promise.resolve(false);
  }
  return voiceQueueNeuralText(clean);
}


function voiceSpeakBrowser(text) {
  // Voz nativa do navegador DESINSTALADA. Apenas AURA Voice local :8099.
  return voiceSpeakNeural(text);
}

function voiceQueueNeuralText(text) {
  const clean = voiceCleanForSpeech(text);
  if (!clean) return Promise.resolve(false);
  return new Promise((resolve) => {
    JARVIS_VOICE.neuralTextQueue.push({text:clean,resolve});
    voiceDrainNeuralTextQueue();
  });
}

function voicePrimeAudio() {
  try {
    if (!JARVIS_VOICE.primedAudio) JARVIS_VOICE.primedAudio = new Audio();
    const el = JARVIS_VOICE.primedAudio;
    el.muted = true;
    el.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=';
    const p = el.play();
    if (p && p.then) p.then(() => { el.pause(); el.muted = false; }).catch(() => {});
  } catch (_) {}
}
try { window.voicePrimeAudio = voicePrimeAudio; } catch (_) {}

async function voiceDrainNeuralTextQueue() {
  if (JARVIS_VOICE.neuralBusy) return;
  const item=JARVIS_VOICE.neuralTextQueue.shift();
  if (!item) return;
  JARVIS_VOICE.neuralBusy=true;
  try {
    voicePrimeAudio();
    voiceSetStatus('🔊 Kanteiro Neural…', 'speaking');
    const r=await fetch(JARVIS_VOICE.baseUrl+'/api/voice/neural',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:item.text, voice:'pt-BR-HumbertoNeural', rate:'-12%', pitch:'-8Hz'}),
      signal:AbortSignal.timeout(20000)
    });
    const data=await r.json().catch(()=>({}));
    if(!r.ok || !data?.audio_base64) throw new Error(data?.error||'neural_tts_fail');
    if(data.gender && data.gender !== 'male') throw new Error('tts_gender_not_male');
    if(data.fallback && data.fallback !== 'disabled') throw new Error('tts_fallback_rejected');
    await new Promise((resolve,reject)=>{
      const audio=JARVIS_VOICE.primedAudio || new Audio();
      JARVIS_VOICE.primedAudio=audio;
      audio.muted=false;
      audio.preload='auto';
      audio.onended=()=>resolve(true);
      audio.onerror=()=>reject(new Error('audio_play_error'));
      audio.src='data:audio/mpeg;base64,'+data.audio_base64;
      const p=audio.play();
      if(p&&p.catch)p.catch(reject);
    });
    item.resolve(true);
  }catch(e){
    voiceSetStatus('Kanteiro Neural indisponível: '+(e?.message||e),'error');
    item.resolve(false);
  }finally{
    JARVIS_VOICE.neuralBusy=false;
    if(JARVIS_VOICE.neuralTextQueue.length) setTimeout(voiceDrainNeuralTextQueue,0);
  }
}

async function voiceSpeakNeural(text) {
  return voiceQueueNeuralText(text);
}

async function auraSpeakText(text) {
  // API pública: só fala respostas; limpa * e arredonda números
  text = voiceCleanForSpeech(text);
  if (!text) return false;
  const ok = await voiceSpeakNeural(text);
  if (ok) return true;
  try {
    const r = await fetch(JARVIS_VOICE.baseUrl + '/api/voice/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: voiceCleanForSpeech(text) }),
      signal: AbortSignal.timeout(20000)
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data?.audio_base64) return false;
    if (data.gender && data.gender !== 'male') return false;
    if (data.fallback && data.fallback !== 'disabled') return false;
    if (/(Francisca|gtts|google)/i.test(`${data.voice || ''} ${data.engine || ''}`)) return false;
    await new Promise((resolve) => {
      const audio = new Audio(`data:${(data.format || data.audio_format) === 'wav' ? 'audio/wav' : 'audio/mpeg'};base64,` + data.audio_base64);
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.play().catch(resolve);
    });
    return true;
  } catch (_) {
    return false;
  }
}
try { window.auraSpeakText = auraSpeakText; window.voiceSpeakNeural = voiceSpeakNeural; } catch (_) {}

function voiceDrainBrowserSpeech() {
  // Voz nativa REMOVIDA. Toda fala vai para o servidor local :8099 (Piper / Neural local).
  if (!JARVIS_VOICE.speechQueue.length) return;
  const text = JARVIS_VOICE.speechQueue.shift();
  voiceSpeakNeural(text).finally(() => {
    if (JARVIS_VOICE.speechQueue.length) setTimeout(voiceDrainBrowserSpeech, 0);
  });
}

function voiceStopBrowserSpeech() {
  JARVIS_VOICE.speechQueue = [];
  JARVIS_VOICE.speakingBrowser = false;
  try { /* native TTS removed */ } catch (_) {}
}

// ---------- Health ----------
function voiceServerError(error) {
  const raw=String(error?.message||error||'erro desconhecido');
  const low=raw.toLowerCase();
  const cause=low.includes('abort')||low.includes('timeout')?'timeout: o servidor não respondeu em 2,5s':'sem conexão: nenhum processo respondeu na porta 8099';
  return `[VOICE OFFLINE] 127.0.0.1:8099 · ${cause}. Execute AURA_INSTALAR_E_INICIAR_TUDO.bat. Log: bridge\\runtime_voice.log`;
}
async function jarvisVoiceHealthCheck() {
  try {
    const r = await fetch(JARVIS_VOICE.baseUrl + '/api/voice/health', { signal: AbortSignal.timeout(2500) });
    const data=await r.json();
    if(!r.ok) return {ok:false,error:`[VOICE HTTP ${r.status}] ${data?.error||'resposta inválida'} · endpoint ${JARVIS_VOICE.baseUrl}`};
    return data;
  } catch (e) {
    return { ok: false, error: voiceServerError(e) };
  }
}

// ---------- VAD (Voice Activity Detection) ----------
const VAD_THRESHOLD = 0.02;       // sensibilidade (RMS)
const VAD_SILENCE_MS = 420;       // silêncio para considerar fim da fala
const VAD_MIN_SPEECH_MS = 180;    // fala mínima para não ser ruído

async function voiceStartContinuousListening() {
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('este contexto do navegador não oferece getUserMedia');
    }
    if (!window.MediaRecorder) {
      throw new Error('MediaRecorder não é suportado por este navegador');
    }
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error('Web Audio API não é suportada');

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    JARVIS_VOICE.micStream = stream;
    JARVIS_VOICE.audioCtx = new AudioCtx();
    if (JARVIS_VOICE.audioCtx.state === 'suspended') await JARVIS_VOICE.audioCtx.resume();
    const source = JARVIS_VOICE.audioCtx.createMediaStreamSource(stream);
    const analyser = JARVIS_VOICE.audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    JARVIS_VOICE.analyser = analyser;

    JARVIS_VOICE.active = true;
    voiceSetMicVisual('active-idle');
    voiceSetStatus('👂 Escuta automática ativa — fale quando quiser', 'listening');
    voiceVadLoop();
  } catch (e) {
    if (JARVIS_VOICE.micStream) JARVIS_VOICE.micStream.getTracks().forEach((t) => t.stop());
    JARVIS_VOICE.micStream = null;
    voiceSetMicVisual(null);
    voiceSetStatus('Sem acesso ao microfone: ' + (e?.message || e), 'error');
  }
}

function voiceStopContinuousListening() {
  JARVIS_VOICE.active = false;
  voiceStopBrowserSpeech();
  if (JARVIS_VOICE.vadLoopId) cancelAnimationFrame(JARVIS_VOICE.vadLoopId);
  if (JARVIS_VOICE.mediaRecorder && JARVIS_VOICE.mediaRecorder.state === 'recording') {
    JARVIS_VOICE.mediaRecorder.stop();
  }
  if (JARVIS_VOICE.micStream) JARVIS_VOICE.micStream.getTracks().forEach((t) => t.stop());
  if (JARVIS_VOICE.audioCtx) JARVIS_VOICE.audioCtx.close();
  voiceSetMicVisual(null);
  voiceSetStatus('', null);
}

function voiceRms(analyser) {
  const buf = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function voiceVadLoop() {
  if (!JARVIS_VOICE.active) return;

  const level = voiceRms(JARVIS_VOICE.analyser);
  const now = performance.now();
  const isSpeech = level > VAD_THRESHOLD;

  if (!JARVIS_VOICE.speaking && isSpeech && !JARVIS_VOICE.processing) {
    // início de fala detectado
    JARVIS_VOICE.speaking = true;
    JARVIS_VOICE.speechStart = now;
    JARVIS_VOICE.silenceStart = null;
    voiceBeginRecording();
    voiceSetMicVisual('speaking-user');
    voiceSetStatus('🎙 Ouvindo…', 'listening');
  } else if (JARVIS_VOICE.speaking) {
    if (isSpeech) {
      JARVIS_VOICE.silenceStart = null;
    } else {
      if (JARVIS_VOICE.silenceStart == null) JARVIS_VOICE.silenceStart = now;
      const silenceElapsed = now - JARVIS_VOICE.silenceStart;
      const speechElapsed = now - JARVIS_VOICE.speechStart;
      if (silenceElapsed > VAD_SILENCE_MS) {
        JARVIS_VOICE.speaking = false;
        if (speechElapsed > VAD_MIN_SPEECH_MS) {
          voiceEndRecording();
        } else {
          voiceCancelRecording();
        }
      }
    }
  }

  JARVIS_VOICE.vadLoopId = requestAnimationFrame(voiceVadLoop);
}

function voiceBeginRecording() {
  try {
    JARVIS_VOICE.chunks = [];
    const supported = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
      .find((type) => !MediaRecorder.isTypeSupported || MediaRecorder.isTypeSupported(type));
    const recorder = supported
      ? new MediaRecorder(JARVIS_VOICE.micStream, { mimeType: supported })
      : new MediaRecorder(JARVIS_VOICE.micStream);
    JARVIS_VOICE.mediaRecorder = recorder;
    recorder.ondataavailable = (e) => { if (e.data.size > 0) JARVIS_VOICE.chunks.push(e.data); };
    recorder.onerror = (e) => {
      JARVIS_VOICE.speaking = false;
      voiceSetStatus('Erro ao gravar o microfone: ' + (e.error?.message || 'MediaRecorder'), 'error');
    };
    recorder.start(100);
  } catch (e) {
    JARVIS_VOICE.speaking = false;
    voiceSetStatus('Não foi possível iniciar a gravação: ' + (e?.message || e), 'error');
  }
}

function voiceEndRecording() {
  if (JARVIS_VOICE.mediaRecorder && JARVIS_VOICE.mediaRecorder.state === 'recording') {
    JARVIS_VOICE.mediaRecorder.onstop = async () => {
      const blob = new Blob(JARVIS_VOICE.chunks, { type: 'audio/webm' });
      await handleVoiceCapture(blob);
    };
    JARVIS_VOICE.mediaRecorder.stop();
  }
}

function voiceCancelRecording() {
  if (JARVIS_VOICE.mediaRecorder && JARVIS_VOICE.mediaRecorder.state === 'recording') {
    JARVIS_VOICE.mediaRecorder.onstop = null;
    JARVIS_VOICE.mediaRecorder.stop();
  }
  voiceSetMicVisual('active-idle');
  voiceSetStatus('👂 Escuta automática ativa — fale quando quiser', 'listening');
}

let _voiceDiagPromise = null;
async function voiceGetDiagnosticsState() {
  if (_voiceDiagPromise) return _voiceDiagPromise;
  _voiceDiagPromise = new Promise((resolve) => {
    try {
      if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) return resolve(null);
      chrome.runtime.sendMessage({ type: 'GET_DIAGNOSTICS' }, (resp) => {
        void chrome.runtime.lastError;
        resolve(resp || null);
      });
    } catch (_) { resolve(null); }
  });
  try { return await _voiceDiagPromise; }
  finally { setTimeout(() => { _voiceDiagPromise = null; }, 200); }
}

async function voiceGetSystemContext() {
  try {
    const r = await voiceGetDiagnosticsState();
    const st = r?.state || {};
    const d = st.diagnostics || {};
    return {
      extension: { version: st.version || '12.6.17', mode: st.captureMode || 'unknown' },
      activeFixture: st.fixtureId ? { fixtureId: st.fixtureId, home: st.home, away: st.away, minute: st.minute, liveStatus: st.liveStatus } : null,
      capture: { health: st.captureHealth || null, quality: st.quality || null, dataMode: st.dataMode || null, completeness: st.dataCompleteness || null, lastUpdate: st.lastUpdate || 0 },
      diagnostics: { networkRequests: d.networkRequests || 0, networkResponses: d.networkResponses || 0, persistErrors: d.persistErrors || 0, staleSnapshots: d.staleSnapshots || 0, sourceConflicts: d.sourceConflicts || 0, localAiOk: d.lastLocalAiOk ?? null, localAiError: d.lastLocalAiError || null },
      intelligence: st.intelligence || null,
      sources: st.sources || null,
      webhook: st.webhook ? { bridgeOffline: !!st.webhook.bridgeOffline, lastOkAt: st.webhook.lastOkAt || 0, lastError: st.webhook.lastError || null, pending: st.webhook.pending || 0 } : null,
      recentErrors: Array.isArray(st.errors) ? st.errors.slice(-5) : [],
    };
  } catch (_) { return {}; }
}

// ---------- Weight of Money (v12.6.0) ----------
// Busca o bloco state.wom (linha/odd asiática + histórico) do background
// para anexar como contexto ao vivo nas chamadas ao Jarvis. Falha em
// silêncio (retorna null) — é dado opcional, nunca deve travar a voz.
async function voiceGetMarketStats() {
  try {
    const r = await voiceGetDiagnosticsState();
    return r?.state?.wom || null;
  } catch (_) {
    return null;
  }
}

// ---------- Jogo ativo: contexto compacto e sempre sincronizado ----------
async function voiceGetLoadedMatchContext() {
  try {
    const r = await voiceGetDiagnosticsState();
    const st = r?.state;
    if (!st?.fixtureId) return null;
    const pair = (key) => {
      const x = st.stats?.[key] || {};
      return { home: x.home ?? null, away: x.away ?? null };
    };
    return {
      fixtureId: st.fixtureId, home: st.home, away: st.away,
      minute: st.minute, extraMinute: st.extraMinute || 0,
      liveStatus: st.liveStatus, score: st.score || {},
      corners: pair('corners'), dangerous: pair('dangerous'),
      attacks: pair('attacks'), shotsOn: pair('shotsOn'),
      xg: pair('xg'), possession: pair('possession'),
      fouls: pair('fouls'), yellow: pair('yellow'), red: pair('red'),
      dataCompleteness: st.dataCompleteness, dataMode: st.dataMode,
      cornerEvents: (st.cornerEvents || []).slice(-8)
    };
  } catch (_) {
    return null;
  }
}

async function voiceWarmLocalEngine() {
  try {
    const r = await jarvisVoiceHealthCheck();
    if (r?.engineReady) voiceSetStatus('⚡ Voz local pronta — jogo em foco', 'ready');
    else if (r?.loading) voiceSetStatus('⚡ Preparando motor FAST…', 'processing');
  } catch (_) {}
}

// ---------- Pipeline streaming ----------
async function voiceFetchTalk(payload) {
  let resp = await fetch(JARVIS_VOICE.baseUrl + '/api/voice/talk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (resp.status === 503) {
    const info = await resp.clone().json().catch(() => ({}));
    if (info.loading || /Iniciando motores|ainda carregando/i.test(String(info.error || ''))) {
      voiceSetStatus('⏳ Preparando motores da IA…', 'processing');
      const ready = await voiceWaitEngineReady(90000);
      if (ready?.engineReady) {
        resp = await fetch(JARVIS_VOICE.baseUrl + '/api/voice/talk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
    }
  }

  if (!resp.ok || !resp.body) {
    const info = await resp.clone().json().catch(() => ({}));
    throw new Error(info.error || info.hint || ('HTTP ' + resp.status));
  }
  return resp;
}

async function handleVoiceCapture(blob) {
  JARVIS_VOICE.processing = true;
  voiceSetMicVisual('processing');
  voiceSetStatus('⏳ Processando…', 'processing');
  try {
    const audioBase64 = await blobToWavBase64(blob);
    const [marketStats, matchContext, systemContext] = await Promise.all([
      voiceGetMarketStats(),
      voiceGetLoadedMatchContext(),
      voiceGetSystemContext(),
    ]);
    const resp = await voiceFetchTalk({
      audio_base64: audioBase64,
      mime: 'audio/wav',
      session_id: voiceCurrentSessionId(),
      wake_required: JARVIS_VOICE.requireWakeWord,
      wake_word: JARVIS_VOICE.wakeWord,
      mood: JARVIS_VOICE.mood,
      market_stats: marketStats,
      match_context: matchContext,
      system_context: systemContext,
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let userText = '';
    let sawUser = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!line) continue;
        let evt;
        try { evt = JSON.parse(line); } catch (_) { continue; }

        if (evt.type === 'stt') {
          userText = evt.text || '';
          if (userText && !sawUser) {
            JARVIS_VOICE._lastUserText = userText;
            voiceAppendMessage('user', userText);
            sawUser = true;
            // Nunca ler a pergunta do usuário em voz alta
          }
        } else if (evt.type === 'segment') {
          const reply = voiceCleanForSpeech(evt.text || '');
          if (reply) voiceAppendMessage('ai', reply);
          voiceSetMicVisual('processing');
          voiceSetStatus('🔊 Respondendo…', 'speaking');
          if (evt.audio_base64) {
            voiceEnqueueAudio(evt.audio_base64, evt.audio_format || 'mp3');
          } else if (reply) {
            // Sempre fala a resposta (sem botão de aprovação)
            voiceSpeakAssistantOnly(reply, { role: 'ai' });
          }
        } else if (evt.type === 'done') {
          if (evt.skipped === 'no_wake_word') {
            voiceSetStatus('👂 Aguardando "' + JARVIS_VOICE.wakeWord + '"…', 'listening');
          }
        }
      }
    }
  } catch (e) {
    voiceSetStatus('Erro: ' + e.message, 'error');
  } finally {
    JARVIS_VOICE.processing = false;
    if (JARVIS_VOICE.active) {
      voiceSetMicVisual('active-idle');
      voiceSetStatus('👂 Escuta automática ativa — fale quando quiser', 'listening');
    } else {
      voiceSetMicVisual(null);
      voiceSetStatus('', null);
    }
  }
}

// ---------- Diagnóstico completo (botão 🩺 Testar Voz) ----------
async function voiceTestMic(ms = 700) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') await ctx.resume();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    let peak = 0;
    const t0 = performance.now();
    while (performance.now() - t0 < ms) {
      peak = Math.max(peak, voiceRms(analyser));
      await new Promise((r) => setTimeout(r, 40));
    }
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
    return { ok: true, label: 'Microfone do navegador', detail: `permissão concedida · nível de pico ${(peak * 100).toFixed(1)}%` };
  } catch (e) {
    return { ok: false, label: 'Microfone do navegador', detail: 'sem permissão ou sem dispositivo: ' + e.message };
  }
}

function voiceTestProfile() {
  const selected = voicePickPtVoice();
  if (selected) {
    return { ok: true, label: 'Perfil AURA Neural Antonio', detail: `${selected.name} · ${selected.lang}` };
  }
  return { ok: true, label: 'Perfil AURA Neural TTS · HumbertoNeural · masculino pt-BR', detail: 'Microsoft Edge Neural pt-BR-HumbertoNeural — sem SAPI, sem fallback feminino' };
}

async function voiceTestSpeaker() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error('Web Audio API não é suportada');
    const ctx = new AudioCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.05;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.15);
    osc.onended = () => ctx.close();
    return { ok: true, label: 'Alto-falante', detail: 'bipe de teste tocado — se não ouviu, confira o volume do sistema' };
  } catch (e) {
    return { ok: false, label: 'Alto-falante', detail: 'falha ao tocar áudio: ' + (e?.message || e) };
  }
}

function voiceEscapeHtml(value) {
  return String(value ?? '').replace(/[&<>\"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;' }[ch]));
}

function voiceDiagIconSpan(ok) {
  return `<span class="diag-icon ${ok ? 'diag-ok' : 'diag-fail'}">${ok ? '✅' : '❌'}</span>`;
}

function voiceRenderDiagnosticBubble(items, serverOffline) {
  const box = document.getElementById('chatMessages');
  const empty = document.getElementById('chatEmpty');
  if (!box) return;
  if (empty) empty.style.display = 'none';
  const row = document.createElement('div');
  row.className = 'bubble-row role-sys';
  const avatar = document.createElement('span');
  avatar.className = 'chat-avatar ai';
  avatar.textContent = '🩺';
  const col = document.createElement('div');
  col.className = 'bubble-col';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const list = items.map((it) => `<li>${voiceDiagIconSpan(it.ok)}<span>${voiceEscapeHtml(it.label)}${it.detail ? ' — <em>' + voiceEscapeHtml(it.detail) + '</em>' : ''}</span></li>`).join('');
  bubble.innerHTML = `<strong>Diagnóstico do sistema de voz</strong><ul class="diag-list">${list}</ul>`;
  if (serverOffline) {
    const btn = document.createElement('button');
    btn.className = 'diag-reload-btn';
    btn.textContent = '🔄 Recarregar motores';
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = 'Recarregando…';
      try { await fetch(JARVIS_VOICE.baseUrl + '/api/voice/reload', { method: 'POST' }); } catch (_) {}
      setTimeout(() => runVoiceDiagnostic(), 2000);
    };
    bubble.appendChild(btn);
  }
  col.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(col);
  box.appendChild(row);
  const scroll = document.getElementById('chatScroll');
  if (scroll) requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight; });
}

async function runVoiceDiagnostic() {
  const btn = document.getElementById('btnVoiceDiag');
  if (btn) { btn.disabled = true; btn.textContent = '🩺 Testando…'; btn.className = 'voice-diag-btn'; }

  const items = [];
  items.push(await voiceTestMic());
  items.push(await voiceTestSpeaker());
  items.push(voiceTestProfile());

  let serverOffline = false;
  try {
    const r = await fetch(JARVIS_VOICE.baseUrl + '/api/voice/diagnostic', { signal: AbortSignal.timeout(4000) });
    const d = await r.json();
    if (Array.isArray(d.checks)) {
      for (const c of d.checks) items.push({ ok: c.ok, label: c.label, detail: c.detail });
    } else {
      items.push({ ok: false, label: 'Servidor de voz', detail: 'resposta inesperada do servidor' });
    }
  } catch (e) {
    serverOffline = true;
    items.push({ ok: false, label: 'Servidor de voz (127.0.0.1:8099)', detail: voiceServerError(e) });
  }

  voiceRenderDiagnosticBubble(items, serverOffline);

  const allOk = items.every((i) => i.ok);
  if (btn) {
    btn.disabled = false;
    btn.textContent = allOk ? '🩺 Tudo OK' : '🩺 Testar Voz';
    btn.className = 'voice-diag-btn ' + (allOk ? 'good' : 'bad');
    setTimeout(() => { btn.className = 'voice-diag-btn'; btn.textContent = '🩺 Testar Voz'; }, 4000);
  }
}

// ---------- Humor / personalidade ----------
function initVoiceMoodControl() {
  const select = document.getElementById('voiceMoodSelect');
  if (!select) return;
  select.value = JARVIS_VOICE.mood;
  select.addEventListener('change', () => {
    JARVIS_VOICE.mood = select.value;
    try { localStorage.setItem('kanteiro_mood', select.value); } catch (_) {}
    voiceSetStatus('Humor definido: ' + select.options[select.selectedIndex].text, 'listening');
    setTimeout(() => { if (!JARVIS_VOICE.active) voiceSetStatus('', null); }, 1800);
  });
}

// ---------- Init ----------
function initVoiceWakeControls() {
  const toggle = document.getElementById('voiceWakeToggle');
  const input = document.getElementById('voiceWakeWordInput');
  const label = document.getElementById('voiceWakeWordLabel');
  if (!toggle || !input || !label) return;

  toggle.checked = JARVIS_VOICE.requireWakeWord;
  input.value = JARVIS_VOICE.wakeWord;
  label.textContent = JARVIS_VOICE.wakeWord;

  toggle.addEventListener('change', () => {
    JARVIS_VOICE.requireWakeWord = toggle.checked;
    try { localStorage.setItem('kanteiro_wake_required', toggle.checked ? '1' : '0'); } catch (_) {}
  });

  input.addEventListener('change', () => {
    const word = (input.value || 'kanteiro').trim().toLowerCase() || 'kanteiro';
    JARVIS_VOICE.wakeWord = word;
    label.textContent = word;
    try { localStorage.setItem('kanteiro_wake_word', word); } catch (_) {}
  });

  label.addEventListener('click', () => { input.hidden = !input.hidden; });
}

async function voiceWaitEngineReady(maxWaitMs = 90000) {
  // O servidor responde na hora (mesmo carregando) — poll até "engineReady"
  // em vez de desistir com uma mensagem genérica de "offline".
  const t0 = performance.now();
  while (performance.now() - t0 < maxWaitMs) {
    const health = await jarvisVoiceHealthCheck();
    if (health.engineReady) return health;
    if (health.error) return health;
    if (!health.loading && !health.ok) return health;
    voiceSetStatus('⏳ Preparando voz FAST (Whisper/Ollama)…', 'processing');
    await new Promise((r) => setTimeout(r, 350));
  }
  return { ok: true, engineReady: false, error: 'Tempo esgotado carregando os motores de voz.' };
}

function initVoiceAssistant() {
  voiceLoadSettings();
  // Modo conversa: sempre escutar e sempre responder (sem aprovação manual)
  try {
    if (localStorage.getItem('kanteiro_wake_required') == null) {
      localStorage.setItem('kanteiro_wake_required', '0');
    }
  } catch (_) {}
  JARVIS_VOICE.requireWakeWord = false;
  try { if (localStorage.getItem('kanteiro_wake_required') === '1') JARVIS_VOICE.requireWakeWord = true; } catch (_) {}
  initVoiceWakeControls();
  initVoiceMoodControl();
  initVoiceVoiceControl();

  const previewBtn = document.getElementById('btnVoicePreview');
  if (previewBtn) previewBtn.addEventListener('click', previewAuraVoice);

  const diagBtn = document.getElementById('btnVoiceDiag');
  if (diagBtn) diagBtn.addEventListener('click', runVoiceDiagnostic);

  const btn = document.getElementById('btnVoiceMic');
  if (!btn) return;

  btn.title = 'Ativar/desativar escuta automática (Kanteiro)';
  btn.addEventListener('click', async () => {
    if (JARVIS_VOICE.active) {
      voiceStopContinuousListening();
      return;
    }
    const health = await jarvisVoiceHealthCheck();
    if (!health.ok && !health.loading && !health.engineReady) {
      voiceSetStatus((health.error || 'Servidor de voz indisponível') + ' · use 🩺 Testar Voz para detalhes', 'error');
      return;
    }
    let ready = health;
    if (!health.engineReady) {
      ready = await voiceWaitEngineReady();
    }
    if (!ready.engineReady) {
      voiceSetStatus((ready.error || 'Motor de voz não ficou pronto') + ' · use 🩺 Testar Voz para detalhes', 'error');
      return;
    }
    voiceStartContinuousListening();
  });

  setTimeout(async () => {
    if (JARVIS_VOICE.active) return;
    try {
      const health = await jarvisVoiceHealthCheck();
      if (!health.ok && !health.engineReady && !health.loading) return;
      if (!health.engineReady) await voiceWaitEngineReady(20000);
      voiceStartContinuousListening();
      voiceSetStatus('Escuta contínua ativa. Fale — eu respondo em voz alta (sem botão).', 'listening');
    } catch (_) {}
  }, 1200);
}

document.addEventListener('DOMContentLoaded', initVoiceAssistant);

// Pré-aquecimento do servidor local sem esperar o primeiro comando.
setTimeout(voiceWarmLocalEngine, 50);
