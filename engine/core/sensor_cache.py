"""
sensor_cache.py — Cache TTL genérico para amostragem de sensores (GPU/CPU/RAM).

PROBLEMA
    pynvml custa microssegundos, mas o fallback `nvidia-smi` é subprocesso
    (50-300 ms no Windows). O hot-path (gpu_resource_manager do V25 legado,
    hardware_governor) não pode pagar isso a cada leitura.

CORREÇÕES sobre o lote recebido (que não deve ser instalado):
    1. Sampler roda FORA de qualquer lock — a versão recebida travava o lock
       durante a amostragem (viola a convenção de nunca segurar lock em I/O).
    2. Single-flight: no máximo UMA amostragem por vez. Threads que chegam
       durante um miss recebem o último valor marcado `_stale=True` — nunca
       bloqueiam em I/O, nunca duplicam subprocesso.
    3. FAIL-CLOSED: erro do sampler NÃO vira "GPU livre" (vram_pct=0).
       Serve o último valor com `_stale=True`, contabiliza em stats() e
       loga com traceback (1ª ocorrência e a cada 10 consecutivas — sem spam).
    4. `consecutive_errors` exposto: o consumidor decide a partir de quantos
       erros "não consigo medir" vira "não autorizo background".

INTEGRAÇÃO (hardware_governor.py e/ou gpu_resource_manager.py do legado):

    self._sensor_cache = SensorCache(self._sample_gpu, ttl_sec=3.0)
    ...
    metrics = self._sensor_cache.get()
    st = self._sensor_cache.stats()["sensor_cache"]
    if metrics.get("_stale") and metrics.get("_error") and st["consecutive_errors"] >= 5:
        return False  # fail-closed: sensor cego = não autoriza background

std-lib only. Python 3.9+. Windows compatível.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

__version__ = "1.0.0"

_LOG = logging.getLogger("aura.sensor_cache")


class SensorCache:
    """Cache TTL thread-safe, single-flight, fail-closed sobre erro de sampler."""

    def __init__(
        self,
        sampler: Callable[[], Dict[str, Any]],
        ttl_sec: float = 3.0,
        stale_on_error: bool = True,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if ttl_sec <= 0:
            raise ValueError("ttl_sec deve ser > 0")
        if not callable(sampler):
            raise TypeError("sampler deve ser callable")
        self._sampler = sampler
        self._ttl = float(ttl_sec)
        self._stale_on_error = bool(stale_on_error)
        self._clock = clock or time.monotonic

        self._lock = threading.Lock()        # estado + contadores
        self._fetch_lock = threading.Lock()  # single-flight do sampler
        self._value: Optional[Dict[str, Any]] = None
        self._valid = False
        self._fetched_at = -1.0

        self._hits = 0
        self._fetches = 0
        self._pass_through = 0
        self._errors = 0
        self._consecutive_errors = 0
        self._last_error: Optional[str] = None
        self._last_sampler_ms = 0.0

    # ------------------------------------------------------------------ api
    def get(self) -> Dict[str, Any]:
        """Métricas do cache. Nunca levanta por falha do sampler.

        Campos extras no retorno:
            `_stale` (bool) — valor pode estar defasado (erro recente do
                               sampler ou amostragem em curso por outra thread).
            `_error` (str)  — presente quando não há valor confiável algum.
        """
        with self._lock:
            if self._valid and (self._clock() - self._fetched_at) < self._ttl:
                self._hits += 1
                out = dict(self._value or {})
                out["_stale"] = False
                return out
            # acquire não-bloqueante: nunca esperamos fetch_lock segurando _lock
            will_fetch = self._fetch_lock.acquire(blocking=False)

        if not will_fetch:
            # Outra thread está amostrando agora: devolve o que existe,
            # sem bloquear em I/O e sem duplicar a amostragem.
            with self._lock:
                self._pass_through += 1
                val = self._value
            if val is not None:
                out = dict(val)
                out["_stale"] = True
                return out
            return {"_stale": True, "_error": "sem amostra; amostragem em curso"}

        exc_info = None
        try:
            err: Optional[str] = None
            value: Optional[Dict[str, Any]] = None
            t0 = self._clock()
            try:
                raw = self._sampler()  # FORA do lock — pode ser subprocesso
                if isinstance(raw, dict):
                    value = raw
                else:
                    err = "sampler retornou %s, esperado dict" % type(raw).__name__
            except Exception:
                err = "%s: %s" % (sys.exc_info()[0].__name__, sys.exc_info()[1])
                exc_info = sys.exc_info()
            elapsed_ms = (self._clock() - t0) * 1000.0

            with self._lock:
                self._fetches += 1
                self._last_sampler_ms = elapsed_ms
                if value is not None:
                    self._value = dict(value)
                    self._valid = True
                    self._fetched_at = self._clock()
                    self._consecutive_errors = 0
                    self._last_error = None
                    out = dict(self._value)
                    out["_stale"] = False
                    return out

                # sampler falhou — fail-closed, nunca fail-open
                self._errors += 1
                self._consecutive_errors += 1
                self._last_error = err
                if self._consecutive_errors == 1 or self._consecutive_errors % 10 == 0:
                    _LOG.error("sensor_cache: sampler falhou (%d consecutivas): %s",
                               self._consecutive_errors, err, exc_info=exc_info)
                if not self._stale_on_error:
                    self._valid = False
                if self._value is not None and self._stale_on_error:
                    out = dict(self._value)
                    out["_stale"] = True
                    return out
                return {"_stale": True, "_error": err}
        finally:
            self._fetch_lock.release()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sensor_cache": {
                    "hits": self._hits,
                    "fetches": self._fetches,
                    "pass_through": self._pass_through,
                    "errors": self._errors,
                    "consecutive_errors": self._consecutive_errors,
                    "last_error": self._last_error,
                    "last_sampler_ms": round(self._last_sampler_ms, 3),
                    "ttl_sec": self._ttl,
                    "has_value": self._value is not None,
                }
            }


if __name__ == "__main__":
    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            sys.exit(1)

    # --- 1) hit/miss com relógio falso (determinístico, sem sleep) ---
    t = {"now": 0.0}
    calls = {"n": 0}

    def ok_sampler():
        calls["n"] += 1
        return {"vram_pct": 55.0, "vram_used_mb": 3300}

    c = SensorCache(ok_sampler, ttl_sec=3.0, clock=lambda: t["now"])
    m1 = c.get()
    check("primeira leitura faz fetch", calls["n"] == 1)
    check("valor correto e fresco", m1.get("vram_pct") == 55.0 and m1.get("_stale") is False)
    m2 = c.get()
    check("dentro do TTL é hit", calls["n"] == 1 and m2.get("_stale") is False)
    t["now"] = 3.5
    c.get()
    check("TTL vencido refaz fetch", calls["n"] == 2)
    st = c.stats()["sensor_cache"]
    check("contadores corretos", st["hits"] == 1 and st["fetches"] == 2 and st["errors"] == 0)

    # --- 2) fail-closed: sampler quebrado serve último valor como _stale ---
    mode = {"broken": False}

    def switchable_sampler():
        if mode["broken"]:
            raise RuntimeError("pynvml desapareceu")
        return {"vram_pct": 41.5, "vram_used_mb": 2490}

    c2 = SensorCache(switchable_sampler, ttl_sec=1.0, clock=lambda: t["now"])
    m_ok = c2.get()
    check("valor bom antes da pane", m_ok.get("vram_pct") == 41.5 and m_ok.get("_stale") is False)
    t["now"] += 2.0            # TTL vence
    mode["broken"] = True      # sampler quebra
    m_bad = c2.get()
    check("pane serve último valor com _stale (não vram=0)",
          m_bad.get("_stale") is True and m_bad.get("vram_pct") == 41.5)
    st2 = c2.stats()["sensor_cache"]
    check("pane contabilizada",
          st2["errors"] == 1 and st2["consecutive_errors"] == 1 and st2["last_error"] is not None)

    # --- 3) single-flight: sampler lento, 5 threads concorrentes ---
    in_flight = {"n": 0, "max": 0}
    guard = threading.Lock()

    def slow_sampler():
        with guard:
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
        time.sleep(0.25)
        with guard:
            in_flight["n"] -= 1
        return {"vram_pct": 60.0}

    c3 = SensorCache(slow_sampler, ttl_sec=60.0, clock=time.monotonic)
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        c3.get()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    st3 = c3.stats()["sensor_cache"]
    check("exatamente um fetch sob concorrência", st3["fetches"] == 1)
    check("sampler nunca rodou em paralelo", in_flight["max"] == 1)
    check("threads simultâneas registradas", st3["pass_through"] >= 1)
    print("ALL TESTS PASSED - sensor_cache.py")
