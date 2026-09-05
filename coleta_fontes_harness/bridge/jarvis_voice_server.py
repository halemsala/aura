from __future__ import annotations

try:
    import sys as _sys
    from pathlib import Path as _CompatPath
    _scripts = _CompatPath(__file__).resolve().parents[1] / "scripts"
    if _scripts.is_dir() and str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from aura_xtts_compat import apply_all as _aura_xtts_apply
    _aura_xtts_apply()
except Exception:
    pass


# V24: higieniza texto antes de TTS
try:
    from engine.core.voice.speech_sanitizer import speech_sanitizer as _AURA_SPEECH
except Exception:
    try:
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        from engine.core.voice.speech_sanitizer import speech_sanitizer as _AURA_SPEECH
    except Exception:
        _AURA_SPEECH = None

def _aura_sanitize_speech(text: str) -> str:
    if _AURA_SPEECH is not None:
        try:
            return _AURA_SPEECH.sanitize(text)
        except Exception:
            pass
    return text or ""

# bridge/jarvis_voice_server.py
# AURA QUANT-X v12.7.0-RECONSOLIDADO — Jarvis Voice + EventBus SUB + GLMDecodingRouter

import asyncio
import base64
import io
import json
import logging
import os
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from engine.agents.jarvis_command_center import CommandCenter, build_default_tools
except Exception:
    CommandCenter = None  # type: ignore[assignment,misc]
    build_default_tools = None  # type: ignore[assignment]

try:
    from engine.agents.pc_operator import PcOperator, build_pc_tools
except Exception:
    PcOperator = None  # type: ignore[assignment,misc]
    build_pc_tools = None  # type: ignore[assignment]

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

logger = logging.getLogger("aura.jarvis_voice")

ZMQ_SUB_ADDR = os.environ.get("AURA_ZMQ_SUB_ADDR", "tcp://127.0.0.1:5555")
VOICE_PORT = int(os.environ.get("AURA_VOICE_PORT", "8099"))
VOICE_BUILD_ID = os.environ.get("AURA_VOICE_BUILD_ID", "AURA-VOICE-MALE-V3")
# POLITICA IMUTAVEL DE VOZ (Manual Mestre)
REQUIRED_VOICE_BUILD_ID = "AURA-VOICE-MALE-V3"
ALLOWED_MALE_VOICES = [
    "hercules", "Hercules", "HERCULES", "faber", "Faber",
    "HumbertoNeural", "NicolauNeural", "DonatoNeural", "AntonioNeural",
    "pt-BR-HumbertoNeural", "pt-BR-NicolauNeural", "pt-BR-DonatoNeural",
    "pt-BR-AntonioNeural", "pt-BR-faber-medium",
]


_MARKET_CONTEXT: Dict[str, Any] = {
    "odds": 0.0, "line": 0.0, "velocity": 0.0, "decision": "HOLD",
    "wom_text": "", "poisson_text": "", "ts": 0,
}
_CTX_LOCK = threading.Lock()


class AuraEventBusSubscriber:
    def __init__(self, connect_addr: str = ZMQ_SUB_ADDR):
        self._addr = connect_addr
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ready = False

    def start(self) -> None:
        if not ZMQ_AVAILABLE:
            logger.warning("pyzmq unavailable — SUB disabled")
            return
        self._thread = threading.Thread(target=self._loop, name="aura-zmq-sub", daemon=True)
        self._thread.start()
        self._ready = True

    def _loop(self) -> None:
        try:
            ctx = zmq.Context.instance()
            sock = ctx.socket(zmq.SUB)
            sock.setsockopt(zmq.RCVHWM, 1000)
            sock.setsockopt_string(zmq.SUBSCRIBE, "aura.analysis")
            sock.setsockopt_string(zmq.SUBSCRIBE, "aura.feedback")
            sock.connect(self._addr)
            logger.info("AuraEventBus SUB connected to %s", self._addr)
            while not self._stop.is_set():
                try:
                    if sock.poll(500):
                        parts = sock.recv_multipart(flags=zmq.NOBLOCK)
                        if len(parts) >= 2:
                            topic = parts[0].decode("utf-8", errors="ignore")
                            payload = json.loads(parts[1].decode("utf-8"))
                            self._on_message(topic, payload)
                except zmq.Again:
                    continue
                except Exception as e:
                    logger.debug("SUB recv error: %s", e)
                    time.sleep(0.05)
            sock.close(0)
        except Exception as e:
            logger.error("SUB loop fatal: %s", e)

    def _on_message(self, topic: str, payload: Dict[str, Any]) -> None:
        global _MARKET_CONTEXT
        if topic == "aura.analysis":
            with _CTX_LOCK:
                _MARKET_CONTEXT = {
                    "odds": float(payload.get("asian_corner_odds", 0.0)),
                    "line": float(payload.get("asian_corner_line", 0.0)),
                    "velocity": float(payload.get("odds_velocity", 0.0)),
                    "decision": str(payload.get("decision", "HOLD")),
                    "wom_text": str(payload.get("wom_text", "")),
                    "poisson_text": str(payload.get("poisson_text", "")),
                    "ts": int(payload.get("ts", time.time())),
                }

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


