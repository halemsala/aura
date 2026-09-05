#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Cache Integration: registra os caches dos módulos
no AutonomousCache para limpeza automática quando a RAM ultrapassa o limite.

Quando RAM > limite (default 4GB):
  1. Limpa fixtures antigas do BrowserAgent (mantém 5 recentes)
  2. Trim histórico de tips do CrossSiteAnalyst (mantém 500)
  3. Limpa predições pendentes velhas do ConformalGate (mantém 500)
  4. Limpa lista de ordem do MCGrid builder (se build completo)
  5. Force-flush da fila do FeedBus
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

log = logging.getLogger("aura.cache_integration")

__version__ = "1.0.0"
__all__ = [
    "start_cache_management", "stop_cache_management", "cache_stats", "CACHE",
    "cleanup_browser_states", "cleanup_analyst_tips",
    "cleanup_conformal_pending", "cleanup_mcgrid_order", "cleanup_feedbus",
]

try:
    from engine.core.autonomous_cache import AutonomousCache
    CACHE: Optional[Any] = AutonomousCache(
        ram_limit_mb=4096, gc_threshold_mb=3072, check_interval=30.0)
except Exception:
    CACHE = None
    log.warning("[cache_integration] autonomous_cache nao encontrado")


def cleanup_browser_states(target_mb: int, browser=None) -> int:
    if browser is None:
        return 0
    freed_mb = 0.0
    try:
        lock = getattr(browser, "_nav_lock", None) or getattr(browser, "_lock", None)
        states = getattr(browser, "_states", {})
        if not states:
            return 0
        def _do():
            nonlocal freed_mb
            items = list(states.items())
            if len(items) <= 5:
                return
            items.sort(key=lambda x: getattr(x[1], "last_update", 0), reverse=True)
            to_remove = items[5:]
            for fid, _state in to_remove:
                states.pop(fid, None)
                freed_mb += 0.02
            if to_remove:
                log.info("[cache] browser: %d fixtures antigas limpas (~%.1fMB)",
                         len(to_remove), freed_mb)
        if lock is not None:
            with lock:
                _do()
        else:
            _do()
    except Exception as e:
        log.error("[cache] browser cleanup falhou: %s", e)
    return max(1, int(round(freed_mb))) if freed_mb > 0 else 0


def cleanup_analyst_tips(target_mb: int, analyst=None) -> int:
    if analyst is None:
        return 0
    freed_mb = 0.0
    n = 0
    n_old = 0
    try:
        lock = getattr(analyst, "_lock", None)
        if lock is None:
            return 0
        with lock:
            tips = getattr(analyst, "_all_tips", [])
            n = len(tips)
            if n > 500:
                analyst._all_tips = tips[-500:]
                freed_mb += (n - 500) * 0.001
            sent = getattr(analyst, "_sent", {})
            now = time.time()
            old_keys = [k for k, t in sent.items() if now - t > 3600]
            for k in old_keys:
                sent.pop(k, None)
            n_old = len(old_keys)
            freed_mb += n_old * 0.0001
        if freed_mb > 0:
            log.info("[cache] analyst: trim %d tips, %d dedup antigos (~%.1fMB)",
                     max(0, n - 500), n_old, freed_mb)
    except Exception as e:
        log.error("[cache] analyst cleanup falhou: %s", e)
    return max(1, int(round(freed_mb))) if freed_mb > 0 else 0


def cleanup_conformal_pending(target_mb: int, conformal=None) -> int:
    if conformal is None:
        return 0
    freed_mb = 0.0
    to_remove = 0
    try:
        lock = getattr(conformal, "_lock", None)
        pending = getattr(conformal, "_pending", None)
        if pending is None:
            return 0
        def _do():
            nonlocal freed_mb, to_remove
            n = len(pending)
            if n <= 500:
                return
            items = list(pending.items())
            to_remove = len(items) // 2
            for i in range(to_remove):
                k, _ = items[i]
                pending.pop(k, None)
            freed_mb += to_remove * 0.0002
        if lock is not None:
            with lock:
                _do()
        else:
            _do()
        if freed_mb > 0:
            log.info("[cache] conformal: %d pendentes velhas limpas (~%.1fMB)",
                     to_remove, freed_mb)
    except Exception as e:
        log.error("[cache] conformal cleanup falhou: %s", e)
    return max(1, int(round(freed_mb))) if freed_mb > 0 else 0


