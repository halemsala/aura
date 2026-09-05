#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — FeedBus: hot path nao-bloqueante + writer dedicado em lote.

Local: engine/core/feed_bus.py
Dependencias: NENHUMA (stdlib). Python 3.9+. Windows OK.

Filosofia:
- O handler HTTP valida, normaliza e publica. NUNCA faz I/O de disco.
- Um writer thread drena a fila em lotes (1 append por lote, nao por evento).
- Fila limitada = backpressure real: sob carga patologica, descarta com
  metrica e log — nunca trava a ingestao, nunca estoura a RAM.
- Subscribers (consumidores em memoria) rodam ANTES dos sinks.
- Nenhuma excecao e silenciosa: tudo e logado com traceback e contabilizado.

Uso (sync — bridge):
    bus = FeedBus(name="bridge_feed")
    bus.add_sink(JsonlSink(Path("./live_feed.jsonl"), rotate="daily"))
    bus.add_sink(LatestJsonSink(Path("./live_latest.json")))
    bus.subscribe(on_batch)          # def on_batch(records: list[dict]) -> None
    bus.start()
    ok = bus.publish(record)         # non-bloqueante (~microssegundos)
    bus.close()                      # flush + join graceful

Uso (async — FastAPI):
    bus.publish(record)              # seguro no event loop (nao bloqueia)
    await bus.aflush(2.0)            # espera fila zerar (via to_thread)