class GLMDecodingRouter:
    ROUTES = {
        "BUY_CORNER": {"temperature": 0.25, "top_p": 0.80, "max_tokens": 96, "repetition_penalty": 1.15,
                       "system_bias": "Priorize acao imediata e disciplina de stake. Seja assertivo."},
        "WATCH_CORNER": {"temperature": 0.35, "top_p": 0.85, "max_tokens": 120, "repetition_penalty": 1.10,
                         "system_bias": "Observe e descreva a confluencia. Nao force entrada."},
        "HOLD": {"temperature": 0.40, "top_p": 0.90, "max_tokens": 80, "repetition_penalty": 1.05,
                 "system_bias": "Mantenha neutralidade. Sem edge claro."},
        "BLOCKED_BY_MARKET": {"temperature": 0.20, "top_p": 0.75, "max_tokens": 64, "repetition_penalty": 1.20,
                              "system_bias": "Bloqueio ativo. Recomende abortar qualquer entrada."},
    }

    @classmethod
    def resolve(cls, decision: str) -> Dict[str, Any]:
        return dict(cls.ROUTES.get(decision, cls.ROUTES["HOLD"]))

    @classmethod
    def apply_to_ollama_options(cls, decision: str, base: Optional[Dict[str, Any]] = None):
        route = cls.resolve(decision)
        opts = dict(base or {})
        opts["temperature"] = route["temperature"]
        opts["top_p"] = route["top_p"]
        opts["num_predict"] = route["max_tokens"]
        opts["repeat_penalty"] = route["repetition_penalty"]
        return opts, route["system_bias"]


app = FastAPI(title="AURA Jarvis Voice", version=VOICE_BUILD_ID)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://aura.local", "http://aura.local"],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CornerAI-Token", "X-Requested-With"],
)
_sub = AuraEventBusSubscriber()

ROOT_DIR = Path(__file__).resolve().parent
JARVIS_DIR = ROOT_DIR / "jarvis"
CONFIG_PATH = JARVIS_DIR / "config.yaml"
_ENGINE_LOCK = threading.RLock()
_ENGINE_STATE: Dict[str, Any] = {
    "loading": False,
    "ready": False,
    "started_at": time.time(),
    "error": None,
    "device": "unknown",
    "stt": None,
    "llm": None,
}
_STT_ENGINE = None
_LLM_ENGINE = None
_PARALLEL_PIPELINE = None
_COMMANDS = None
_PC_OPERATOR = None
_MIC_LOCK = threading.Lock()
_EAR_STOP = threading.Event()
_EAR_STATE: Dict[str, Any] = {"running": False, "last": "", "hits": 0, "device": ""}


def _read_config() -> dict:
    try:
        import yaml
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except Exception as exc:
        logger.warning("Configuração do Jarvis indisponível: %s", exc)
        return {}


def _edge_rate(value: Any) -> str:
    if isinstance(value, (int, float)):
        ratio = float(value)
        if 0.5 <= ratio <= 1.5:
            return f"{round((ratio - 1.0) * 100):+d}%"
    text = str(value or "-8%").strip()
    return text if text.endswith("%") else "-8%"


def _edge_pitch(value: Any) -> str:
    if isinstance(value, (int, float)):
        ratio = float(value)
        if 0.7 <= ratio <= 1.3:
            return f"{int(round((ratio - 1.0) * 100)):+d}Hz"
        return "-4Hz"
    text = str(value or "-4Hz").strip()
    return text if text.lower().endswith("hz") else "-4Hz"


def _configure_tts_env(cfg: Optional[dict] = None) -> dict:
    cfg = cfg or _read_config()
    tts_cfg = cfg.get("tts") or {}
    voice_cfg = cfg.get("voice") or {}
    # O YAML é autoritativo para não reutilizar uma voz feminina/legada do ambiente.
    requested = str(tts_cfg.get("voice_name") or os.environ.get("KANTEIRO_NEURAL_VOICE") or "pt-BR-HumbertoNeural").strip()
    os.environ["KANTEIRO_NEURAL_VOICE"] = requested or "pt-BR-HumbertoNeural"
    os.environ["KANTEIRO_NEURAL_RATE"] = _edge_rate(tts_cfg.get("base_rate"))
    os.environ["KANTEIRO_NEURAL_PITCH"] = _edge_pitch(tts_cfg.get("base_pitch"))
    os.environ["KANTEIRO_NEURAL_VOLUME"] = "+0%"
    hercules_model = os.path.abspath(os.path.join(os.path.dirname(__file__), "jarvis", "voices", "piper", "pt_BR-faber-medium.onnx"))
    if os.path.isfile(hercules_model):
        os.environ.setdefault("AURA_PIPER_MODEL", hercules_model)
        os.environ.setdefault("AURA_PIPER_CONFIG", hercules_model + ".json")
    configured_engine = str(tts_cfg.get("provider") or voice_cfg.get("preferred_engine") or "edge").strip().lower()
    if bool(voice_cfg.get("xtts_enabled")):
        os.environ["AURA_TTS_ENGINE"] = "xtts-reference"
    elif configured_engine in {"piper", "faber", "hercules", "local"}:
        os.environ["AURA_TTS_ENGINE"] = "piper"
    else:
        os.environ["AURA_TTS_ENGINE"] = "edge"
    return cfg


