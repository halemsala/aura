#!/usr/bin/env python3
"""AURA Neural TTS — voz masculina pt-BR natural (Jarvis BR).

Prioridade:
1. Microsoft Edge Neural — Antonio → Humberto → Nicolau
2. Fallback Google Translate TTS

Cache em duas camadas:
- RAM (LRU) para frases repetidas na mesma sessão (latência ~0)
- Disco (.tts_cache) com chave estável (voz|rate|pitch|texto normalizado)
- Eviction por tamanho (MAX_CACHE_MB) e idade (MAX_CACHE_FILES)
"""
from __future__ import annotations

import asyncio
import io
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import wave
from collections import OrderedDict
from typing import List, Optional, Tuple

CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".tts_cache"))
MAX_CHUNK = 320
# Limites de cache em disco (ajustáveis via env)
MAX_CACHE_MB = float(os.getenv("AURA_TTS_CACHE_MB", "64"))
MAX_CACHE_FILES = int(os.getenv("AURA_TTS_CACHE_FILES", "400"))
# LRU em RAM: quantos chunks MP3 manter (cada chunk ~10–40 KB típico)
RAM_CACHE_MAX = int(os.getenv("AURA_TTS_RAM_CACHE", "48"))
LOCAL_ONLY = os.getenv("AURA_LOCAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}  # default OFF — edge-tts liberado; use AURA_LOCAL_ONLY=1 para Piper puro
_HERCULES_ONNX = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "voices", "piper", "pt_BR-faber-medium.onnx"
))
_HERCULES_CFG = _HERCULES_ONNX + ".json"


def _piper_bin() -> str:
    return (os.getenv("AURA_PIPER_BIN") or "piper").strip() or "piper"


def _piper_model() -> str:
    env = (os.getenv("AURA_PIPER_MODEL") or "").strip()
    if env and os.path.isfile(env):
        return env
    if os.path.isfile(_HERCULES_ONNX):
        return _HERCULES_ONNX
    return env


def _piper_config() -> str:
    env = (os.getenv("AURA_PIPER_CONFIG") or "").strip()
    if env and os.path.isfile(env):
        return env
    if os.path.isfile(_HERCULES_CFG):
        return _HERCULES_CFG
    return env


def _tts_engine() -> str:
    return (os.getenv("AURA_TTS_ENGINE") or "edge").strip().lower()


PIPER_BIN = _piper_bin()
PIPER_MODEL = _piper_model()
PIPER_CONFIG = _piper_config()
TTS_ENGINE = _tts_engine()
REFERENCE_WAV = os.getenv(
    "AURA_REFERENCE_VOICE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "voices", "voz_masculina_referencia.wav")),
).strip()
XTTS_DEVICE = os.getenv("AURA_XTTS_DEVICE", "cpu").strip() or "cpu"
_XTTS_ENGINE = None
_XTTS_ERROR = None
_XTTS_LOCK = threading.Lock()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MALE_BASE = (
    "pt-BR-HumbertoNeural",
    "pt-BR-NicolauNeural",
    "pt-BR-DonatoNeural",
)
_APPROVED_MALE_VOICES = frozenset(list(_MALE_BASE) + [
    "Hercules", "HERCULES", "faber", "Faber", "Humberto", "humberto",
    "pt-BR-HumbertoNeural", "pt-BR-NicolauNeural", "pt-BR-DonatoNeural",
])
_REQUESTED_VOICE = os.getenv("KANTEIRO_NEURAL_VOICE", "pt-BR-HumbertoNeural").strip()
VOICE_SELECTION_ERROR = None
AURA_VOICE = _REQUESTED_VOICE or "pt-BR-HumbertoNeural"
VOICE_OPTIONS = {
    "hercules": "pt-BR-HumbertoNeural",
    "jarvis": "pt-BR-HumbertoNeural",
    "humberto": "pt-BR-HumbertoNeural",
    "faber": "pt-BR-HumbertoNeural",
    "nicolau": "pt-BR-NicolauNeural",
    "donato": "pt-BR-DonatoNeural",
}
if AURA_VOICE.lower() in VOICE_OPTIONS:
    AURA_VOICE = VOICE_OPTIONS[AURA_VOICE.lower()]
