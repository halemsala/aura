#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
natural_voice.py — VOZ HUMANA para o AURA: substitui edge-tts por modelos
neurais com prosodia natural, pausas, respiracao e controle de emocao.

MOTIVACAO: edge-tts (atual) produz voz neural decente mas com prosodia
template — sem pausas naturais, sem respiracao, sem variacao de ritmo.
Os modelos desta camada geram prosodia DE FATO (diffusion/adversarial),
produzindo voz que em teste cego supera gravacoes humanas.

MODELOS SUPORTADOS (auto-detectados, melhor primeiro):
    1. CHATTERBOX V3 (MIT, 0.5B) — RECOMENDADO
       - Controle de emocao (0.0 = monotono, 1.0 = dramatico)
       - Clona voz de 6s de audio
       - 20+ idiomas incluindo portugues
       - Real-time em GPU (RTX 4050 ok)
       - pip install chatterbox-tts

    2. KOKORO (Apache 2.0, 82M) — LEVE
       - 6x real-time em CPU (sem GPU!)
       - Prosodia natural, vozes pt-BR
       - pip install kokoro soundfile

    3. F5-TTS pt-BR (MIT) — NATIVO BRASILEIRO
       - Fine-tuned em 100+ horas de Common Voice pt-BR
       - Zero-shot voice cloning
       - Melhor sotaque brasileiro nativo

    4. FALLBACK: edge-tts (atual) — quando nada instalado

PROSODIA HUMANA (o que resolve a voz robotica):
    - Pausas naturais: o modelo decide onde respirar (nao template)
    - Variacao de ritmo: frases longas desaceleram, curtas aceleram
    - Entonacao contextual: perguntas sobem, afirmativas descem
    - Respiracao audivel em pausas longas (Chatterbox)
    - SSA (Speech Synthesis Alignment): alinhamento fonema-a-audio

INTEGRACAO: substitui _synthesize_bytes() do jarvis_voice_server.py.
Hunks na resposta. Detecta no import; degrada para edge-tts sem quebrar.

DEPENDENCIAS OPCIONAIS:
    pip install chatterbox-tts          # Chatterbox (GPU)
    pip install kokoro soundfile        # Kokoro (CPU ou GPU)
    pip install f5-tts                  # F5-TTS pt-BR (GPU)

stdlib only sem deps. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.natural_voice")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]