def _voice_profile_info() -> Dict[str, Any]:
    cfg = _configure_tts_env()
    voice_cfg = cfg.get("voice") or {}
    tts_cfg = cfg.get("tts") or {}
    reference = JARVIS_DIR / "voices" / "voz_masculina_referencia.wav"
    profile = ROOT_DIR.parent / "voice_profiles" / "PERFIL_ASSISTENTE_ESPORTIVO_ANALITICO.md"
    prompt = ROOT_DIR.parent / "voice_profiles" / "PROMPT_GROK_VOZ_MASCULINA.md"
    try:
        from jarvis.modules.neural_tts import available as tts_available
        tts_runtime = tts_available()
    except Exception as exc:
        tts_runtime = {"ready": False, "engine": "unavailable", "voice": None, "gender": "unknown", "error": str(exc), "fallback": "disabled"}
    return {
        "active_profile": voice_cfg.get("active_profile", "assistente_esportivo_analitico"),
        "preferred_engine": voice_cfg.get("preferred_engine", "edge-tts"),
        "configured_voice": tts_cfg.get("voice_name", "hercules"),
        "tts_runtime": tts_runtime,
        "reference_wav": str(reference),
        "reference_present": reference.is_file(),
        "profile_file": str(profile),
        "profile_present": profile.is_file(),
        "style_prompt_file": str(prompt),
        "style_prompt_present": prompt.is_file(),
        "reference_is_model": False,
        "note": "WAV e referencia documental; nao contem pesos de clonagem TTS.",
    }


def _load_engines(force: bool = False) -> None:
    global _STT_ENGINE, _LLM_ENGINE
    with _ENGINE_LOCK:
        if _ENGINE_STATE["loading"]:
            return
        if _ENGINE_STATE["ready"] and not force:
            return
        _ENGINE_STATE.update({"loading": True, "error": None})
    try:
        cfg = _read_config()
        device_cfg = cfg.get("device") or {}
        stt_cfg = cfg.get("stt") or {}
        llm_cfg = cfg.get("llm") or {}
        try:
            from jarvis.modules.device import resolve_device, recommend_llm_runtime, get_llm_model
            device = resolve_device(str(device_cfg.get("mode") or "auto"))
            runtime = recommend_llm_runtime(device)
        except Exception as exc:
            logger.warning("Resolvedor de dispositivo indisponível; usando CPU: %s", exc)
            device = "cpu"
            runtime = {"profile": "cpu", "num_gpu": 0, "num_ctx": 2048, "num_batch": 128, "temperature": 0.25}
        from jarvis.modules.stt import STT
        stt = STT(
            model_name=str(stt_cfg.get("model") or "base"),
            device="cpu",
            language=str(stt_cfg.get("language") or "pt"),
            compute_type_gpu="float16",
            compute_type_cpu="int8",
        )
        llm = None
        model_ready = True
        global _PARALLEL_PIPELINE
        with _ENGINE_LOCK:
            _STT_ENGINE = stt
            _LLM_ENGINE = llm
            _ENGINE_STATE.update({
                "loading": False,
                "ready": bool(stt),
                "error": None,
                "device": "cpu",
                "stt": stt.stats(),
                "llm": {"ok": True, "note": "LLM é o Hermes/Alfred qwen3:8b — voz não carrega segundo modelo"},
            })
        if model_ready:
            try:
                from jarvis.parallel_audio_pipeline import ParallelAudioPipeline
                _PARALLEL_PIPELINE = ParallelAudioPipeline(
                    prewarm_fn=lambda ctx: _update_market_context({"market_stats": ctx or {}}),
                    tts_fn=_synthesize_bytes,
                )
                logger.info("Pilar 4 integrado ao Voice: pipeline paralelo ativo")
            except Exception as exc:
                _PARALLEL_PIPELINE = None
                logger.warning("Pilar 4 indisponível; fallback de voz sequencial: %s", exc)
        logger.info("Motores de voz carregados; STT CPU pronto=%s (LLM = Hermes qwen3:8b)", bool(stt))
    except Exception as exc:
        with _ENGINE_LOCK:
            _ENGINE_STATE.update({"loading": False, "ready": False, "error": str(exc)})
        logger.exception("Falha ao carregar motores de voz")


def _start_lazy_init(force: bool = False) -> bool:
    with _ENGINE_LOCK:
        if _ENGINE_STATE["loading"]:
            return False
        if _ENGINE_STATE["ready"] and not force:
            return True
        thread = threading.Thread(target=_load_engines, args=(force,), name="aura-voice-loader", daemon=True)
        thread.start()
        return False


def _snapshot_state() -> dict:
    with _ENGINE_LOCK:
        state = dict(_ENGINE_STATE)
        state["build_id"] = VOICE_BUILD_ID
        llm = _LLM_ENGINE
        state["llmHealth"] = llm.health() if llm is not None else {
            "ok": True, "requested_model": "qwen3:8b", "active_model": "hermes/alfred",
            "available_models": ["qwen3:8b"], "fallback_models": [], "last_error": None,
            "note": "voz não carrega segundo LLM — qwen3:8b fica no Hermes/Alfred",
        }
        state["engineReady"] = bool(state.get("ready"))
        state["voiceProfile"] = _voice_profile_info()
        state["parallelAudio"] = _PARALLEL_PIPELINE.get_stats() if _PARALLEL_PIPELINE is not None else {"active": False}
        state["uptimeS"] = max(0, int(time.time() - float(state.get("started_at") or time.time())))
        state.pop("started_at", None)
        return state


def _mood_instruction(mood: str) -> str:
    return {
        "baixo": "Tom sóbrio, direto e sem humor.",
        "medio": "Tom técnico, humano e com humor sutil.",
        "alto": "Tom técnico, mais energético e espirituoso, sem perder disciplina.",
    }.get(str(mood or "medio").lower(), "Tom técnico, humano e com humor sutil.")


