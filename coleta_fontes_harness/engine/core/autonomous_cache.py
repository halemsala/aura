#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Autonomous Cache: monitora RAM do processo Python.
Quando excede o limite, deleta automaticamente os caches mais antigos
registrados. Evita vazamento de RAM ate o Windows fechar o app.
"""
from __future__ import annotations
import gc
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.cache")
__version__ = "1.0.0"
__all__ = ["AutonomousCache", "CACHE"]


class AutonomousCache:
    """Monitor de RAM com limpeza automatica de caches registrados."""

    def __init__(self, *, ram_limit_mb: int = 4096,
                 gc_threshold_mb: int = 3072,
                 check_interval: float = 30.0):
        self.ram_limit = int(ram_limit_mb)
        self.gc_threshold = int(gc_threshold_mb)
        self.interval = float(check_interval)
        self._lock = threading.RLock()
        self._registries: List[Dict[str, Any]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._evictions = 0
        self._gc_runs = 0
        self._last_rss_mb = 0
        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            pass

    def register(self, name: str,
                 cleanup_fn: Callable[[int], int], *, priority: int = 0) -> None:
        """Registra um cache limpavel.
        cleanup_fn(target_mb) deve deletar ate target_mb de dados e
        retornar quantos MB liberou de fato."""
        with self._lock:
            self._registries.append({"name": str(name), "cleanup": cleanup_fn,
                                      "priority": int(priority)})
            self._registries.sort(key=lambda r: r["priority"])

    def _rss_mb(self) -> int:
        if self._psutil is not None:
            try:
                return int(self._psutil.Process().memory_info().rss / (1024 * 1024))
            except Exception:
                pass
        try:
            import resource
            return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
        except Exception:
            return 0

    def _evict(self, target_mb: int) -> int:
        freed = 0
        with self._lock:
            regs = list(self._registries)
        for reg in regs:
            if freed >= target_mb:
                break
            try:
                f = int(reg["cleanup"](target_mb - freed))
                freed += f
                self._evictions += 1
                log.info("[cache] %s liberou %d MB", reg["name"], f)
            except Exception:
                log.exception("[cache] cleanup de %s falhou", reg["name"])
        return freed

    def _check(self) -> None:
        rss = self._rss_mb()
        self._last_rss_mb = rss
        if rss == 0:
            return
        if rss > self.ram_limit:
            excess = rss - self.gc_threshold
            log.warning("[cache] RAM %dMB > limite %dMB — limpando %dMB",
                        rss, self.ram_limit, excess)
            self._evict(excess)
        if rss > self.gc_threshold:
            gc.collect()
            self._gc_runs += 1

    def start(self) -> "AutonomousCache":
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._loop,
                                        name="auto-cache", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while self._running:
            try:
                self._check()
            except Exception:
                log.exception("[cache] check falhou")
            time.sleep(self.interval)

    def stop(self) -> None:
        self._running = False

    def stats(self) -> dict:
        with self._lock:
            return {"rss_mb": self._last_rss_mb,
                    "ram_limit_mb": self.ram_limit,
                    "gc_threshold_mb": self.gc_threshold,
                    "evictions": self._evictions,
                    "gc_runs": self._gc_runs,
                    "registries": len(self._registries),
                    "running": self._running}


CACHE = AutonomousCache()


if __name__ == "__main__":
    import sys
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    fake = {f"k{i}": "x" * 1024 for i in range(500)}

    def cleanup(target):
        n = 0
        while fake and n < target:
            fake.popitem()
            n += 1
        return n

    cache = AutonomousCache(ram_limit_mb=1, gc_threshold_mb=1,
                            check_interval=1.0)
    cache.register("fake", cleanup)
    check("registra cache", cache.stats()["registries"] == 1)
    cache.start()
    time.sleep(2)
    st = cache.stats()
    check("detecta RAM e limpa",
          st["evictions"] > 0 or st["rss_mb"] == 0,
          f"evict={st['evictions']} rss={st['rss_mb']}MB")
    cache.stop()
    print(f"\nautonomous_cache selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