AURA_RATE = os.getenv("KANTEIRO_NEURAL_RATE", "-15%")
AURA_PITCH = os.getenv("KANTEIRO_NEURAL_PITCH", "-18Hz")
AURA_VOLUME = os.getenv("KANTEIRO_NEURAL_VOLUME", "+0%")

# Todas as tentativas são masculinas; não há fallback feminino.
MALE_VOICES: Tuple[str, ...] = tuple(
    dict.fromkeys([AURA_VOICE] + [v for v in _MALE_BASE if v != AURA_VOICE])
)

# ── stats / RAM LRU ──────────────────────────────────────────────────
_stats = {"hits_ram": 0, "hits_disk": 0, "misses": 0, "writes": 0, "evictions": 0}
_ram_lock = threading.Lock()
_ram_lru: "OrderedDict[str, bytes]" = OrderedDict()
_disk_lock = threading.Lock()
_last_prune_at = 0.0


def sanitize_for_speech(text: str) -> str:
    """Remove markdown e normaliza números/tokens operacionais para fala natural pt-BR.

    V24: word-boundary tokens (evita corromper DEV_MODE/REV_2) + % explícito.
    """
    s = str(text or "")
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[*#>`~|_^=\{\}\(\)]+", " ", s)
    s = re.sub(r"https?://\S+", "link", s)

    _TOKEN_MAP = {
        "xG": "xis gê",
        "EV": "ê vê",
        "HOLD": "aguardar",
        "BUY_CORNER": "entrada em escanteios",
        "WATCH_CORNER": "monitorar escanteios",
        "BLOCKED_BY_DATA": "bloqueado por dados",
        "GLM_ADVISORY_ONLY": "modo consultivo",
        "paper_trade": "paper trade",
    }
    _TOKEN_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _TOKEN_MAP) + r")\b")
    s = _TOKEN_RE.sub(lambda m: _TOKEN_MAP[m.group(1)], s)

    def frac(m):
        raw = m.group(1) if m.lastindex else m.group(0)
        try:
            n = float(str(raw).replace(",", "."))
        except Exception:
            return m.group(0)
        if 0 < abs(n) < 1:
            return f"{int(round(n * 100))} por cento"
        if abs(n) >= 100:
            return str(int(round(n)))
        rounded = round(n, 1)
        if abs(rounded - int(rounded)) < 1e-6:
            return str(int(rounded))
        return str(rounded).replace(".", ",")

    # Placar 2-1 → "2 a 1" (evita leitura ambígua no TTS)
    s = re.sub(r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})(?!\d)", r"\1 a \2", s)
    # Percent first so "12.5%" → "12,5 por cento"
    s = re.sub(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%", lambda m: frac(m) + " por cento", s)
    s = re.sub(r"(?<!\d)(\d+([.,]\d+)?)(?!\d)", frac, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def humanize_for_speech(text: str) -> str:
    """Pausas naturais sem reticências no início/fim (Edge cortava as sílabas)."""
    s = sanitize_for_speech(text)
    if not s:
        return s
    s = re.sub(r"\s*\.\.\.\s*", ", ", s)
    s = re.sub(r"([;:])\s+", r", ", s)
    s = s.strip(" .")
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _chunks(text: str) -> List[str]:
    # sanitize_for_speech already normalizes whitespace — no second re.sub
    clean = sanitize_for_speech(str(text or "")).strip()
    if not clean:
        return []
    if len(clean) <= MAX_CHUNK:
        return [clean]
    parts: List[str] = []
    buf = ""
    for piece in re.split(r"(?<=[\.\!\?;:])\s+", clean):
        piece = piece.strip()
        if not piece:
            continue
        if not buf:
            buf = piece
        elif len(buf) + 1 + len(piece) <= MAX_CHUNK:
            buf = buf + " " + piece
        else:
            parts.append(buf)
            buf = piece
    if buf:
        parts.append(buf)
    # Quebra forçada se ainda > MAX_CHUNK
    out: List[str] = []
    for p in parts:
        while len(p) > MAX_CHUNK:
            cut = p.rfind(" ", 0, MAX_CHUNK)
            if cut < 40:
                cut = MAX_CHUNK
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out


def _norm_key(engine: str, text: str) -> str:
    """Chave estável: engine + texto já sanitizado/normalizado."""
    norm = re.sub(r"\s+", " ", sanitize_for_speech(text)).strip().lower()
    return f"{engine}|{norm}"


def _cache_path(engine: str, text: str, suffix: str = ".mp3") -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(_norm_key(engine, text).encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}{suffix}")


def _ram_get(path: str) -> Optional[bytes]:
    with _ram_lock:
        if path in _ram_lru:
            _ram_lru.move_to_end(path)
            _stats["hits_ram"] += 1
            return _ram_lru[path]
    return None


def _ram_put(path: str, data: bytes) -> None:
    if not data:
        return
    with _ram_lock:
        if path in _ram_lru:
            _ram_lru.move_to_end(path)
            _ram_lru[path] = data
        else:
            _ram_lru[path] = data
            while len(_ram_lru) > RAM_CACHE_MAX:
                _ram_lru.popitem(last=False)
                _stats["evictions"] += 1


def _read_cache(path: str) -> Optional[bytes]:
    hit = _ram_get(path)
    if hit is not None:
        return hit
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            data = f.read()
        if not data or len(data) < 80:
            return None
        # Atualiza mtime para LRU em disco
        try:
            os.utime(path, None)
        except OSError:
            pass
        _stats["hits_disk"] += 1
        _ram_put(path, data)
        return data
    except OSError:
        return None


def _write_cache(path: str, data: bytes) -> None:
    if not data or len(data) < 80:
        return
    try:
        os.makedirs(os.path.dirname(path) or CACHE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
        _stats["writes"] += 1
        _ram_put(path, data)
        _maybe_prune_disk()
    except OSError:
        try:
            if os.path.isfile(path + ".tmp"):
                os.remove(path + ".tmp")
        except OSError:
            pass


def _maybe_prune_disk() -> None:
    """Remove arquivos antigos se passar do limite de MB ou de quantidade."""
    global _last_prune_at
    now = time.time()
    if now - _last_prune_at < 30:
        return
    with _disk_lock:
        if time.time() - _last_prune_at < 30:
            return
        _last_prune_at = time.time()
        try:
            files = []
            total = 0
            for name in os.listdir(CACHE_DIR):
                if not name.endswith((".mp3", ".wav")):
                    continue
                fp = os.path.join(CACHE_DIR, name)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, fp))
                total += st.st_size
            max_bytes = int(MAX_CACHE_MB * 1024 * 1024)
            if total <= max_bytes and len(files) <= MAX_CACHE_FILES:
                return
            # Mais antigos primeiro
            files.sort(key=lambda x: x[0])
            for mtime, size, fp in files:
                if total <= max_bytes and len(files) <= MAX_CACHE_FILES:
                    break
                try:
                    os.remove(fp)
                    total -= size
                    _stats["evictions"] += 1
                    with _ram_lock:
                        _ram_lru.pop(fp, None)
                except OSError:
                    pass
        except OSError:
            pass


def _xtts_engine():
    global _XTTS_ENGINE, _XTTS_ERROR
    if _XTTS_ENGINE is not None:
        return _XTTS_ENGINE
    with _XTTS_LOCK:
        if _XTTS_ENGINE is not None:
            return _XTTS_ENGINE
        if _XTTS_ERROR is not None:
            raise RuntimeError(_XTTS_ERROR)
        try:
            from .tts import TTSEngine
            _XTTS_ENGINE = TTSEngine(
                device=XTTS_DEVICE,
                reference_voice=REFERENCE_WAV,
                language="pt",
                speed=1.05,
                cache_dir=os.path.join(CACHE_DIR, "xtts"),
                cache_max=MAX_CACHE_FILES,
            )
            return _XTTS_ENGINE
        except Exception as exc:
            _XTTS_ERROR = f"xtts_reference_unavailable:{type(exc).__name__}:{exc}"
            raise RuntimeError(_XTTS_ERROR) from exc


def _float_audio_to_wav(audio) -> bytes:
    import numpy as np

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        raise RuntimeError("xtts_empty")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(pcm)
    return output.getvalue()


def _synthesize_xtts(text: str) -> bytes:
    if not os.path.isfile(REFERENCE_WAV):
        raise RuntimeError(f"xtts_reference_missing:{REFERENCE_WAV}")
    path = _cache_path(f"xtts|{XTTS_DEVICE}|{REFERENCE_WAV}", text, suffix=".wav")
    cached = _read_cache(path)
    if cached:
        return cached
    _stats["misses"] += 1
    audio = _xtts_engine().synthesize(text, speed_mult=1.0, use_cache=True)
    data = _float_audio_to_wav(audio)
    _write_cache(path, data)
    return data


def _piper_executable() -> str:
    executable = shutil.which(_piper_bin())
    if executable:
        return executable
    candidate = os.path.abspath(_piper_bin())
    if os.path.isfile(candidate):
        return candidate
    raise RuntimeError("piper_bin_missing")


def _synthesize_piper(text: str) -> bytes:
    model = _piper_model()
    if not model or not os.path.isfile(model):
        raise RuntimeError("piper_model_missing")
    executable = _piper_executable()
    cache_path = _cache_path(f"piper|{model}", text, suffix=".wav")
    cached = _read_cache(cache_path)
    if cached:
        return cached
    _stats["misses"] += 1
    fd, temporary = tempfile.mkstemp(prefix="aura-piper-", suffix=".wav", dir=CACHE_DIR)
    os.close(fd)
    try:
        command = [executable, "--model", model, "--output_file", temporary]
        cfg = _piper_config()
        if cfg and os.path.isfile(cfg):
            command.extend(["--config", cfg])
        result = subprocess.run(
            command,
            input=sanitize_for_speech(text) + "\\n",
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "piper_failed").strip()[-300:]
            raise RuntimeError(f"piper_failed:{detail}")
        with open(temporary, "rb") as handle:
            data = handle.read()
        if len(data) < 80 or data[:4] != b"RIFF":
            raise RuntimeError("piper_invalid_wav")
        _write_cache(cache_path, data)
        return data
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


async def _edge_chunk(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=AURA_RATE,
        pitch=AURA_PITCH,
        volume=AURA_VOLUME,
    )
    chunks: List[bytes] = []
    async for item in communicate.stream():
        if item.get("type") == "audio":
            chunks.append(item["data"])
    data = b"".join(chunks)
    if not data or len(data) < 200:
        raise RuntimeError("edge_tts_empty")
    return data


def _synthesize_edge(text: str) -> bytes:
    if LOCAL_ONLY:
        raise RuntimeError("edge_tts_blocked_local_only")
    last_err: Optional[Exception] = None
    for voice in MALE_VOICES:
        path = _cache_path(f"edge|{voice}|{AURA_RATE}|{AURA_PITCH}|{AURA_VOLUME}", text)
        cached = _read_cache(path)
        if cached:
            return cached
        _stats["misses"] += 1
        try:
            data = asyncio.run(_edge_chunk(text, voice))
            _write_cache(path, data)
            return data
        except Exception as exc:
            last_err = exc
            continue
    raise last_err or RuntimeError("edge_tts_fail")


def _fetch_gtts_chunk(text: str, lang: str = "pt-BR") -> bytes:
    path = _cache_path(f"gtts|{lang}", text)
    cached = _read_cache(path)
    if cached:
        return cached
    _stats["misses"] += 1
    query = urllib.parse.urlencode(
        {"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": text}
    )
    req = urllib.request.Request(
        "https://translate.google.com/translate_tts?" + query,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Referer": "https://translate.google.com/",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = resp.read()
    if not data or len(data) < 80:
        raise RuntimeError("gtts_empty")
    _write_cache(path, data)
    return data


def _concat_wav_blobs(blobs: List[bytes]) -> bytes:
    if not blobs:
        return b""
    first_params = None
    frames: List[bytes] = []
    for blob in blobs:
        with wave.open(io.BytesIO(blob), "rb") as reader:
            params = reader.getparams()
            if first_params is None:
                first_params = params
            elif (params.nchannels, params.sampwidth, params.framerate, params.comptype) != (
                first_params.nchannels, first_params.sampwidth, first_params.framerate, first_params.comptype
            ):
                raise RuntimeError("piper_wav_format_mismatch")
            frames.append(reader.readframes(reader.getnframes()))
    assert first_params is not None
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(first_params.nchannels)
        writer.setsampwidth(first_params.sampwidth)
        writer.setframerate(first_params.framerate)
        writer.writeframes(b"".join(frames))
    return output.getvalue()


def pad_audio_edges(data: bytes, ms: int = 320) -> bytes:
    """Silêncio no começo e no fim para o Edge/MediaPlayer não cortar a frase."""
    if not data or data[:4] != b"RIFF":
        return data
    try:
        reader = wave.open(io.BytesIO(data), "rb")
        params = reader.getparams()
        frames = reader.readframes(reader.getnframes())
        reader.close()
        n = int(params.framerate * max(80, ms) / 1000.0) * params.nchannels
        silence = b"\x00" * (n * params.sampwidth)
        output = io.BytesIO()
        writer = wave.open(output, "wb")
        writer.setparams(params)
        writer.writeframes(silence + frames + silence)
        writer.close()
        return output.getvalue()
    except Exception:
        return data


def synthesize_mp3(text: str, lang: str = "pt-BR") -> bytes:
    clean = humanize_for_speech(str(text or "")).strip()
    if len(clean) > 480:
        clean = clean[:480].rsplit(" ", 1)[0].rstrip(",;:") + "."
    pieces = _chunks(clean)
    if not pieces:
        raise ValueError("texto vazio")
    engine = _tts_engine()
    if engine in {"xtts", "xtts-reference", "reference"}:
        return pad_audio_edges(_concat_wav_blobs([_synthesize_xtts(part) for part in pieces]))
    force_piper = LOCAL_ONLY or engine in {"piper", "faber", "local"}
    if force_piper:
        return pad_audio_edges(_concat_wav_blobs([_synthesize_piper(part) for part in pieces]))
    try:
        blobs = [_synthesize_edge(part) for part in pieces]
        data = b"".join(blobs)
        return pad_audio_edges(data) if data[:4] == b"RIFF" else data
    except Exception as exc:
        if os.path.isfile(_piper_model() or "") and _piper_executable_available():
            return pad_audio_edges(_concat_wav_blobs([_synthesize_piper(part) for part in pieces]))
        raise RuntimeError(f"tts_male_unavailable:{exc}") from exc


def cache_stats() -> dict:
    disk_files = 0
    disk_bytes = 0
    try:
        for name in os.listdir(CACHE_DIR):
            if not name.endswith(".mp3"):
                continue
            fp = os.path.join(CACHE_DIR, name)
            try:
                disk_bytes += os.path.getsize(fp)
                disk_files += 1
            except OSError:
                pass
    except OSError:
        pass
    with _ram_lock:
        ram_entries = len(_ram_lru)
        ram_bytes = sum(len(v) for v in _ram_lru.values())
    hits = _stats["hits_ram"] + _stats["hits_disk"]
    total = hits + _stats["misses"]
    return {
        "hits_ram": _stats["hits_ram"],
        "hits_disk": _stats["hits_disk"],
        "misses": _stats["misses"],
        "writes": _stats["writes"],
        "evictions": _stats["evictions"],
        "hit_rate": round(hits / total, 3) if total else None,
        "ram_entries": ram_entries,
        "ram_bytes": ram_bytes,
        "disk_files": disk_files,
        "disk_bytes": disk_bytes,
        "disk_mb": round(disk_bytes / (1024 * 1024), 2),
        "max_cache_mb": MAX_CACHE_MB,
        "max_cache_files": MAX_CACHE_FILES,
        "cache_dir": CACHE_DIR,
    }


def clear_cache(ram: bool = True, disk: bool = False) -> dict:
    """Limpa cache RAM e/ou disco. disk=True apaga .tts_cache/*.mp3."""
    removed = 0
    if ram:
        with _ram_lock:
            _ram_lru.clear()
    if disk:
        try:
            for name in os.listdir(CACHE_DIR):
                if name.endswith(".mp3") or name.endswith(".wav") or name.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, name))
                        removed += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return {"ram_cleared": ram, "disk_removed": removed, "cache_dir": CACHE_DIR}