def _context_text(payload: dict) -> str:
    context = {
        "market_stats": payload.get("market_stats") or {},
        "match_context": payload.get("match_context") or {},
        "system_context": payload.get("system_context") or {},
    }
    raw = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
    return raw[:8000]


def _decode_audio_to_tempfile(audio_base64: str) -> str:
    if not audio_base64:
        raise ValueError("audio_base64 ausente")
    encoded = str(audio_base64)
    if "," in encoded and encoded.lower().split(",", 1)[0].startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    if len(encoded) > 20_000_000:
        raise ValueError("áudio excede o limite de 15 MB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("audio_base64 inválido") from exc
    if not data:
        raise ValueError("áudio vazio")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("áudio excede o limite de 15 MB")
    handle = tempfile.NamedTemporaryFile(prefix="aura-voice-", suffix=".wav", delete=False)
    try:
        handle.write(data)
        handle.flush()
        return handle.name
    finally:
        handle.close()


def _require_ready() -> Optional[JSONResponse]:
    state = _snapshot_state()
    if state.get("loading"):
        return JSONResponse(status_code=503, content={"ok": False, "loading": True, "engineReady": False, "error": "Iniciando motores de voz; tente novamente em alguns segundos."})
    if not state.get("engineReady"):
        _start_lazy_init(force=False)
        return JSONResponse(status_code=503, content={"ok": False, "loading": True, "engineReady": False, "error": state.get("error") or "Motores de voz ainda não estão prontos."})
    return None


@app.on_event("startup")
async def _startup():
    global _COMMANDS, _PC_OPERATOR
    _sub.start()
    _start_lazy_init()
    if _COMMANDS is None and CommandCenter is not None and build_default_tools is not None:
        try:
            def _voice_state_line():
                state = _snapshot_state()
                if state.get("loading"):
                    return "carregando motores"
                return "pronta" if state.get("engineReady") else "degradada"

            _COMMANDS = build_default_tools(CommandCenter(), deps={
                "voice_state_fn": _voice_state_line,
                "voice_reload_fn": lambda: _start_lazy_init(force=True),
                "urls": {
                    "bridge": "http://127.0.0.1:8080/health",
                    "engine": "http://127.0.0.1:8765/api/status",
                },
            })
            logger.info("CommandCenter ativo: %d ferramentas", len(_COMMANDS.list_tools()))
        except Exception:
            logger.exception("CommandCenter falhou ao inicializar; voz segue em modo chat")
            _COMMANDS = None
    if _COMMANDS is not None and PcOperator is not None and build_pc_tools is not None:
        try:
            project_root = Path(__file__).resolve().parents[1]
            configured = os.environ.get("AURA_PC_ALLOWED_ROOTS", "")
            raw_roots = [item for item in configured.split(os.pathsep) if item.strip()]
            if not raw_roots:
                raw_roots = [
                    str(Path.home() / "Desktop"),
                    str(Path.home() / "Documents"),
                    str(Path.home() / "Downloads"),
                    str(project_root),
                ]
            roots = [Path(item) for item in raw_roots if Path(item).exists()]
            if project_root.exists() and str(project_root) not in {str(p) for p in roots}:
                roots.append(project_root)
            _PC_OPERATOR = PcOperator(roots=roots, project_root=project_root)
            build_pc_tools(_COMMANDS, _PC_OPERATOR, root=project_root)
            logger.info("PcOperator ativo: %d raízes permitidas", len(roots))
        except Exception:
            logger.exception("PcOperator indisponível; ferramentas de arquivo não registradas")
            _PC_OPERATOR = None
    logger.info("Jarvis Voice server startup complete; inicialização dos motores em background")
    if os.environ.get("AURA_EAR", "1") != "0":
        threading.Thread(target=_ear_loop, name="aura-ear", daemon=True).start()


@app.on_event("shutdown")
async def _shutdown():
    global _PARALLEL_PIPELINE
    _sub.stop()
    if _PARALLEL_PIPELINE is not None:
        try:
            _PARALLEL_PIPELINE.shutdown()
        except Exception as exc:
            logger.warning("Falha ao encerrar Pilar 4: %s", exc)
        _PARALLEL_PIPELINE = None


class VoiceRequest(BaseModel):
    odds: float = 0.0
    linha: float = 0.0
    estado: str = "HOLD"
    context: str = ""
    text: str = ""
    session_id: str = "default"
    mood: str = "medio"
    audio_base64: str = ""
    mime: str = "audio/wav"
    wake_required: bool = False
    wake_word: str = "kanteiro"
    market_stats: Dict[str, Any] = Field(default_factory=dict)
    match_context: Dict[str, Any] = Field(default_factory=dict)
    system_context: Dict[str, Any] = Field(default_factory=dict)


def _build_prompt(estado: str, odds: float, linha: float, extra: str = "") -> str:
    with _CTX_LOCK:
        ctx = dict(_MARKET_CONTEXT)
    route = GLMDecodingRouter.resolve(estado)
    bias = route["system_bias"]
    parts = [
        f"Estado: {estado}", f"Odds: {odds:.4f}", f"Linha: {linha:.2f}",
        f"Velocity: {ctx.get('velocity', 0.0):.4f}",
        f"WOM: {ctx.get('wom_text', '')}", f"Poisson: {ctx.get('poisson_text', '')}",
        f"Instrucao: {bias}",
    ]
    if extra:
        parts.append(f"Contexto extra: {extra[:200]}")
    return " | ".join(parts)


async def _stream_voice_ndjson(odds: float, linha: float, estado: str, context: str = ""):
    opts, bias = GLMDecodingRouter.apply_to_ollama_options(estado)
    yield json.dumps({
        "type": "context",
        "data": f"[CONTEXTO] Odds={odds:.4f} Linha={linha:.2f} Estado={estado} | {bias}",
        "router": opts,
    }) + "\n"
    await asyncio.sleep(0.05)
    script = f"Alerta quant. Estado {estado}. Odds {odds:.2f} linha {linha:.1f}. {bias}"
    words = script.split()
    buf = []
    for w in words:
        buf.append(w)
        if len(buf) >= 3:
            yield json.dumps({"type": "audio_chunk", "text": " ".join(buf)}) + "\n"
            buf = []
            await asyncio.sleep(0.28)
    if buf:
        yield json.dumps({"type": "audio_chunk", "text": " ".join(buf)}) + "\n"


def _update_market_context(payload: dict) -> None:
    market = payload.get("market_stats") or {}
    with _CTX_LOCK:
        _MARKET_CONTEXT.update({
            "odds": float(market.get("asian_corner_odds", market.get("odds", 0.0)) or 0.0),
            "line": float(market.get("asian_corner_line", market.get("line", 0.0)) or 0.0),
            "velocity": float(market.get("odds_velocity", market.get("velocity", 0.0)) or 0.0),
            "decision": str(payload.get("decision") or market.get("decision") or "HOLD"),
            "wom_text": str(market.get("wom_text") or ""),
            "poisson_text": str(market.get("poisson_text") or ""),
            "ts": int(time.time()),
        })


def _llm_ready_response() -> Optional[JSONResponse]:
    with _ENGINE_LOCK:
        llm = _LLM_ENGINE
        loading = bool(_ENGINE_STATE.get("loading"))
    if loading:
        return JSONResponse(status_code=503, content={"ok": False, "loading": True, "engineReady": False, "error": "Iniciando motores de voz."})
    if llm is None:
        _start_lazy_init()
        return JSONResponse(status_code=503, content={"ok": False, "loading": True, "engineReady": False, "error": "Motores de voz ainda não carregados."})
    if not llm.ensure_model():
        return JSONResponse(status_code=503, content={"ok": False, "loading": False, "engineReady": False, "error": llm.last_error or "Ollama/modelo indisponível."})
    return None


def _stt_ready_response() -> Optional[JSONResponse]:
    with _ENGINE_LOCK:
        stt = _STT_ENGINE
        loading = bool(_ENGINE_STATE.get("loading"))
    if loading or stt is None:
        _start_lazy_init()
        return JSONResponse(status_code=503, content={"ok": False, "loading": True, "engineReady": False, "error": "Whisper ainda está carregando."})
    return None


def _wav_rms(path: str) -> float:
    try:
        with wave.open(path, "rb") as reader:
            frames = reader.readframes(reader.getnframes())
            width = reader.getsampwidth() or 2
        if width == 2 and frames:
            import array
            samples = array.array("h")
            samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
            if not samples:
                return 0.0
            acc = sum(int(s) * int(s) for s in samples)
            return (acc / len(samples)) ** 0.5 / 32768.0
    except Exception:
        return -1.0
    return 0.0


def _transcribe_path(path: str) -> str:
    with _ENGINE_LOCK:
        stt = _STT_ENGINE
    if stt is None:
        raise RuntimeError("stt_not_ready")
    return str(stt.transcribe(path, loose=True) or "").strip()


def _transcribe_file(path: str) -> str:
    try:
        return _transcribe_path(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _record_windows_mic(seconds: float = 8.0) -> dict:
    import sys as _sys
    root = str(Path(__file__).resolve().parents[1])
    if root not in _sys.path:
        _sys.path.insert(0, root)
    from alfred.mic_capture import record as _record
    return _record(seconds=seconds, prefer="realtek")


def _listen_windows(seconds: float = 8.0) -> dict:
    with _MIC_LOCK:
        rec = _record_windows_mic(seconds)
        path = rec.get("path")
    text = ""
    try:
        if path and not rec.get("silent"):
            text = _transcribe_path(path)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
    rec.pop("path", None)
    rec["text"] = text
    rec["ok"] = True
    rec["nota"] = (
        "microfone em silêncio — escolhe Conjunto de microfones Realtek em Som → Entrada e tira o mudo"
        if rec.get("silent") and not text else ""
    )
    _EAR_STATE["device"] = rec.get("device") or ""
    _EAR_STATE["last"] = text[:120]
    return rec


WAKE_WORDS = ("alfred", "aura", "hermes", "hercules")


def _ear_loop() -> None:
    """Sempre a ouvir o microfone Windows. Só age com palavra de acordar."""
    import urllib.request
    _EAR_STATE["running"] = True
    logger.info("ear: a ouvir o microfone Windows (wake: Alfred)")
    while not _EAR_STOP.is_set():
        try:
            with _ENGINE_LOCK:
                ready = _STT_ENGINE is not None
            if not ready:
                _EAR_STOP.wait(2.0)
                continue
            with _MIC_LOCK:
                probe = _record_windows_mic(0.6)
            probe_path = probe.get("path")
            if probe_path:
                try:
                    os.remove(probe_path)
                except OSError:
                    pass
            if probe.get("rms", 0) < 0.012:
                _EAR_STOP.wait(0.15)
                continue
            rec = _listen_windows(7.0)
            text = str(rec.get("text") or "").strip()
            low = text.casefold()
            if not text or not any(w in low for w in WAKE_WORDS):
                continue
            if not low.startswith("alfred"):
                text = "Alfred, " + text
            _EAR_STATE["hits"] = int(_EAR_STATE.get("hits") or 0) + 1
            logger.info("ear ouviu: %s", text[:160])
            payload = json.dumps(
                {"message": text, "use_memory": True, "session_id": "ear"},
                ensure_ascii=False,
            ).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8777/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
                reply = str(body.get("reply") or "")[:400]
                if reply:
                    try:
                        audio = _synthesize_bytes(reply)
                        # não reproduz daqui — o chat/Alfred fala; evita eco no mic
                        logger.info("ear resposta %d chars", len(reply))
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("ear chat falhou: %s", exc)
            _EAR_STOP.wait(8.0)
        except Exception as exc:
            logger.warning("ear loop: %s", exc)
            _EAR_STOP.wait(1.5)
    _EAR_STATE["running"] = False


def _synthesize_bytes(text: str) -> bytes:
    cfg = _configure_tts_env()
    from jarvis.modules.neural_tts import available as tts_available, synthesize_mp3
    runtime = tts_available()
    if not runtime.get("ready") or runtime.get("gender") != "male":
        raise RuntimeError(f"tts_male_not_ready:{runtime.get('error') or runtime.get('engine')}")
    return synthesize_mp3(text, lang="pt-BR")


def _audio_format(data: bytes) -> str:
    return "wav" if data[:4] == b"RIFF" else "mp3"


def _reply_from_text(req: VoiceRequest) -> str:
    with _ENGINE_LOCK:
        llm = _LLM_ENGINE
    if llm is None:
        raise RuntimeError("llm_not_ready")
    _update_market_context(req.model_dump())
    context = req.context or _context_text(req.model_dump())
    return llm.ask(
        req.session_id or "default",
        req.text.strip(),
        mood_instruction=_mood_instruction(req.mood),
        context=context,
        max_tokens=96,
    )


async def _talk_events(req: VoiceRequest):
    started = time.perf_counter()
    text = req.text.strip()
    if not text and req.audio_base64:
        path = _decode_audio_to_tempfile(req.audio_base64)
        try:
            text = await asyncio.to_thread(_transcribe_file, path)
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
    if not text:
        yield json.dumps({"type": "done", "skipped": "empty_input"}, ensure_ascii=False) + "\n"
        return
    if req.wake_required and req.wake_word.lower() not in text.lower():
        yield json.dumps({"type": "stt", "text": text}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "done", "skipped": "no_wake_word"}, ensure_ascii=False) + "\n"
        return
    yield json.dumps({"type": "stt", "text": text}, ensure_ascii=False) + "\n"
    global _PARALLEL_PIPELINE
    if _COMMANDS is not None:
        try:
            command_result = await asyncio.to_thread(
                _COMMANDS.handle_utterance, text, req.session_id or "default")
            if command_result is not None:
                spoken = _aura_sanitize_speech(str(command_result.get("speech") or ""))
                event: Dict[str, Any] = {
                    "type": "segment",
                    "text": spoken,
                    "command": {
                        "tool": command_result.get("tool"),
                        "awaiting_confirmation": bool(command_result.get("awaiting_confirmation")),
                        "cancelled": bool(command_result.get("cancelled")),
                    },
                }
                try:
                    audio = await asyncio.to_thread(_synthesize_bytes, spoken)
                    event["audio_base64"] = base64.b64encode(audio).decode("ascii")
                    event["audio_format"] = _audio_format(audio)
                except Exception as exc:
                    logger.info("TTS indisponivel para comando: %s", exc)
                yield json.dumps(event, ensure_ascii=False) + "\n"
                yield json.dumps({"type": "done", "command": True}, ensure_ascii=False) + "\n"
                return
        except Exception:
            logger.exception("CommandCenter falhou; seguindo para o chat normal")
    if _PARALLEL_PIPELINE is not None:
        try:
            def stream_reply(prompt: str, max_tokens: int = 72):
                parallel_req = req.model_copy(update={"text": prompt})
                reply_text = _reply_from_text(parallel_req)
                return reply_text
            parallel = await asyncio.to_thread(
                _PARALLEL_PIPELINE.process_text,
                req.session_id or "default",
                text,
                {**(req.market_stats or {}), **(req.match_context or {})},
                stream_reply,
                _synthesize_bytes,
            )
            for segment in parallel.get("segments", []):
                event: Dict[str, Any] = {"type": "segment", "text": segment.get("text", "")}
                audio = segment.get("audio")
                if audio:
                    event["audio_base64"] = base64.b64encode(audio).decode("ascii")
                    event["audio_format"] = _audio_format(audio)
                yield json.dumps(event, ensure_ascii=False) + "\n"
            yield json.dumps({
                "type": "done",
                "latency_ms": parallel.get("latency_ms"),
                "first_segment_ms": parallel.get("first_segment_ms"),
                "parallel": True,
            }, ensure_ascii=False) + "\n"
            return
        except Exception as exc:
            logger.warning("Pilar 4 falhou; usando fallback sequencial: %s", exc)
    reply = await asyncio.to_thread(_reply_from_text, req)
    # Divide por frases para preservar a experiência de primeira resposta rápida.
    pieces = [part.strip() for part in __import__("re").split(r"(?<=[.!?])\s+", reply) if part.strip()]
    if not pieces:
        pieces = [reply]
    for piece in pieces[:8]:
        event: Dict[str, Any] = {"type": "segment", "text": piece}
        try:
            audio = await asyncio.to_thread(_synthesize_bytes, piece)
            event["audio_base64"] = base64.b64encode(audio).decode("ascii")
            event["audio_format"] = _audio_format(audio)
        except Exception as exc:
            logger.warning("TTS não disponível para segmento: %s", exc)
        yield json.dumps(event, ensure_ascii=False) + "\n"
    yield json.dumps({
        "type": "done",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "first_segment_ms": round((time.perf_counter() - started) * 1000, 2),
    }, ensure_ascii=False) + "\n"


@app.post("/api/voice/stt")
async def voice_stt(req: VoiceRequest):
    guard = _stt_ready_response()
    if guard:
        return guard
    try:
        path = _decode_audio_to_tempfile(req.audio_base64)
        rms = _wav_rms(path)
        text = await asyncio.to_thread(_transcribe_file, path)
        silent = rms >= 0 and rms < 0.008
        return {
            "ok": True,
            "text": text,
            "language": "pt",
            "rms": round(float(rms), 5),
            "silent": silent,
            "nota": "microfone em silêncio — dispositivo errado ou mudo" if silent and not text else "",
        }
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    except Exception as exc:
        logger.exception("Falha no STT")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


class ListenRequest(BaseModel):
    seconds: float = 8.0
    session_id: str = "chat"
    prefer: str = "realtek"


@app.post("/api/voice/listen")
async def voice_listen(req: ListenRequest):
    """Grava o microfone do Windows (Realtek) e transcreve. Não usa o browser."""
    guard = _stt_ready_response()
    if guard:
        return guard
    try:
        rec = await asyncio.to_thread(_listen_windows, float(req.seconds or 8))
        rec["language"] = "pt"
        rec["ear"] = dict(_EAR_STATE)
        return rec
    except Exception as exc:
        logger.exception("Falha a gravar microfone Windows")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)[:300]})