"""
from __future__ import annotations

import asyncio
import atexit
import gzip
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.feedbus")

__version__ = "1.0.0"
__all__ = ["FeedBus", "FeedBusClient", "JsonlSink", "LatestJsonSink", "atomic_write_text"]

_SENTINEL = object()


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Escrita atomica: tmp + os.replace. Leitor nunca ve arquivo truncado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


class FeedBusClient:
    """Cliente WS opt-in com reconexão exponencial e cancelamento cooperativo."""
    def __init__(self, uri: str = "ws://127.0.0.1:8765", max_retry_delay: float = 30.0):
        self.uri = uri
        self._retry_delay = 1.0
        self._max_retry_delay = max(1.0, float(max_retry_delay))

    async def connect_with_retry(self, connect_fn, listen_fn=None, stop_event=None):
        """Conecta usando callbacks injetados; não cria sockets nem faz rede sozinho."""
        delay = 1.0
        while stop_event is None or not stop_event.is_set():
            try:
                log.info("Conectando a %s...", self.uri)
                connection = await connect_fn(self.uri)
                self._retry_delay = 1.0
                delay = 1.0
                log.info("Conexão WS estabelecida.")
                if listen_fn is None:
                    return connection
                await listen_fn(connection)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("WS desconectado: %s. Tentando em %.1fs.", exc, delay)
                if stop_event is None:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.to_thread(stop_event.wait, delay)
                delay = min(delay * 2.0, self._max_retry_delay)
                self._retry_delay = delay
        return None


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------
class JsonlSink:
    """Append JSONL em lote com rotacao (diaria ou por tamanho).

    - Mantem o arquivo ABERTO entre lotes (1 syscall de append por lote).
    - rotate=None   : mesmo arquivo para sempre (mesmo nome do legado).
    - rotate="daily": um arquivo por dia — name-YYYYMMDD.jsonl (muda o nome!).
    - rotate="size" : renomeia para name.<epoch>.<n>.jsonl ao exceder max_bytes.
    - fsync: "never" (rapido) | "batch" (duravel por lote) | "rotate" (default).
    - NUNCA lanca para o bus: erros sao logados e contabilizados.
    """

    def __init__(self, path, rotate: Optional[str] = "daily",
                 max_bytes: int = 256 * 1024 * 1024, gzip_rotated: bool = False,
                 fsync: str = "rotate"):
        if rotate not in (None, "daily", "size"):
            raise ValueError(f"rotate invalido: {rotate!r}")
        if fsync not in ("never", "batch", "rotate"):
            raise ValueError(f"fsync invalido: {fsync!r}")
        self.path = Path(path)
        self.rotate = rotate
        self.max_bytes = int(max_bytes)
        self.gzip_rotated = bool(gzip_rotated)
        self.fsync = fsync
        self._lock = threading.Lock()
        self._fh = None
        self._cur_path: Optional[Path] = None
        self._bytes = 0
        self._rotate_seq = 0
        self.records = 0
        self.batches = 0
        self.errors = 0
        self.rotations = 0

    # -- internals ----------------------------------------------------------
    def _daily_path(self) -> Path:
        stamp = time.strftime("%Y%m%d")
        if stamp in self.path.name:
            return self.path
        return self.path.with_name(f"{self.path.stem}-{stamp}{self.path.suffix}")

    def _ensure_open(self) -> None:
        if self.rotate == "size" and self._fh is None and \
                self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            self._do_rotate_size()
        target = self._daily_path() if self.rotate == "daily" else self.path
        if self._fh is not None and self._cur_path == target:
            return
        self._close_quietly()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(target, "a", encoding="utf-8")
        self._cur_path = target
        try:
            self._bytes = target.stat().st_size
        except OSError:
            self._bytes = 0

    def _do_rotate_size(self) -> None:
        self._close_quietly()
        if self.path.exists():
            self._rotate_seq += 1
            dst = self.path.with_name(
                f"{self.path.stem}.{int(time.time())}.{self._rotate_seq}{self.path.suffix}")
            try:
                os.replace(str(self.path), str(dst))
                self.rotations += 1
                if self.gzip_rotated:
                    self._gzip_file(dst)
            except Exception:
                log.exception("[JsonlSink] rotacao falhou: %s", self.path)
        self._bytes = 0
        self._cur_path = None  # forca reabrir no proximo lote

    def _gzip_file(self, p: Path) -> None:
        try:
            with open(p, "rb") as f_in, gzip.open(str(p) + ".gz", "wb", compresslevel=3) as f_out:
                shutil.copyfileobj(f_in, f_out)
            p.unlink()
        except Exception:
            log.exception("[JsonlSink] gzip da rotacao falhou (original mantido): %s", p)

    def _close_quietly(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                if self.fsync == "rotate":
                    os.fsync(self._fh.fileno())
            except Exception:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            self._cur_path = None

    # -- API ----------------------------------------------------------------
    def write_batch(self, batch: List[dict]) -> None:
        if not batch:
            return
        buf = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in batch)
        with self._lock:
            try:
                self._ensure_open()
                fh = self._fh
                if fh is None:  # paranoia
                    raise OSError("arquivo nao aberto")
                fh.write(buf)
                fh.flush()
                if self.fsync == "batch":
                    os.fsync(fh.fileno())
                self._bytes += len(buf.encode("utf-8"))
                self.records += len(batch)
                self.batches += 1
                if self.rotate == "size" and self._bytes >= self.max_bytes:
                    self._do_rotate_size()
            except Exception:
                self.errors += 1
                log.exception("[JsonlSink] falha ao gravar lote (%d registros) — continuando",
                              len(batch))

    def close(self) -> None:
        with self._lock:
            self._close_quietly()


class LatestJsonSink:
    """Mantem o ULTIMO registro (ou ultimo por chave) com escrita atomica.

    - key_fn=None: escreve `path` com o ultimo registro do lote (modo legado).
    - key_fn=fn(record)->str: escreve `path` (ultimo global) E
      path.parent/latest-<chave>.json por chave (LRU em memoria, max_keys).
    Arquivos de chaves antigas NAO sao deletados (retencao = tarefa externa).
    """

    def __init__(self, path, key_fn: Optional[Callable[[dict], str]] = None,
                 max_keys: int = 64, key_prefix: str = "latest-"):
        self.path = Path(path)
        self.key_fn = key_fn
        self.max_keys = int(max_keys)
        self.key_prefix = key_prefix
        self._keys: Dict[str, float] = {}   # chave -> ts (para LRU)
        self._lock = threading.Lock()
        self.writes = 0
        self.errors = 0
        self.evictions = 0

    def _key_path(self, k: str) -> Path:
        safe = re.sub(r"[^\w.\-]+", "_", k)[:80] or "_"
        return self.path.parent / f"{self.key_prefix}{safe}.json"

    def write_batch(self, batch: List[dict]) -> None:
        if not batch:
            return
        try:
            with self._lock:
                if self.key_fn is not None:
                    per_key: Dict[str, dict] = {}
                    for r in batch:
                        try:
                            k = str(self.key_fn(r))
                        except Exception:
                            k = "_unknown"
                        per_key[k] = r
                    now = time.time()
                    for k, r in per_key.items():
                        self._keys[k] = now
                        atomic_write_text(
                            self._key_path(k),
                            json.dumps(r, ensure_ascii=False, default=str, indent=2))
                    while len(self._keys) > self.max_keys:
                        oldest = min(self._keys, key=self._keys.get)  # type: ignore[arg-type]
                        self._keys.pop(oldest, None)
                        self.evictions += 1
                last = batch[-1]
                atomic_write_text(
                    self.path, json.dumps(last, ensure_ascii=False, default=str, indent=2))
                self.writes += 1
        except Exception:
            self.errors += 1
            log.exception("[LatestJsonSink] falha (lote ignorado)")


# ---------------------------------------------------------------------------
# FeedBus
# ---------------------------------------------------------------------------
class FeedBus:
    """Barramento de ingestao: publish non-bloqueante + writer em lote.

    Backpressure: fila limitada (maxsize). Politica de descarte:
      - "newest" (default): recusa o registro que chegou (protege os em voo).
      - "oldest"          : descarta o mais antigo, entra o mais fresco.
    Toda descarga e contabilizada em stats() — nada acontece no escuro.
    """

    def __init__(self, name: str = "feed", *, maxsize: int = 4096,
                 batch_size: int = 256, flush_interval: float = 0.25,
                 drop_policy: str = "newest", stale_ttl: Optional[float] = None,
                 writers: int = 1, subscriber_warn_ms: float = 50.0,
                 close_timeout: float = 5.0):
        if drop_policy not in ("newest", "oldest"):
            raise ValueError(f"drop_policy invalido: {drop_policy!r}")
        self.name = str(name)
        self.batch_size = int(batch_size)
        self.flush_interval = float(flush_interval)
        self.drop_policy = drop_policy
        self.stale_ttl = stale_ttl  # seg: registros mais velhos que isso sao descartados no writer
        self.subscriber_warn_ms = float(subscriber_warn_ms)
        self.close_timeout = float(close_timeout)
        self._n_writers = max(1, int(writers))

        self._q: "queue.Queue[Any]" = queue.Queue(maxsize=int(maxsize))
        self._subs: List[tuple] = []      # (sid, fn, mode)
        self._sinks: List[Any] = []
        self._threads: List[threading.Thread] = []
        self._st = {
            "published": 0, "dropped_full": 0, "dropped_stale": 0,
            "batches": 0, "records": 0, "max_depth": 0,
            "subscriber_errors": 0, "sink_errors": 0, "slow_subscriber_events": 0,
            "last_flush_ms": 0.0, "last_flush_ts": 0.0,
        }
        self._st_lock = threading.Lock()
        self._inflight = 0
        self._flush_cond = threading.Condition()
        self._running = False
        self._closing = False
        self._closed = False
        self._started_at = 0.0
        self._warn_counter = 0

    # -- API ------------------------------------------------------------------
    def publish(self, record: dict, *, key: Optional[str] = None,
                ts: Optional[float] = None) -> bool:
        """Publica um registro. NON-BLOQUEANTE (seguro em handler HTTP e event loop).

        Retorna True se aceito; False se descartado por backpressure ou fechamento.
        """
        if self._closed or self._closing:
            return False
        item = {"r": record, "k": key, "ts": ts if ts is not None else time.time()}
        with self._flush_cond:
            self._inflight += 1
        try:
            self._q.put_nowait(item)
        except queue.Full:
            if self.drop_policy == "oldest":
                try:
                    self._q.get_nowait()          # sai o mais antigo...
                    self._q.put_nowait(item)      # ...entra o mais fresco
                    with self._flush_cond:
                        self._inflight -= 1       # compensa o antigo descartado
                    with self._st_lock:
                        self._st["dropped_full"] += 1
                        self._st["published"] += 1
                    return True
                except (queue.Full, queue.Empty):
                    pass
            with self._flush_cond:
                self._inflight -= 1
            with self._st_lock:
                self._st["dropped_full"] += 1
                self._warn_counter += 1
                warn = (self._warn_counter % 500 == 1)
                total = self._st["dropped_full"]
            if warn:
                log.warning("[%s] fila cheia — %d descartes acumulados "
                            "(ingestao mais rapida que o writer)", self.name, total)
            return False
        with self._st_lock:
            self._st["published"] += 1
            d = self._q.qsize()
            if d > self._st["max_depth"]:
                self._st["max_depth"] = d
        return True

    def subscribe(self, fn: Callable[[List[dict]], None], *, sid: str = "",
                  mode: str = "batch") -> Callable[[], None]:
        """Consumidor em memoria. RODA NO THREAD DO WRITER:
        nao faca I/O pesado aqui (use um sink); excessao aqui nunca mata o bus.
        mode "batch": fn(lista_de_registros). mode "record": fn(registro) por item.
        Retorna funcao de dessassinatura.
        """
        if mode not in ("batch", "record"):
            raise ValueError(f"mode invalido: {mode!r}")
        sid = sid or getattr(fn, "__name__", f"sub{len(self._subs)}")
        entry = (sid, fn, mode)
        self._subs.append(entry)

        def _unsub() -> None:
            try:
                self._subs.remove(entry)
            except ValueError:
                pass
        return _unsub

    def add_sink(self, sink: Any) -> "FeedBus":
        """Sink precisa implementar write_batch(records: list[dict])."""
        if not hasattr(sink, "write_batch"):
            raise TypeError("sink precisa de metodo write_batch(list[dict])")
        self._sinks.append(sink)
        return self

    def start(self) -> "FeedBus":
        if self._running:
            return self
        self._running = True
        self._closing = False
        self._closed = False
        self._started_at = time.time()
        for i in range(max(1, getattr(self, "_n_writers", 1) or 1)):
            t = threading.Thread(target=self._writer_loop,
                                 name=f"{self.name}-writer-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        atexit.register(self._atexit_close)
        return self

    def close(self, timeout: Optional[float] = None) -> None:
        if self._closed:
            return
        self._closing = True
        deadline = time.time() + (self.close_timeout if timeout is None else float(timeout))
        for _ in self._threads:
            try:
                self._q.put_nowait(_SENTINEL)
            except queue.Full:
                break
        for t in self._threads:
            t.join(timeout=max(0.0, deadline - time.time()))
        for sink in self._sinks:
            try:
                if hasattr(sink, "close"):
                    sink.close()
            except Exception:
                log.exception("[%s] sink falhou no close", self.name)
        self._closed = True
        leftover = self._q.qsize()
        if leftover:
            log.warning("[%s] %d itens nao drenados no close", self.name, leftover)

    def flush_sync(self, timeout: float = 5.0) -> bool:
        """Bloqueia ate todos os publicados serem despachados (ou timeout)."""
        deadline = time.time() + float(timeout)
        with self._flush_cond:
            while self._inflight > 0:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self._flush_cond.wait(remaining)
            return True

    async def aflush(self, timeout: float = 5.0) -> bool:
        """Versao async do flush (nao bloqueia o event loop)."""
        import asyncio
        return await asyncio.to_thread(self.flush_sync, timeout)

    def stats(self) -> dict:
        with self._st_lock:
            st = dict(self._st)
        st["queue_depth"] = self._q.qsize()
        st["in_flight"] = self._inflight
        st["subscribers"] = len(self._subs)
        st["sinks"] = len(self._sinks)
        st["running"] = self._running and not self._closed
        if self._started_at:
            st["uptime_sec"] = round(time.time() - self._started_at, 1)
            if st["batches"]:
                st["avg_batch"] = round(st["records"] / st["batches"], 1)
        return st

    # -- internals ------------------------------------------------------------
    def _atexit_close(self) -> None:
        try:
            self.close(timeout=min(self.close_timeout, 3.0))
        except Exception:
            pass

    def _inflight_add(self, delta: int) -> None:
        with self._flush_cond:
            self._inflight += delta
            if self._inflight <= 0:
                self._flush_cond.notify_all()

    def _writer_loop(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=self.flush_interval)
            except queue.Empty:
                if self._closing and self._q.empty():
                    break
                continue
            if item is _SENTINEL:
                if self._q.empty():
                    break
                continue  # drena o resto antes de sair
            batch = [item]
            while len(batch) < self.batch_size:
                try:
                    nxt = self._q.get_nowait()
                except queue.Empty:
                    break
                if nxt is _SENTINEL:
                    continue
                batch.append(nxt)
            self._dispatch(batch)

    def _dispatch(self, batch: List[dict]) -> None:
        t0 = time.perf_counter()
        n_total = len(batch)
        # 1) politica de frescor
        if self.stale_ttl is not None:
            now = time.time()
            fresh = [b for b in batch if (now - b["ts"]) <= self.stale_ttl]
            n_stale = n_total - len(fresh)
            if n_stale:
                with self._st_lock:
                    self._st["dropped_stale"] += n_stale
            batch = fresh
        records = [b["r"] for b in batch]
        # 2) subscribers primeiro (consumidores de hot path)
        if records:
            for sid, fn, mode in list(self._subs):
                t1 = time.perf_counter()
                try:
                    if mode == "record":
                        for r in records:
                            fn(r)
                    else:
                        fn(records)
                except Exception:
                    with self._st_lock:
                        self._st["subscriber_errors"] += 1
                    log.exception("[%s] subscriber %s falhou (ignorado)", self.name, sid)
                dt_ms = (time.perf_counter() - t1) * 1000.0
                if dt_ms > self.subscriber_warn_ms:
                    with self._st_lock:
                        self._st["slow_subscriber_events"] += 1
                    log.warning("[%s] subscriber %s LENTO: %.1f ms para %d registros",
                                self.name, sid, dt_ms, len(records))
            # 3) sinks (disco)
            for i, sink in enumerate(self._sinks):
                try:
                    sink.write_batch(records)
                except Exception:
                    with self._st_lock:
                        self._st["sink_errors"] += 1
                    log.exception("[%s] sink #%d falhou (ignorado)", self.name, i)
        # 4) metricas + sinal de flush
        ms = (time.perf_counter() - t0) * 1000.0
        with self._st_lock:
            self._st["batches"] += 1
            self._st["records"] += len(records)
            self._st["last_flush_ms"] = round(ms, 3)
            self._st["last_flush_ts"] = time.time()
        self._inflight_add(-n_total)


# ---------------------------------------------------------------------------
# Self-test: python engine/core/feed_bus.py
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # T1: fluxo basico end-to-end
        jsonl = td / "live_feed.jsonl"
        latest = td / "live_latest.json"
        bus = FeedBus(name="t1", maxsize=1024, batch_size=64, flush_interval=0.02)
        bus.add_sink(JsonlSink(jsonl, rotate=None))
        bus.add_sink(LatestJsonSink(latest))
        got: List[dict] = []
        bus.subscribe(lambda rs: got.extend(rs), sid="t1sub")
        bus.start()
        N = 5000
        for i in range(N):
            bus.publish({"i": i, "fixture": f"F{i % 7}"})
        ok_flush = bus.flush_sync(timeout=10.0)
        bus.close(timeout=5.0)
        lines = sum(1 for _ in jsonl.open("r", encoding="utf-8"))
        check("flush_sync termina", ok_flush)
        check("jsonl tem todas as linhas", lines == N, f"{lines}/{N}")
        last = json.loads(latest.read_text(encoding="utf-8"))
        check("latest.json = ultimo registro", last.get("i") == N - 1)
        check("subscriber recebeu tudo", len(got) == N, f"{len(got)}/{N}")
        st = bus.stats()
        check("zero drops em carga normal", st["dropped_full"] == 0)

        # T2: backpressure deterministico (publica ANTES do start)
        bus2 = FeedBus(name="t2", maxsize=16, batch_size=8, drop_policy="newest")
        bus2.add_sink(JsonlSink(td / "bp.jsonl", rotate=None))
        accepted = sum(1 for i in range(5000) if bus2.publish({"i": i}))
        bus2.start()
        bus2.flush_sync(timeout=10.0)
        bus2.close(timeout=5.0)
        st2 = bus2.stats()
        check("backpressure: fila limitada", accepted == 16, f"aceitos={accepted}")
        check("backpressure: drops contabilizados", st2["dropped_full"] == 5000 - accepted)
        check("backpressure: nada aceito foi perdido", st2["records"] == accepted)

        # T3: subscriber quebrado nao mata o writer
        bus3 = FeedBus(name="t3")
        bus3.add_sink(JsonlSink(td / "t3.jsonl", rotate=None))
        ok_seen: List[dict] = []

        def boom(rs):
            raise RuntimeError("boom")

        bus3.subscribe(boom, sid="boom")
        bus3.subscribe(lambda rs: ok_seen.extend(rs), sid="ok")
        bus3.start()
        for i in range(200):
            bus3.publish({"i": i})
        bus3.flush_sync(timeout=5.0)
        bus3.close(timeout=3.0)
        st3 = bus3.stats()
        check("subscriber quebrado nao mata o writer",
              st3["subscriber_errors"] > 0 and len(ok_seen) == 200)

        # T4: rotacao por tamanho
        rot = td / "rot.jsonl"
        bus4 = FeedBus(name="t4")
        bus4.add_sink(JsonlSink(rot, rotate="size", max_bytes=2048))
        bus4.start()
        for i in range(2000):
            bus4.publish({"i": i, "pad": "x" * 24})
        bus4.flush_sync(timeout=5.0)
        bus4.close(timeout=3.0)
        n_files = len(list(td.glob("rot.*.jsonl"))) + (1 if rot.exists() else 0)
        check("rotacao por tamanho cria multiplos arquivos", n_files >= 2, f"{n_files} arquivos")

        # T5: latest por chave
        lk = td / "latest_global.json"
        bus5 = FeedBus(name="t5")
        bus5.add_sink(LatestJsonSink(lk, key_fn=lambda r: r["fixture"], max_keys=4))
        bus5.start()
        for i in range(100):
            bus5.publish({"fixture": f"F{i % 3}", "i": i})
        bus5.flush_sync(timeout=5.0)
        bus5.close(timeout=3.0)
        check("latest por chave (3 fixtures)", len(list(td.glob("latest-F*.json"))) == 3)
        check("latest global existe", lk.exists())

    print(f"\nfeed_bus selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
