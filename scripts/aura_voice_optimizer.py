#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Voice Optimizer v1.0
Cache de TTS, batching de STT e otimização de pipeline de voz.
"""
import os, sys, json, hashlib, time
from pathlib import Path
from typing import Optional

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
VOICE_CACHE = AURA_ROOT / "voice_assets" / "cache"
VOICE_CACHE.mkdir(parents=True, exist_ok=True)
CACHE_INDEX = VOICE_CACHE / "index.json"


class TTSCache:
    """Cache de arquivos TTS com deduplicação por hash de texto."""

    def __init__(self, max_entries: int = 1000, max_age_hours: int = 24):
        self.max_entries = max_entries
        self.max_age = max_age_hours * 3600
        self._index = self._load_index()

    def _load_index(self) -> dict:
        if CACHE_INDEX.exists():
            try:
                return json.loads(CACHE_INDEX.read_text(encoding="utf-8"))
            except:
                pass
        return {}

    def _save_index(self):
        CACHE_INDEX.write_text(json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8")

    def _text_hash(self, text: str, voice: str = "default") -> str:
        return hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]

    def get(self, text: str, voice: str = "default") -> Optional[Path]:
        key = self._text_hash(text, voice)
        if key in self._index:
            entry = self._index[key]
            if time.time() - entry["created"] < self.max_age:
                path = VOICE_CACHE / entry["filename"]
                if path.exists():
                    return path
            del self._index[key]
            self._save_index()
        return None

    def put(self, text: str, audio_path: Path, voice: str = "default"):
        key = self._text_hash(text, voice)
        filename = f"{key}_{int(time.time())}.wav"
        target = VOICE_CACHE / filename

        import shutil
        shutil.copy2(audio_path, target)

        self._index[key] = {
            "text_preview": text[:100],
            "voice": voice,
            "filename": filename,
            "created": time.time(),
            "size": target.stat().st_size
        }

        # Limpar entradas antigas
        self._cleanup()
        self._save_index()

    def _cleanup(self):
        now = time.time()
        old = [k for k, v in self._index.items() if now - v["created"] > self.max_age]
        for k in old:
            path = VOICE_CACHE / self._index[k]["filename"]
            path.unlink(missing_ok=True)
            del self._index[k]

        # Limitar quantidade
        if len(self._index) > self.max_entries:
            sorted_entries = sorted(self._index.items(), key=lambda x: x[1]["created"])
            for k, _ in sorted_entries[:len(sorted_entries) - self.max_entries]:
                path = VOICE_CACHE / self._index[k]["filename"]
                path.unlink(missing_ok=True)
                del self._index[k]

    def stats(self) -> dict:
        total_size = sum(VOICE_CACHE.glob("*.wav"), key=lambda p: p.stat().st_size, default=0)
        return {
            "cached_entries": len(self._index),
            "cache_dir": str(VOICE_CACHE),
            "max_entries": self.max_entries,
            "max_age_hours": self.max_age // 3600,
        }


class STTBatchProcessor:
    """Processamento em batch de STT para reduzir overhead."""

    def __init__(self, batch_size: int = 5, max_wait_ms: int = 1000):
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self._buffer = []

    def add(self, audio_chunk: bytes, metadata: dict = None):
        self._buffer.append({"audio": audio_chunk, "meta": metadata or {}, "time": time.time()})
        if len(self._buffer) >= self.batch_size:
            return self.flush()
        return None

    def flush(self) -> list:
        batch = self._buffer[:]
        self._buffer = []
        return batch

    def process_batch(self, batch: list) -> list:
        """Processa um batch de áudio. Substituir pelo modelo STT real."""
        results = []
        for item in batch:
            # Simulação — substituir por chamada ao modelo
            results.append({
                "text": f"[STT_RESULT_{len(results)}]",
                "confidence": 0.95,
                "meta": item["meta"]
            })
        return results


def main():
    print("=" * 60)
    print("AURA Voice Optimizer v1.0")
    print("=" * 60)

    cache = TTSCache()
    print("TTS Cache stats:", cache.stats())

    # Teste de cache
    test_text = "Bem-vindo ao AURA Operator OS"
    cached = cache.get(test_text)
    if cached:
        print(f"[CACHE HIT] {test_text[:50]}...")
    else:
        print(f"[CACHE MISS] {test_text[:50]}...")

    print("=" * 60)


if __name__ == "__main__":
    main()