@app.get("/api/voice/mic")
async def voice_mic():
    try:
        import sys as _sys
        root = str(Path(__file__).resolve().parents[1])
        if root not in _sys.path:
            _sys.path.insert(0, root)
        from alfred.mic_capture import list_input_devices, pick_device
        chosen = pick_device("realtek")
        return {"ok": True, "device": chosen, "devices": list_input_devices(), "ear": dict(_EAR_STATE)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)[:300]})


@app.post("/api/voice/chat")
async def voice_chat(req: VoiceRequest):
    guard = _llm_ready_response()
    if guard:
        return guard
    if not req.text.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "text ausente"})
    try:
        reply = await asyncio.to_thread(_reply_from_text, req)
        return {"ok": True, "reply": reply, "reply_text": reply, "session_id": req.session_id or "default"}
    except Exception as exc:
        logger.exception("Falha no chat de voz")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.post("/api/voice/tts")
@app.post("/api/voice/neural")
async def voice_tts(req: VoiceRequest):
    if not req.text.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "text ausente"})
    try:
        audio = await asyncio.to_thread(_synthesize_bytes, req.text)
        encoded = base64.b64encode(audio).decode("ascii")
        audio_format = "wav" if audio[:4] == b"RIFF" else "mp3"
        runtime = _voice_profile_info().get("tts_runtime") or {}
        return {"ok": True, "audio_base64": encoded, "tts_base64": encoded, "audio_format": audio_format, "format": audio_format, "voice": runtime.get("voice"), "engine": runtime.get("engine"), "gender": runtime.get("gender"), "fallback": "disabled", "reference_present": runtime.get("reference_present", False)}
    except Exception as exc:
        logger.warning("TTS indisponível: %s", exc)
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc), "hint": "Instale edge-tts ou configure Piper local."})