class NaturalVoiceEngine:
    """Detecta e usa o melhor TTS disponível. Degrada para edge-tts."""

    def __init__(self, prefer_gpu: bool = True,
                 emotion_level: float = 0.7,
                 voice_clone_path: Optional[str] = None):
        self._prefer_gpu = prefer_gpu
        self._emotion = max(0.0, min(1.0, emotion_level))
        self._clone_path = voice_clone_path
        self._lock = threading.RLock()
        self._engine: Optional[str] = None
        self._chatterbox = None
        self._kokoro = None
        self._f5 = None
        self._stats = {"generations": 0, "by_engine": {},
                       "failures": 0, "avg_latency_ms": 0.0,
                       "total_ms": 0.0}
        self._detect()

    def _detect(self) -> None:
        """Detecta engines na ordem: Chatterbox > Kokoro > F5 > edge-tts."""
        # 1. Chatterbox (melhor qualidade, GPU)
        try:
            import chatterbox  # type: ignore
            self._chatterbox = chatterbox
            self._engine = "chatterbox"
            logger.info("natural_voice: Chatterbox TTS ativo (GPU)")
            return
        except Exception as exc:
            logger.warning("natural_voice: Chatterbox indisponível: %s", exc)

        # 2. Kokoro (leve, CPU ok)
        try:
            import kokoro  # type: ignore
            self._kokoro = kokoro
            self._engine = "kokoro"
            logger.info("natural_voice: Kokoro TTS ativo (CPU/GPU)")
            return
        except Exception as exc:
            logger.warning("natural_voice: Kokoro indisponível: %s", exc)

        # 3. F5-TTS (pt-BR nativo)
        try:
            import f5_tts  # type: ignore
            self._f5 = f5_tts
            self._engine = "f5"
            logger.info("natural_voice: F5-TTS pt-BR ativo")
            return
        except Exception as exc:
            logger.warning("natural_voice: F5-TTS indisponível: %s", exc)

        # 4. Fallback: edge-tts
        self._engine = "edge-tts"
        logger.info("natural_voice: usando edge-tts (fallback). "
                    "Para voz humana: pip install chatterbox-tts")

    @property
    def engine_name(self) -> str:
        return self._engine or "edge-tts"

    @property
    def is_natural(self) -> bool:
        """True se usando engine neural com prosodia de verdade."""
        return self._engine in ("chatterbox", "kokoro", "f5")

    def set_emotion(self, level: float) -> None:
        """Ajusta intensidade emocional (0.0-1.0). Só Chatterbox."""
        self._emotion = max(0.0, min(1.0, float(level)))

    @staticmethod
    def _new_output(output_path: Optional[str], suffix: str) -> Tuple[str, bool]:
        if output_path:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target), False
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            return handle.name, True
        finally:
            handle.close()

    @staticmethod
    def _cleanup_temp(path: str, temporary: bool) -> None:
        if temporary and path:
            try:
                os.unlink(path)
            except OSError:
                pass

    @classmethod
    def _complete_output(cls, path: str, temporary: bool, speech: str) -> Dict[str, Any]:
        if not temporary:
            return {"ok": True, "path": path, "temporary": False, "speech": speech}
        try:
            data = Path(path).read_bytes()
        finally:
            cls._cleanup_temp(path, True)
        return {"ok": True, "bytes": data, "temporary": False, "speech": speech}

    # ------------------------------------------------------------ síntese

    def synthesize(self, text: str, output_path: Optional[str] = None,
                   voice: Optional[str] = None,
                   emotion: Optional[float] = None
                   ) -> Dict[str, Any]:
        """Gera áudio com prosódia natural. Retorna dict com path/bytes."""
        if not (text or "").strip():
            return {"ok": False, "speech": "Texto vazio."}
        t0 = time.monotonic()
        emotion = emotion if emotion is not None else self._emotion

        if self._engine == "chatterbox":
            result = self._synth_chatterbox(text, output_path, emotion)
        elif self._engine == "kokoro":
            result = self._synth_kokoro(text, output_path, voice)
        elif self._engine == "f5":
            result = self._synth_f5(text, output_path)
        else:
            result = self._synth_edge_tts(text, output_path)

        elapsed_ms = (time.monotonic() - t0) * 1000
        with self._lock:
            self._stats["generations"] += 1
            self._stats["total_ms"] += elapsed_ms
            self._stats["avg_latency_ms"] = round(
                self._stats["total_ms"] / self._stats["generations"], 1)
            self._stats["by_engine"][self._engine] = \
                self._stats["by_engine"].get(self._engine, 0) + 1
        if result.get("ok"):
            result["engine"] = self._engine
            result["latency_ms"] = round(elapsed_ms, 1)
        return result

    # ------------------------------------------------------------ Chatterbox
    def _synth_chatterbox(self, text: str, output_path: Optional[str],
                          emotion: float) -> Dict[str, Any]:
        """Chatterbox V3: melhor qualidade, controle de emoção."""
        output = ""
        temporary = False
        try:

            import torch
            from chatterbox.tts import ChatterboxTTS

            # lazy init do modelo (pesado — só na primeira chamada)
            if not hasattr(self, "_cb_model"):
                device = "cuda" if self._prefer_gpu and torch.cuda.is_available() else "cpu"
                if self._clone_path and Path(self._clone_path).is_file():
                    self._cb_model = ChatterboxTTS.from_pretrained(
                        device=device,
                        reference_audio=self._clone_path)
                else:
                    self._cb_model = ChatterboxTTS.from_pretrained(
                        device=device)
                logger.info("chatterbox: modelo carregado em %s", device)

            wav = self._cb_model.generate(
                text,
                emotion=emotion,        # 0.0=monotono, 1.0=dramatico
                exaggeration=emotion,    # controle de prosódia
                temperature=0.7,
                repetition_penalty=1.1,
            )
            output, temporary = self._new_output(output_path, ".wav")
            import soundfile as sf
            sf.write(output, wav.squeeze().cpu().numpy(),
                     self._cb_model.sr)
            return self._complete_output(output, temporary, "Audio gerado com Chatterbox.")
        except Exception as exc:
            self._cleanup_temp(output, temporary)
            logger.exception("chatterbox falhou")

            self._stats["failures"] += 1
            # fallback para edge-tts
            return self._synth_edge_tts(text, output_path)

    # ------------------------------------------------------------ Kokoro
    def _synth_kokoro(self, text: str, output_path: Optional[str],
                      voice: Optional[str]) -> Dict[str, Any]:
        """Kokoro: leve (82M), CPU ok, prosódia natural."""
        output = ""
        temporary = False
        try:

            from kokoro import KPipeline
            import soundfile as sf

            if not hasattr(self, "_kokoro_pipeline"):
                import torch
                device = ("cuda" if self._prefer_gpu and
                          torch.cuda.is_available() else "cpu")
                self._kokoro_pipeline = KPipeline(lang_code="p")  # p = pt-BR
                logger.info("kokoro: pipeline pt-BR carregado")

            voice = voice or "pf_dora"  # voz feminina pt-BR padrão
            generator = self._kokoro_pipeline(text, voice=voice)
            audio_chunks = []
            for _, _, audio in generator:
                audio_chunks.append(audio)
            import numpy as np
            full_audio = np.concatenate(audio_chunks)
            output, temporary = self._new_output(output_path, ".wav")
            sf.write(output, full_audio, 24000)
            return self._complete_output(output, temporary, "Audio gerado com Kokoro.")
        except Exception as exc:
            self._cleanup_temp(output, temporary)
            logger.exception("kokoro falhou")

            self._stats["failures"] += 1
            return self._synth_edge_tts(text, output_path)

    # ------------------------------------------------------------ F5-TTS
    def _synth_f5(self, text: str, output_path: Optional[str]) -> Dict[str, Any]:
        """F5-TTS pt-BR: sotaque brasileiro nativo."""
        output = ""
        temporary = False
        try:
            output, temporary = self._new_output(output_path, ".wav")

            # usa CLI do F5-TTS (mais estável que Python API no Windows)
            cmd = ["f5-tts_infer-cli",
                   "--GEN_TEXT", text,
                   "--OUTPUT_FILE", output]
            if self._clone_path and Path(self._clone_path).is_file():
                cmd.extend(["--REF_AUDIO", self._clone_path])
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.decode()[-200:])
            return self._complete_output(output, temporary, "Audio gerado com F5-TTS pt-BR.")
        except Exception as exc:
            self._cleanup_temp(output, temporary)
            logger.exception("f5 falhou")

            self._stats["failures"] += 1
            return self._synth_edge_tts(text, output_path)

    # ------------------------------------------------------------ edge-tts
    def _synth_edge_tts(self, text: str, output_path: Optional[str]
                        ) -> Dict[str, Any]:
        """Fallback: edge-tts (voz neural Microsoft, prosódia limitada)."""
        output = ""
        temporary = False
        try:

            import asyncio
            import edge_tts

            async def _gen():
                voice = "pt-BR-AntonioNeural"
                communicate = edge_tts.Communicate(text, voice)
                nonlocal temporary
                output_path_local, temporary = self._new_output(output_path, ".mp3")
                await communicate.save(output_path_local)
                return output_path_local

            output = asyncio.run(_gen())
            return self._complete_output(output, temporary, "Audio gerado com edge-tts (fallback).")
        except Exception as exc:
            self._cleanup_temp(output, temporary)
            logger.exception("edge-tts falhou")

            return {"ok": False, "speech": "Falha em todos os TTS: %s" % exc}

    # ------------------------------------------------------------ estado
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"natural_voice": {
                "engine": self._engine,
                "is_natural": self.is_natural,
                "emotion_level": self._emotion,
                **self._stats}}