def cleanup_mcgrid_order(target_mb: int, mc=None) -> int:
    if mc is None:
        return 0
    freed_mb = 0.0
    try:
        builder = getattr(mc, "builder", None)
        if builder is None:
            return 0
        status = builder.status() if hasattr(builder, "status") else {}
        if status.get("building", False):
            return 0
        order = getattr(builder, "_order", None)
        if order is None:
            return 0
        n = len(order)
        if n > 0:
            builder._order = []
            freed_mb += n * 0.00003
            log.info("[cache] mcgrid: %d itens de ordem limpos (~%.1fMB)", n, freed_mb)
    except Exception as e:
        log.error("[cache] mcgrid cleanup falhou: %s", e)
    return max(1, int(round(freed_mb))) if freed_mb > 0 else 0


def cleanup_feedbus(target_mb: int, bus=None) -> int:
    if bus is None:
        return 0
    freed_mb = 0.0
    try:
        depth = 0
        q = getattr(bus, "_q", None)
        if q is not None:
            depth = q.qsize()
        if depth == 0:
            return 0
        flush = getattr(bus, "flush_sync", None)
        if flush:
            flush(timeout=2.0)
            freed_mb = depth * 0.002
            log.info("[cache] feedbus: %d itens flusheados (~%.1fMB)", depth, freed_mb)
    except Exception as e:
        log.error("[cache] feedbus cleanup falhou: %s", e)
    return max(1, int(round(freed_mb))) if freed_mb > 0 else 0


_started = False


def start_cache_management(*, bus=None, conformal=None, mc=None,
                           browser=None, analyst=None,
                           ram_limit_mb: int = 4096,
                           gc_threshold_mb: int = 3072,
                           check_interval: float = 30.0) -> bool:
    global _started, CACHE
    if _started:
        log.info("[cache_integration] ja iniciado — pulando")
        return True
    try:
        from engine.core.autonomous_cache import AutonomousCache as _AC
        CACHE = _AC(ram_limit_mb=ram_limit_mb,
                    gc_threshold_mb=gc_threshold_mb,
                    check_interval=check_interval)
    except Exception:
        log.error("[cache_integration] autonomous_cache.py nao encontrado")
        return False

    if browser is not None:
        CACHE.register("browser_states",
                       lambda mb, b=browser: cleanup_browser_states(mb, b),
                       priority=0)
        log.info("[cache_integration] browser_states registrado (priority=0)")
    if analyst is not None:
        CACHE.register("analyst_tips",
                       lambda mb, a=analyst: cleanup_analyst_tips(mb, a),
                       priority=1)
        log.info("[cache_integration] analyst_tips registrado (priority=1)")
    if conformal is not None:
        CACHE.register("conformal_pending",
                       lambda mb, c=conformal: cleanup_conformal_pending(mb, c),
                       priority=2)
        log.info("[cache_integration] conformal_pending registrado (priority=2)")
    if mc is not None:
        CACHE.register("mcgrid_order",
                       lambda mb, m=mc: cleanup_mcgrid_order(mb, m),
                       priority=3)
        log.info("[cache_integration] mcgrid_order registrado (priority=3)")
    if bus is not None:
        CACHE.register("feedbus_flush",
                       lambda mb, b=bus: cleanup_feedbus(mb, b),
                       priority=4)
        log.info("[cache_integration] feedbus_flush registrado (priority=4)")

    CACHE.start()
    _started = True
    log.info(
        "[cache_integration] CACHE iniciado (RAM limite=%dMB, GC=%dMB, "
        "interval=%.0fs, %d limpezas registradas)",
        ram_limit_mb, gc_threshold_mb, check_interval, len(CACHE._registries))
    return True


def stop_cache_management() -> None:
    global _started
    if CACHE:
        CACHE.stop()
    _started = False
    log.info("[cache_integration] parado")


def cache_stats() -> dict:
    if not CACHE:
        return {"active": False}
    return CACHE.stats()