@app.post("/api/voice/talk")
async def voice_talk(req: VoiceRequest):
    stt_guard = _stt_ready_response() if req.audio_base64 else None
    llm_guard = _llm_ready_response()
    if stt_guard:
        return stt_guard
    if llm_guard:
        return llm_guard
    return StreamingResponse(_talk_events(req), media_type="application/x-ndjson")


@app.get("/api/voice/tools")
async def voice_tools():
    if _COMMANDS is None:
        return {"ok": False, "tools": [], "error": "command_center indisponivel"}
    return {"ok": True, "tools": _COMMANDS.list_tools(), "stats": _COMMANDS.stats()}


@app.post("/api/voice/command")
async def voice_command(req: VoiceRequest):
    if _COMMANDS is None:
        return JSONResponse(status_code=503, content={"ok": False, "error": "command_center indisponivel"})
    if not req.text.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "text ausente"})
    result = await asyncio.to_thread(_COMMANDS.handle_utterance, req.text.strip(), req.session_id or "default")
    if result is None:
        return {"ok": True, "handled": False, "hint": "nao era comando; use /api/voice/chat"}
    return {"ok": True, "handled": True, **result}


@app.get("/api/voice/alerts")
async def voice_alerts():
    if _COMMANDS is None:
        return {"ok": False, "alerts": []}
    return {"ok": True, "alerts": _COMMANDS.take_alerts(10)}