# ---------------------------------------------------------------------------
# integração com o voice server
# ---------------------------------------------------------------------------
_engine: Optional[NaturalVoiceEngine] = None
_engine_lock = threading.Lock()


def get_natural_voice(prefer_gpu: bool = True,
                      emotion: float = 0.7,
                      clone_path: Optional[str] = None
                      ) -> NaturalVoiceEngine:
    """Singleton processual do engine de voz natural."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = NaturalVoiceEngine(prefer_gpu=prefer_gpu,
                                         emotion_level=emotion,
                                         voice_clone_path=clone_path)
        return _engine


def replace_synthesize_bytes(voice_server_module) -> None:
    """Monkey-patch: substitui _synthesize_bytes do jarvis_voice_server
    pelo engine natural. Mantém a assinatura (text -> bytes mp3/wav)."""
    natural = get_natural_voice()

    def _new_synthesize_bytes(text: str) -> bytes:
        result = natural.synthesize(text)
        if not result.get("ok"):
            raise RuntimeError(result.get("speech", "TTS falhou"))
        if isinstance(result.get("bytes"), (bytes, bytearray)):
            return bytes(result["bytes"])
        path = result.get("path")
        if not path:
            raise RuntimeError("TTS retornou áudio sem bytes nem caminho")
        return Path(path).read_bytes()

    voice_server_module._synthesize_bytes = _new_synthesize_bytes
    logger.info("natural_voice: _synthesize_bytes substituído (engine=%s)",
                natural.engine_name)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    # Engine detection (sem instalar nada, deve cair em edge-tts)
    engine = NaturalVoiceEngine(prefer_gpu=False)
    check("detect: engine identificado",
          engine.engine_name in ("chatterbox", "kokoro", "f5", "edge-tts"))
    check("detect: stats tem engine",
          "engine" in engine.stats()["natural_voice"])

    # Se tiver chatterbox instalado
    if engine.engine_name == "chatterbox":
        check("chatterbox: detectado como natural",
              engine.is_natural is True)
    elif engine.engine_name == "kokoro":
        check("kokoro: detectado como natural",
              engine.is_natural is True)
    else:
        check("fallback: edge-tts detectado",
              engine.engine_name == "edge-tts")

    # emotion setter
    engine.set_emotion(0.5)
    check("emotion: setter funciona",
          engine.stats()["natural_voice"]["emotion_level"] == 0.5)

    # singleton
    e1 = get_natural_voice()
    e2 = get_natural_voice()
    check("singleton: mesma instância", e1 is e2)

    # Síntese real é opt-in: evita rede/download durante validação offline.
    if (engine.engine_name == "edge-tts" and
            os.environ.get("AURA_NATURAL_VOICE_SELFTEST_SYNTHESIS") == "1"):
        try:
            import edge_tts  # verifica se está instalado
            result = engine.synthesize("Teste de voz natural.")
            check("edge-tts: síntese funciona", result.get("ok") is True
                  and isinstance(result.get("bytes"), (bytes, bytearray)))
            check("edge-tts: temporário limpo", not result.get("path"))

        except ImportError:
            print("[SKIP] edge-tts não instalado neste ambiente")
    elif engine.engine_name == "edge-tts":
        print("[SKIP] síntese real desativada; use AURA_NATURAL_VOICE_SELFTEST_SYNTHESIS=1")

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - natural_voice.py")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
