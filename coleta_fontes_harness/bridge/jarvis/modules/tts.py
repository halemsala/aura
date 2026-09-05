
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

"""Text-to-Speech local-first com XTTS-v2, cache persistente e warmup."""
import os
import hashlib
import logging
import sys
from pathlib import Path as _Path

logger = logging.getLogger("aura.tts")
import json
import numpy as np

try:
    _scripts = _Path(__file__).resolve().parents[3] / "scripts"
    if _scripts.is_dir() and str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))
    from aura_xtts_compat import apply_all as _aura_xtts_apply

    _aura_xtts_apply()
except Exception:
    pass

try:
    from TTS.api import TTS as CoquiTTS
except ImportError:
    CoquiTTS = None


class TTSEngine:
    def __init__(self, device, reference_voice, language, speed, output_device=None,
                 cache_dir=None, cache_max=300):
        if CoquiTTS is None:
            raise RuntimeError("Coqui TTS não instalado; use neural_tts/Edge TTS ou instale o extra opcional coqui-tts")
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        print(f"[tts] Carregando XTTS-v2 em {device}...")
        self.tts = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        self.reference_voice = reference_voice
        self.language = language
        self.speed = speed
        self.output_device = output_device
        self.has_reference = os.path.isfile(reference_voice)
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), "..", "..", ".voice_cache")
        self.cache_dir = os.path.abspath(self.cache_dir)
        self.cache_max = max(50, int(cache_max))
        os.makedirs(self.cache_dir, exist_ok=True)
        self._memory_cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._warmed = False
        if not self.has_reference:
            print(f"[tts] AVISO: voz de referência '{reference_voice}' não encontrada. Usando voz padrão.")

    def _key(self, text, speed_mult):
        raw = f"{self.language}|{self.speed:.4f}|{float(speed_mult):.4f}|{text.strip()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _cache_path(self, key):
        return os.path.join(self.cache_dir, key + ".npy")

    def _read_cache(self, key):
        if key in self._memory_cache:
            self._cache_hits += 1
            return self._memory_cache[key].copy()
        path = self._cache_path(key)
        if os.path.isfile(path):
            try:
                audio = np.load(path, allow_pickle=False).astype(np.float32)
                self._memory_cache[key] = audio
                self._cache_hits += 1
                return audio.copy()
            except Exception as exc:
                logger.debug("Cache TTS inválido; removendo %s: %s", path, exc)
                try:
                    os.remove(path)
                except OSError as remove_exc:
                    logger.debug("Não foi possível remover cache TTS %s: %s", path, remove_exc)
        self._cache_misses += 1
        return None

    def _write_cache(self, key, audio):
        try:
            np.save(self._cache_path(key), audio.astype(np.float32), allow_pickle=False)
            self._memory_cache[key] = audio.astype(np.float32)
            if len(self._memory_cache) > self.cache_max:
                oldest = next(iter(self._memory_cache))
                self._memory_cache.pop(oldest, None)
        except Exception as exc:
            print(f"[tts] cache write ignorado: {exc}")

    def synthesize(self, text: str, speed_mult: float = 1.0, use_cache: bool = True) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.array([], dtype=np.float32)
        key = self._key(text, speed_mult)
        if use_cache:
            cached = self._read_cache(key)
            if cached is not None:
                return cached

        effective_speed = max(0.5, min(2.0, self.speed * speed_mult))
        kwargs = dict(text=text, language=self.language, speed=effective_speed)
        if self.has_reference:
            kwargs["speaker_wav"] = self.reference_voice
        else:
            kwargs["speaker"] = self.tts.speakers[0] if self.tts.speakers else None
        wav = np.array(self.tts.tts(**kwargs), dtype=np.float32)
        if use_cache and wav.size:
            self._write_cache(key, wav)
        return wav

    def warmup(self):
        """Força uma primeira inferência curta para aquecer modelo/GPU e cache."""
        if self._warmed:
            return
        phrase = "Motor de voz local pronto."
        self.synthesize(phrase, speed_mult=1.0, use_cache=True)
        self._warmed = True
        print("[tts] XTTS-v2 aquecido; cache local pronto.")

    def stats(self):
        return {
            "warmed": self._warmed,
            "memoryEntries": len(self._memory_cache),
            "cacheHits": self._cache_hits,
            "cacheMisses": self._cache_misses,
            "cacheDir": self.cache_dir,
        }

    def speak(self, text: str):
        import sounddevice as sd
        audio = self.synthesize(text)
        if audio.size == 0:
            return
        sd.play(audio, samplerate=24000, device=self.output_device)
        sd.wait()