@app.get("/api/voice/diagnostic")
async def voice_diagnostic():
    # V23 BLOCO 4: obrigacao do build de voz
    current_build = VOICE_BUILD_ID
    if current_build != REQUIRED_VOICE_BUILD_ID:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "error": "POLICY_VIOLATION",
                "expected_build": REQUIRED_VOICE_BUILD_ID,
                "current_build": current_build,
                "msg": "Mate o processo na porta 8099 e inicie o build correto.",
            },
        )
    try:
        _cfg_voice = str((tts_cfg if "tts_cfg" in dir() else {}).get("voice_name") or os.environ.get("KANTEIRO_NEURAL_VOICE") or "hercules")
    except Exception:
        _cfg_voice = os.environ.get("KANTEIRO_NEURAL_VOICE", "hercules")
    _voice_short = _cfg_voice.split("-")[-1] if "-" in _cfg_voice else _cfg_voice
    if _cfg_voice not in ALLOWED_MALE_VOICES and _voice_short not in ALLOWED_MALE_VOICES:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"error": "GENDER_POLICY_VIOLATION", "msg": "Voz feminina ou generica detectada.", "voice": _cfg_voice},
        )

    state = _snapshot_state()
    with _ENGINE_LOCK:
        stt = _STT_ENGINE
        llm = _LLM_ENGINE
    voice_info = _voice_profile_info()
    runtime = voice_info.get("tts_runtime") or {}
    checks = [
        {"id": "server", "ok": True, "label": "Servidor de voz", "detail": f"porta {VOICE_PORT}"},
        {"id": "stt", "ok": stt is not None, "label": "Whisper STT", "detail": (stt.stats() if stt else "não carregado")},
        {"id": "ollama", "ok": bool(llm and llm.available_models), "label": "Ollama", "detail": (llm.health() if llm else "não consultado")},
        {"id": "llm_model", "ok": bool(llm and llm.model and llm.last_ok), "label": "Modelo LLM", "detail": (llm.model if llm and llm.model else "não resolvido")},
        {"id": "voice_reference", "ok": voice_info["reference_present"], "label": "Voz de referência", "detail": voice_info["reference_wav"]},
        {"id": "voice_profile", "ok": voice_info["profile_present"] and voice_info["style_prompt_present"], "label": "Perfil e prompt", "detail": voice_info["active_profile"]},
        {"id": "tts_runtime", "ok": runtime.get("ready") and runtime.get("gender") == "male", "label": "TTS masculino efetivo", "detail": f"{runtime.get('engine')} · {runtime.get('voice')} · fallback={runtime.get('fallback')}"},
    ]
    return {"ok": all(item["ok"] for item in checks), "build_id": VOICE_BUILD_ID, "checks": checks, "voiceProfile": voice_info, "voiceRuntime": runtime, "state": state}


