"""Teste XTTS com WAV de referencia — sem torchcodec/FFmpeg."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from aura_xtts_compat import apply_all  # noqa: E402

WAV = ROOT / "bridge" / "jarvis" / "voices" / "voz_masculina_referencia.wav"
OUT = ROOT / "logs_supervisor" / "teste_xtts.wav"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    if not WAV.is_file():
        print(f"ERRO: WAV ausente: {WAV}")
        return 2
    print("COMPAT", apply_all())
    try:
        import torch
        from TTS.api import TTS
    except Exception as e:
        print(f"ERRO import TTS: {e}")
        print("ACAO: python scripts\\instalar_deps_voz.py")
        return 3

    try:
        import soundfile as sf
        import numpy as np

        data, sr = sf.read(str(WAV), always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        target_sr = 22050
        if sr != target_sr:
            import librosa

            data = librosa.resample(np.asarray(data, dtype=np.float32), orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        tmp = OUT.parent / "_ref_22k_mono.wav"
        sf.write(str(tmp), data, sr)
        speaker = str(tmp)
        print(f"REF_PREP={tmp} sr={sr}")
    except Exception as e:
        print(f"AVISO soundfile prep falhou, usando WAV original: {e}")
        speaker = str(WAV)

    use_gpu = bool(torch.cuda.is_available())
    print(f"CUDA={use_gpu}")
    print("A carregar XTTS-v2 (1.a vez demora)...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)
    tts.tts_to_file(
        text="Pressao de escanteios subiu no segundo tempo. Linha ainda com valor. Gestao de banca primeiro.",
        file_path=str(OUT),
        speaker_wav=speaker,
        language="pt",
    )
    size = OUT.stat().st_size if OUT.is_file() else 0
    print(f"OK size={size} path={OUT}")
    return 0 if size > 1000 else 4


if __name__ == "__main__":
    sys.exit(main())
