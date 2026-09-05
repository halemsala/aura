"""
tts_cache.py — Cache LRU de disco para síntese de voz (camada do neural_tts).

Fila do §7: "cache de disco no neural_tts". Frases recorrentes ("Entrada na
janela W1 registrada", "Aguardo confirmação do conformal") são sintetizadas
uma única vez; as demais saem do disco em ~0 ms.

CORREÇÕES sobre o lote recebido:
    1. SHA-256 em vez de MD5 (consistência com os digests do sistema).
    2. Cache LIMITADO com LRU — a versão recebida crescia para sempre,
       o oposto da filosofia do autonomous_cache.
    3. Erro de síntese: log com traceback + contabilização em stats() +
       re-raise (nunca silencioso; o chamador decide o fallback de voz).
    4. Escrita atômica tmp + os.replace (a recebida acertava nisso).
    5. Síntese e replace executam FORA do lock; lock só para contadores/LRU.

INTEGRAÇÃO (neural_tts.py — mescla, não substituição):

    self._cache = TTSDiskCache(cache_dir=os.path.join(data_dir, "tts_cache"))
    # onde hoje chama o sintetizador direto:
    path = self._cache.get_or_synthesize(text, self._synth_to_file)
    # _synth_to_file(text, tmp_path) escreve o áudio em tmp_path

std-lib only. Python 3.9+. Windows compatível.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

__version__ = "1.0.0"

_LOG = logging.getLogger("aura.tts_cache")


def _remove_tmp(path: str) -> None:
    """Remove tmp; falha é debug-level (o erro relevante já foi logado)."""
    try:
        os.remove(path)
    except OSError:
        _LOG.debug("tts_cache: tmp inexistente ao limpar: %s", path)


class TTSDiskCache:
    """Cache LRU de arquivos de áudio por hash SHA-256 do texto."""

    def __init__(self, cache_dir: str, max_entries: int = 2000, ext: str = "wav") -> None:
        if max_entries <= 0:
            raise ValueError("max_entries deve ser > 0")
        self._dir = os.path.abspath(cache_dir)
        self._max_entries = int(max_entries)
        self._ext = ext

        self._lock = threading.Lock()
        self._lru: Dict[str, float] = {}  # path -> último uso (monotonic)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._synth_errors = 0
        self._last_synth_ms = 0.0

        os.makedirs(self._dir, exist_ok=True)
        self._index_existing()

    def _index_existing(self) -> None:
        """Reindexa arquivos de boot anterior (cache frio pós-restart).
        Nota: usa mtime (época ~1e9) como score inicial — sempre 'mais antigo'
        que qualquer monotonic() de runtime, então sobreviventes de restart
        são os primeiros evictados."""
        try:
            names = os.listdir(self._dir)
        except OSError as exc:
            _LOG.warning("tts_cache: não consegui listar %s: %s", self._dir, exc)
            return
        for name in names:
            if not name.endswith("." + self._ext):
                continue
            path = os.path.join(self._dir, name)
            try:
                self._lru[path] = float(os.path.getmtime(path))
            except OSError:
                continue

    # ------------------------------------------------------------------ api
    def get_or_synthesize(self, text: str,
                          synth_fn: Callable[[str, str], None],
                          ext: Optional[str] = None) -> str:
        """Retorna o path do áudio. Miss invoca synth_fn(text, tmp_path);
        hit devolve o path existente. Erro de síntese loga, contabiliza e
        re-levanta (nunca silencioso)."""
        ext = ext or self._ext
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        final_path = os.path.join(self._dir, digest + "." + ext)

        with self._lock:
            if os.path.exists(final_path):
                self._hits += 1
                self._lru[final_path] = time.monotonic()
                return final_path

        tmp_path = "%s.%d.%d.tmp" % (final_path, os.getpid(), threading.get_ident())
        t0 = time.monotonic()
        try:
            synth_fn(text, tmp_path)  # FORA do lock — GPU/rede demoram aqui
        except Exception:
            with self._lock:
                self._synth_errors += 1
            _LOG.exception("tts_cache: síntese falhou (digest=%s)", digest[:12])
            _remove_tmp(tmp_path)
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        if not os.path.exists(tmp_path):
            with self._lock:
                self._synth_errors += 1
            _LOG.error("tts_cache: synth_fn não criou arquivo em %s", tmp_path)
            raise RuntimeError("synth_fn não produziu arquivo em tmp_path")

        os.replace(tmp_path, final_path)  # atômico, mesmo volume

        with self._lock:
            self._misses += 1
            self._last_synth_ms = elapsed_ms
            self._lru[final_path] = time.monotonic()
            self._evict_locked()
        return final_path

    def _evict_locked(self) -> None:
        """LRU com lote (máx 64 remoções por chamada). Chamada com lock."""
        batch = 0
        while len(self._lru) > self._max_entries and batch < 64:
            victim = min(self._lru, key=self._lru.get)
            self._lru.pop(victim, None)
            try:
                os.remove(victim)
                self._evictions += 1
            except OSError as exc:
                _LOG.warning("tts_cache: falha ao evictar %s: %s", victim, exc)
            batch += 1

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tts_cache": {
                    "hits": self._hits,
                    "misses": self._misses,
                    "evictions": self._evictions,
                    "synth_errors": self._synth_errors,
                    "last_synth_ms": round(self._last_synth_ms, 3),
                    "entries": len(self._lru),
                    "max_entries": self._max_entries,
                    "cache_dir": self._dir,
                }
            }


if __name__ == "__main__":
    import shutil
    import tempfile

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            sys.exit(1)

    tmp = tempfile.mkdtemp(prefix="aura_tts_selftest_")
    try:
        def synth(txt: str, path: str) -> None:
            with open(path, "wb") as fh:
                fh.write(("audio::" + txt).encode("utf-8"))

        cache = TTSDiskCache(cache_dir=tmp, max_entries=2)

        p1 = cache.get_or_synthesize("Entrada na janela W1 registrada", synth)
        p2 = cache.get_or_synthesize("Entrada na janela W1 registrada", synth)
        check("hit devolve mesmo path", p1 == p2)
        check("arquivo em disco", os.path.exists(p1))

        st = cache.stats()["tts_cache"]
        check("contadores miss/hit", st["hits"] == 1 and st["misses"] == 1)

        # LRU: cap=2, terceira entrada evicta a mais antiga
        cache.get_or_synthesize("Pressão alta no ataque", synth)
        cache.get_or_synthesize("Aguardo confirmação do conformal", synth)
        st = cache.stats()["tts_cache"]
        check("limite LRU respeitado", st["entries"] <= 2)
        check("evict contabilizado", st["evictions"] >= 1)
        check("entrada mais antiga evictada", not os.path.exists(p1))

        # erro de síntese: contabiliza, limpa tmp e propaga
        def synth_broken(txt: str, path: str) -> None:
            raise RuntimeError("motor de voz fora do ar")

        raised = False
        try:
            cache.get_or_synthesize("isto vai falhar", synth_broken)
        except RuntimeError:
            raised = True
        check("erro de síntese propaga (não silencioso)", raised)
        check("erro de síntese contabilizado",
              cache.stats()["tts_cache"]["synth_errors"] == 1)

        # cache frio: nova instância reindexa arquivos e acerta
        cache2 = TTSDiskCache(cache_dir=tmp, max_entries=10)
        cache2.get_or_synthesize("Aguardo confirmação do conformal", synth)
        st2 = cache2.stats()["tts_cache"]
        check("reindexação pós-restart acerta", st2["hits"] == 1 and st2["misses"] == 0)

        leftovers = [n for n in os.listdir(tmp) if n.endswith(".tmp")]
        check("nenhum tmp órfão", leftovers == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ALL TESTS PASSED - tts_cache.py")