@app.post("/api/voice/reload")
async def voice_reload():
    _start_lazy_init(force=True)
    return {"ok": True, "loading": True, "message": "Nova tentativa de carregamento iniciada."}


@app.post("/api/voice/reset_session")
async def voice_reset_session(req: VoiceRequest):
    with _ENGINE_LOCK:
        llm = _LLM_ENGINE
    if llm:
        llm.reset_session(req.session_id or "default")
    return {"ok": True, "session_id": req.session_id or "default"}


@app.get("/api/voice/stream")
async def voice_stream(odds: float = 0.0, linha: float = 0.0, estado: str = "HOLD", context: str = ""):
    return StreamingResponse(
        _stream_voice_ndjson(odds, linha, estado, context),
        media_type="application/x-ndjson",
    )


@app.post("/api/voice/plan")
async def voice_plan(req: VoiceRequest):
    opts, bias = GLMDecodingRouter.apply_to_ollama_options(req.estado)
    with _CTX_LOCK:
        ctx = dict(_MARKET_CONTEXT)
    return {
        "estado": req.estado,
        "router_options": opts,
        "system_bias": bias,
        "live_context": ctx,
        "prompt_preview": _build_prompt(req.estado, req.odds, req.linha, req.context)[:300],
    }


@app.get("/api/voice/context")
async def voice_context():
    with _CTX_LOCK:
        return dict(_MARKET_CONTEXT)


@app.get("/api/health")
async def health():
    state = _snapshot_state()
    return {
        "status": "ok",
        "service": "jarvis_voice",
        "version": VOICE_BUILD_ID,
        "build_id": VOICE_BUILD_ID,
        "process_up": True,
        "engineReady": state.get("engineReady", False),
        "loading": state.get("loading", False),
        "device": state.get("device"),
        "llmHealth": state.get("llmHealth"),
        "error": state.get("error"),
        "zmq_sub": ZMQ_AVAILABLE,
        "port": VOICE_PORT,
        "ts": int(time.time()),
        "uptimeS": state.get("uptimeS", 0),
    }

@app.get("/api/voice/health")
async def health_voice_alias():
    return await health()

@app.get("/health")
async def health_root_alias():
    return await health()


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="AURA QUANT-X Voice/Jarvis")
    parser.add_argument("--host", default=os.environ.get("AURA_VOICE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=VOICE_PORT)
    parser.add_argument("--lazy", action="store_true", help="mantém STT/TTS pesado em inicialização lazy")
    args = parser.parse_args()
    VOICE_PORT = args.port
    if args.lazy:
        os.environ["AURA_VOICE_LAZY"] = "1"
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, log_level="info")
