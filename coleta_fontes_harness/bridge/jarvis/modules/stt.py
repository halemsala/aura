"""Speech-to-Text local com faster-whisper, otimizado para GPU NVIDIA.

Perfil alvo: RTX 4050 6 GB (híbrida). Whisper usa CUDA float16 quando
disponível; cai para CPU int8 sem derrubar o servidor de voz.
"""
from __future__ import annotations

import contextlib
import gc
import logging
import os
from typing import Any

try:
    import numpy as np
except Exception:
    np = None  # type: ignore

logger = logging.getLogger("aura.stt")

_HALLUCINATION_MARKERS = (
    "olha o desktop", "cria pasta", "toca musica", "sobe o aura",
    "autorizo, cancela", "thanks for watching", "legendas", "inscreva-se",
)


def _reject_hallucination(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    low = t.casefold()
    hits = sum(1 for m in _HALLUCINATION_MARKERS if m in low)
    if hits >= 3:
        return ""
    if "thanks for watching" in low or "inscreva-se no canal" in low:
        return ""
    words = [w for w in low.replace(",", " ").split() if w]
    if len(words) <= 2 and words and words[0] in {"obrigado", "thanks", "music", "you"}:
        return ""
    return t

try:
    import torch
except Exception:
    torch = None  # type: ignore

try:
    from faster_whisper import WhisperModel
except Exception:
    import sys as _sys
    from pathlib import Path as _P
    cands = [
        _P(_sys.executable).resolve().parent / "Lib" / "site-packages",
        _P(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "Lib" / "site-packages",
    ]
    for _sp in cands:
        if _sp.is_dir() and str(_sp) not in _sys.path:
            _sys.path.append(str(_sp))
    from faster_whisper import WhisperModel


class STT:
    def __init__(
        self,
        model_name: str,
        device: str,
        language: str,
        compute_type_gpu: str = "float16",
        compute_type_cpu: str = "int8",
    ):
        self.language = language or "pt"
        self.device = "cuda" if str(device).startswith("cuda") else "cpu"
        # GPU: float16 é o sweet spot qualidade/VRAM na 4050.
        # CPU: int8 para não matar latência em notebook.
        if self.device == "cuda":
            compute_type = compute_type_gpu or "float16"
            # Índice CUDA controlado por CUDA_VISIBLE_DEVICES / AURA_CUDA_DEVICE
            device_index = int(os.environ.get("AURA_CUDA_DEVICE", "0"))
        else:
            compute_type = compute_type_cpu or "int8"
            device_index = 0

        # Menos workers competindo com Ollama na mesma GPU
        cpu_threads = max(2, min(4, (os.cpu_count() or 4) // 2))
        num_workers = 1

        print(
            f"[stt] Carregando Whisper '{model_name}' em {self.device} "
            f"(compute={compute_type}, workers={num_workers})..."
        )
        kwargs: dict[str, Any] = dict(
            device=self.device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=num_workers,
        )
        if self.device == "cuda":
            kwargs["device_index"] = device_index

        self.model = WhisperModel(model_name, **kwargs)
        self.model_name = model_name
        self.compute_type = compute_type

    def _has_speech(self, audio_array, threshold: float = 0.02) -> bool:
        """VAD RMS simples; em caso de erro, mantém o caminho de transcrição."""
        if np is None:
            return True
        try:
            audio_np = np.asarray(audio_array, dtype=np.float32)
            if audio_np.size == 0:
                return False
            rms = float(np.sqrt(np.mean(np.square(audio_np))))
            return rms > float(threshold)
        except Exception as exc:
            logger.debug("VAD indisponível; processando áudio: %s", exc)
            return True

    def transcribe_mic(self, audio_chunk, threshold: float = 0.02) -> str:
        if not self._has_speech(audio_chunk, threshold):
            return ""
        return self.transcribe(audio_chunk)

    def transcribe(self, audio, loose: bool = False) -> str:
        if getattr(audio, "size", 0) == 0 and not isinstance(audio, str):
            return ""
        try:
            context = torch.no_grad() if torch is not None else contextlib.nullcontext()
            with context:
                segments, info = self.model.transcribe(
                    audio,
                    language=self.language,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    vad_filter=True,
                    vad_parameters={
                        "min_silence_duration_ms": 400,
                        "speech_pad_ms": 300,
                        "threshold": 0.45,
                    },
                    condition_on_previous_text=False,
                    without_timestamps=True,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    no_speech_threshold=0.6,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                return _reject_hallucination(text)
        finally:
            # CTranslate2/Torch mantém arenas de memória; coleta explícita reduz
            # retenção entre frases sem descarregar o modelo persistente.
            if torch is not None:
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.ipc_collect()
                except Exception:
                    pass
            gc.collect()

    def stats(self) -> dict:
        return {
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "local": True,
            "provider": "faster-whisper",
        }

# --- V23 BLOCO 6: loader explicito CPU/int8 para comandos curtos ---
_stt_singleton = None

def load_stt_model(model_name: str = "base", device: str = "cpu"):
    global _stt_singleton
    if _stt_singleton is None:
        _stt_singleton = STT(model_name=model_name, device=device, language="pt", compute_type_cpu="int8")
    return _stt_singleton

def transcribe_audio(audio_path: str) -> str:
    model = load_stt_model()
    return model.transcribe(audio_path)