def _piper_executable_available() -> bool:
    try:
        _piper_executable()
        return True
    except Exception:
        return False


def available() -> dict:
    model = _piper_model()
    piper_ready = bool(model and os.path.isfile(model) and _piper_executable_available())
    if LOCAL_ONLY or _tts_engine() in {"piper", "faber", "local"}:
        return {
            "engine": "aura-hercules-piper",
            "voice": "hercules",
            "voiceOptions": VOICE_OPTIONS,
            "lang": "pt-BR",
            "gender": "male",
            "format": "wav",
            "local_only": True,
            "ready": piper_ready,
            "edge_tts": False,
            "gtts": False,
            "piper": True,
            "profile": "hercules",
            "model": model,
            "cache_dir": CACHE_DIR,
            "cache": cache_stats(),
            "rate": AURA_RATE,
            "pitch": AURA_PITCH,
        }
    has_edge = False
    try:
        import edge_tts  # noqa: F401

        has_edge = True
    except Exception:
        has_edge = False
    reference_present = os.path.isfile(REFERENCE_WAV)
    xtts_installed = False
    try:
        import importlib.util
        xtts_installed = importlib.util.find_spec("TTS") is not None
    except Exception:
        xtts_installed = False
    reference_mode = TTS_ENGINE in {"xtts", "xtts-reference", "reference"}
    runtime_engine = "aura-xtts-reference" if reference_mode else ("aura-neural-jarvis-br" if has_edge else "unavailable-male-edge")
    runtime_ready = bool((reference_mode and xtts_installed and reference_present) or (not reference_mode and has_edge and not VOICE_SELECTION_ERROR))
    return {
        "engine": runtime_engine,
        "voice": "voz_masculina_referencia.wav" if reference_mode else (AURA_VOICE if has_edge else None),
        "voiceOptions": VOICE_OPTIONS,
        "lang": "pt-BR",
        "gender": "male" if (reference_mode or has_edge) else "unknown",
        "ready": runtime_ready,
        "fallback": "disabled",
        "selection_error": VOICE_SELECTION_ERROR,
        "error": None if runtime_ready else ("edge_tts_male_unavailable" if not reference_mode else "xtts_reference_unavailable"),
        "needs_windows_voice": False,
        "reference_wav": REFERENCE_WAV,
        "reference_present": reference_present,
        "reference_mode": reference_mode,
        "xtts_installed": xtts_installed,
        "edge_tts": has_edge,
        "cache_dir": CACHE_DIR,
        "cache": cache_stats(),
        "rate": AURA_RATE,
        "pitch": AURA_PITCH,
    }


# --- V23 BLOCO 6: API publica de cache TTS em disco ---
async def get_tts_cached(text: str, voice: str = "hercules") -> str:
    """Retorna caminho do mp3 em cache; gera via edge_tts se miss."""
    import hashlib as _hashlib
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _hashlib.sha256(f"{text}_{voice}".encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, f"pub_{key}.mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 80:
        return cache_path
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(cache_path)
        return cache_path
    except Exception as e:
        raise RuntimeError(f"tts_cache_fail:{e}") from e


def sanitize_for_speech_v24(text: str) -> str:
    """Compose neural_tts sanitize + PhoneticSanitizerV23 when available."""
    base = sanitize_for_speech(text)
    try:
        try:
            from engine.core.phonetic_sanitizer_v23 import phonetic_sanitizer_v23
        except Exception:
            from core.phonetic_sanitizer_v23 import phonetic_sanitizer_v23  # type: ignore
        return phonetic_sanitizer_v23.sanitize(base)
    except Exception:
        return base