if __name__ == "__main__":
    import sys
    import threading

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    errs = []

    def check(n, c, x=""):
        s = "PASS" if c else "FAIL"
        print(f"[{s}] {n}" + (f" — {x}" if x else ""))
        if not c:
            errs.append(n)

    class FakeBrowser:
        def __init__(self):
            self._nav_lock = threading.Lock()
            self._states = {}

        class _State:
            def __init__(self, fid, ts):
                self.fixture_id = fid
                self.last_update = ts
                self.stats = {"corners": [5, 4]}
                self.events = [{"minute": i} for i in range(20)]
                self.odds = [{"price": 1.85}] * 5
                self.advanced = {"CPI_v2": {"home": {"cpi": 0.7}}}

    fb = FakeBrowser()
    for i in range(20):
        fb._states[f"fix_{i}"] = FakeBrowser._State(f"fix_{i}", time.time() - i * 100)
    check("browser: 20 states antes", len(fb._states) == 20)
    freed = cleanup_browser_states(10, browser=fb)
    check("browser: limpou estados antigos", len(fb._states) == 5)
    check("browser: manteve 5 recentes", len(fb._states) == 5)
    check("browser: freed > 0", freed > 0, f"{freed}MB")

    fb2 = FakeBrowser()
    check("browser: 0 states = 0 freed", cleanup_browser_states(10, browser=fb2) == 0)
    check("browser: None = 0", cleanup_browser_states(10, browser=None) == 0)

    class FakeAnalyst:
        def __init__(self):
            self._lock = threading.Lock()
            self._all_tips = [f"tip_{i}" for i in range(5000)]
            self._sent = {f"fp_{i}": time.time() - 7200 for i in range(200)}

    fa = FakeAnalyst()
    check("analyst: 5000 tips antes", len(fa._all_tips) == 5000)
    check("analyst: 200 sent antes", len(fa._sent) == 200)
    freed = cleanup_analyst_tips(10, analyst=fa)
    check("analyst: trim para 500", len(fa._all_tips) == 500)
    check("analyst: sent antigos limpos", len(fa._sent) == 0)
    check("analyst: freed > 0", freed > 0)

    class FakeConformal:
        def __init__(self):
            from collections import OrderedDict
            self._lock = threading.RLock()
            self._pending = OrderedDict()
            for i in range(2000):
                self._pending[f"pred_{i}"] = {"p": 0.7, "lo": 0.6, "hi": 0.8}

    fc = FakeConformal()
    check("conformal: 2000 pendentes antes", len(fc._pending) == 2000)
    freed = cleanup_conformal_pending(10, conformal=fc)
    check("conformal: limpou ~1000 pendentes",
          len(fc._pending) < 2000 and len(fc._pending) >= 500,
          f"{len(fc._pending)} restantes")
    check("conformal: freed > 0", freed > 0)

    class FakeBuilder:
        def __init__(self, building=False, order_size=26000):
            self._building = building
            self._order = list(range(order_size))

        def status(self):
            return {"building": self._building}

    class FakeMC:
        def __init__(self, building=False):
            self.builder = FakeBuilder(building)

    fm_done = FakeMC(building=False)
    freed = cleanup_mcgrid_order(10, mc=fm_done)
    check("mcgrid: limpou order (build completo)", len(fm_done.builder._order) == 0)
    check("mcgrid: freed > 0", freed > 0)

    fm_building = FakeMC(building=True)
    freed2 = cleanup_mcgrid_order(10, mc=fm_building)
    check("mcgrid: nao toca durante build", len(fm_building.builder._order) == 26000)
    check("mcgrid: freed = 0 durante build", freed2 == 0)

    class FakeBus:
        def __init__(self):
            import queue
            self._q = queue.Queue(maxsize=100)
            for i in range(50):
                self._q.put_nowait({"view": {"minute": i}, "payload": {"x": "y" * 500}})
            self._flushed = False

        def flush_sync(self, timeout=2.0):
            self._flushed = True
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except Exception:
                    break

    fbus = FakeBus()
    check("feedbus: 50 itens na fila", fbus._q.qsize() == 50)
    freed = cleanup_feedbus(10, bus=fbus)
    check("feedbus: flusheado", fbus._flushed is True)
    check("feedbus: fila vazia apos flush", fbus._q.qsize() == 0)
    check("feedbus: freed > 0", freed > 0)

    ok = start_cache_management(
        bus=None, conformal=None, mc=None, browser=None, analyst=None,
        ram_limit_mb=100, gc_threshold_mb=80, check_interval=1.0)
    check("start: inicia CACHE mesmo sem modulos", ok is True)
    check("start: CACHE rodando",
          CACHE is not None and CACHE.stats().get("running") is True)
    stop_cache_management()
    check("stop: CACHE parado",
          CACHE is not None and CACHE.stats().get("running") is False)

    ok2 = start_cache_management(
        bus=fbus, conformal=fc, mc=fm_done, browser=fb, analyst=fa,
        ram_limit_mb=100, gc_threshold_mb=80, check_interval=1.0)
    check("start: registra limpezas", ok2 is True)
    st = cache_stats()
    check("start: stats tem registries", st.get("registries", 0) >= 1,
          f"{st.get('registries', 0)}")
    stop_cache_management()

    start_cache_management(ram_limit_mb=100, check_interval=1.0)
    n1 = len(CACHE._registries)
    start_cache_management(ram_limit_mb=100, check_interval=1.0)
    n2 = len(CACHE._registries)
    check("idempotente: nao duplica", n1 == n2, f"{n1}->{n2}")
    stop_cache_management()

    print(f"\ncache_integration selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
