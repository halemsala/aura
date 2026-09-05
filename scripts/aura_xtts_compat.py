"""Compatibilidade XTTS no Windows sem FFmpeg/torchcodec e com transformers 5.x.

Problemas reais do host do utilizador (2026-08-30):
1) coqui-tts importa isin_mps_friendly de transformers.pytorch_utils.
   transformers>=5.1 removeu o simbolo.
2) torchaudio>=2.9 encaminha load/save para torchcodec. No Windows isso
   exige FFmpeg full-shared + DLL libtorchcodec_coreN.dll. PyTorch 2.13+cpu
   do utilizador falhou a carregar todas as variantes 4-9.

Esta camada:
- injeta isin_mps_friendly se faltar
- substitui torchaudio.load / save e torchaudio._torchcodec.* por soundfile
Deve ser aplicada ANTES de `from TTS.api import TTS`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def apply_torchcodec_stub() -> str:
    """Coqui 0.27.5 faz `raise ImportError` se torch>=2.9 e torchcodec ausente."""
    try:
        import transformers.utils.import_utils as iu  # type: ignore

        iu.is_torchcodec_available = lambda: True  # type: ignore[assignment]
    except Exception:
        pass
    stub_root = Path(__file__).resolve().parent / "_torchcodec_stub"
    if stub_root.is_dir() and str(stub_root) not in sys.path:
        sys.path.insert(0, str(stub_root))
    if "torchcodec" in sys.modules:
        return "torchcodec_already_imported"
    try:
        import torchcodec  # noqa: F401

        return f"torchcodec_stub:{getattr(torchcodec, '__version__', 'ok')}"
    except Exception as exc:
        return f"torchcodec_stub_fail:{type(exc).__name__}"


def apply_transformers_shim() -> str:
    try:
        import transformers.pytorch_utils as pu  # type: ignore
    except Exception as exc:
        return f"transformers_unavailable:{type(exc).__name__}"
    if hasattr(pu, "isin_mps_friendly"):
        return "transformers_ok"
    def isin_mps_friendly(*_args: Any, **_kwargs: Any) -> bool:
        return False
    pu.isin_mps_friendly = isin_mps_friendly  # type: ignore[attr-defined]
    return "transformers_shim_isin_mps_friendly"


def _soundfile_load(
    uri: Any,
    frame_offset: int = 0,
    num_frames: int = -1,
    normalize: bool = True,
    channels_first: bool = True,
    format: Any = None,
    buffer_size: int = 4096,
    backend: Any = None,
):
    import numpy as np
    import soundfile as sf
    import torch

    handle = uri if hasattr(uri, "read") else str(uri)
    data, sr = sf.read(handle, always_2d=True)
    data = np.asarray(data, dtype=np.float32)
    if frame_offset:
        data = data[int(frame_offset) :]
    if num_frames is not None and int(num_frames) >= 0:
        data = data[: int(num_frames)]
    tensor = torch.from_numpy(np.ascontiguousarray(data))
    if channels_first:
        tensor = tensor.transpose(0, 1).contiguous()
    if normalize:
        tensor = torch.clamp(tensor, -1.0, 1.0)
    return tensor, int(sr)


def _soundfile_save(
    uri: Any,
    src: Any,
    sample_rate: int,
    channels_first: bool = True,
    format: Any = None,
    encoding: Any = None,
    bits_per_sample: Any = None,
    buffer_size: int = 4096,
    backend: Any = None,
    compression: Any = None,
):
    import numpy as np
    import soundfile as sf

    arr = src.detach().cpu().numpy() if hasattr(src, "detach") else np.asarray(src)
    arr = np.asarray(arr, dtype=np.float32)
    if channels_first and arr.ndim == 2:
        arr = arr.T
    path = uri if hasattr(uri, "write") else str(uri)
    sf.write(path, arr, int(sample_rate))


def apply_torchaudio_soundfile_fallback() -> str:
    try:
        import soundfile as sf  # noqa: F401
    except Exception as exc:
        return f"soundfile_missing:{type(exc).__name__}"
    patched = []
    try:
        import torchaudio

        torchaudio.load = _soundfile_load  # type: ignore[assignment]
        if hasattr(torchaudio, "save"):
            torchaudio.save = _soundfile_save  # type: ignore[assignment]
        patched.append("torchaudio.load/save")
    except Exception as exc:
        return f"torchaudio_unavailable:{type(exc).__name__}"
    try:
        import torchaudio._torchcodec as tc  # type: ignore

        tc.load_with_torchcodec = _soundfile_load  # type: ignore[assignment]
        if hasattr(tc, "save_with_torchcodec"):
            tc.save_with_torchcodec = _soundfile_save  # type: ignore[assignment]
        patched.append("torchaudio._torchcodec")
    except Exception:
        pass
    return "audio_ok:" + ",".join(patched) if patched else "audio_patch_skipped"


def apply_all() -> dict:
    return {
        "torchcodec": apply_torchcodec_stub(),
        "transformers": apply_transformers_shim(),
        "audio": apply_torchaudio_soundfile_fallback(),
    }


if __name__ == "__main__":
    info = apply_all()
    print("XTTS_COMPAT", info)
