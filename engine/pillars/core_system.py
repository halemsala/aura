#!/usr/bin/env python3
"""AURA QUANT-X V13.0 — core_system.py — Topologia unificada (pilares 1,2,4,5,8,10)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import struct
import threading
import time
from multiprocessing import Array
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import numpy as np

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SHM_FLOATS = 50_000
_GLOBAL_RING: Optional[Array] = None
_ALPHA_ARR: Optional[Array] = None
_CONFIG_ARR: Optional[Array] = None
_LOG_RING: Optional[Array] = None
_LOG_META: Optional[Array] = None


def init_shared_memory() -> None:
    global _GLOBAL_RING, _ALPHA_ARR, _CONFIG_ARR, _LOG_RING, _LOG_META
    if _GLOBAL_RING is None:
        _GLOBAL_RING = Array("d", [0.0] * SHM_FLOATS, lock=False)
        _GLOBAL_RING[0] = 0.55
        _GLOBAL_RING[1] = 0.50
        _GLOBAL_RING[2] = 0.0
    if _ALPHA_ARR is None:
        _ALPHA_ARR = Array("d", [1.0] * 500, lock=False)
    if _CONFIG_ARR is None:
        _CONFIG_ARR = Array("d", [0.0] * 64, lock=False)
        _CONFIG_ARR[0] = 0.65
        _CONFIG_ARR[1] = 0.45
        _CONFIG_ARR[2] = 20.0
        _CONFIG_ARR[3] = 10000.0
    if _LOG_RING is None:
        _LOG_RING = Array("d", [0.0] * 4096, lock=False)
    if _LOG_META is None:
        _LOG_META = Array("i", [0, 0], lock=False)


def get_ring() -> Array:
    if _GLOBAL_RING is None:
        init_shared_memory()
    return _GLOBAL_RING  # type: ignore


def get_alphas() -> Array:
    if _ALPHA_ARR is None:
        init_shared_memory()
    return _ALPHA_ARR  # type: ignore


def get_config() -> Array:
    if _CONFIG_ARR is None:
        init_shared_memory()
    return _CONFIG_ARR  # type: ignore


def sync_twin_to_ring(prob: float, momentum: float = 0.0, pressure: float = 0.0) -> None:
    ring = get_ring()
    ring[0] = float(max(0.0, min(1.0, prob)))
    ring[1] = float(max(0.0, min(1.0, momentum)))
    ring[2] = float(pressure)


class DataStoreArrow:
    """Pilar 1 — buffer RAM, flush assíncrono (zero I/O no hot path)."""

    def __init__(self, max_rows: int = 10_000, out_dir: str = "logs_arrow") -> None:
        self.max_rows = max_rows
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._ts: List[float] = []
        self._rota: List[str] = []
        self._dados: List[str] = []
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
        self._file_idx = 0
        self._pending_flush = False

    async def inserir(self, rota: str, dados: str) -> None:
        async with self._lock:
            self._ts.append(time.time())
            self._rota.append(rota)
            self._dados.append(dados[:4000])
            if len(self._ts) >= self.max_rows:
                await asyncio.get_event_loop().run_in_executor(None, self._flush)

    def inserir_sync(self, rota: str, dados: str) -> None:
        with self._thread_lock:
            self._ts.append(time.time())
            self._rota.append(rota)
            self._dados.append(dados[:4000])
            if len(self._ts) >= self.max_rows:
                self._flush()

    def _flush(self) -> None:
        if not self._ts:
            return
        path = self.out_dir / f"logs_events_{self._file_idx}_{int(time.time())}.parquet"
        try:
            if HAS_ARROW:
                table = pa.table({
                    "ts": pa.array(self._ts, type=pa.float64()),
                    "rota": pa.array(self._rota, type=pa.string()),
                    "dados": pa.array(self._dados, type=pa.string()),
                })
                pq.write_table(table, str(path), compression="snappy")
            else:
                jpath = path.with_suffix(".jsonl")
                with jpath.open("w", encoding="utf-8") as f:
                    for t, r, d in zip(self._ts, self._rota, self._dados):
                        f.write(json.dumps({"ts": t, "rota": r, "dados": d}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        self._file_idx += 1
        self._ts.clear()
        self._rota.clear()
        self._dados.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            "buffered": len(self._ts),
            "flushed_files": self._file_idx,
            "arrow": HAS_ARROW,
            "max_rows": self.max_rows,
        }


class RoteadorVetorial:
    """Pilar 2 — embeddings + cosseno (sem if/else de string no hot path)."""

    INTENT_TEXTS = [
        "trading corner odds edge kelly risk",
        "voice audio speech tts stt speak",
        "health status diagnostic latency",
        "general chat conversation help",
    ]
    INTENT_LABELS = ["trading", "voice", "health", "general"]

    def __init__(self) -> None:
        self._model = None
        self._anchors: Optional[np.ndarray] = None
        self._fallback_tfidf: Dict[str, np.ndarray] = {}
        self._ready = False
        self._load()

    def _load(self) -> None:
        if HAS_ST:
            try:
                self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                self._anchors = self._model.encode(self.INTENT_TEXTS, normalize_embeddings=True)
                self._ready = True
                return
            except Exception:
                self._model = None
        vocab: Dict[str, int] = {}
        for t in self.INTENT_TEXTS:
            for w in t.split():
                if w not in vocab:
                    vocab[w] = len(vocab)
        dim = max(len(vocab), 1)
        for label, text in zip(self.INTENT_LABELS, self.INTENT_TEXTS):
            vec = np.zeros(dim, dtype=np.float32)
            for w in text.split():
                vec[vocab[w]] += 1.0
            n = np.linalg.norm(vec)
            if n > 0:
                vec /= n
            self._fallback_tfidf[label] = vec
        self._vocab = vocab
        self._ready = True

    def _embed_fallback(self, texto: str) -> np.ndarray:
        dim = len(self._vocab)
        vec = np.zeros(dim, dtype=np.float32)
        for w in texto.lower().split():
            if w in self._vocab:
                vec[self._vocab[w]] += 1.0
        n = np.linalg.norm(vec)
        if n > 0:
            vec /= n
        return vec

    def scores(self, texto: str) -> Dict[str, float]:
        if not texto or not texto.strip():
            return {lab: 0.0 for lab in self.INTENT_LABELS}
        if self._model is not None and self._anchors is not None:
            q = self._model.encode([texto], normalize_embeddings=True)[0]
            sims = (self._anchors @ q).tolist()
            return {lab: float(s) for lab, s in zip(self.INTENT_LABELS, sims)}
        q = self._embed_fallback(texto)
        out: Dict[str, float] = {}
        for lab, anc in self._fallback_tfidf.items():
            out[lab] = float(np.dot(q, anc))
        return out

    def obter_rota(self, texto: str) -> str:
        sc = self.scores(texto)
        return max(sc.items(), key=lambda kv: kv[1])[0]


class PipelineAudioPontuacao:
    """Pilar 4 — fila assíncrona, split por pontuação."""

    def __init__(self) -> None:
        self.regex_split = re.compile(r"([.!?…]+)")
        self.fila: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._running = False

    async def gerar_from_tokens(self, tokens: AsyncIterator[str]) -> List[str]:
        buffer = ""
        chunks: List[str] = []
        async for tok in tokens:
            buffer += tok
            partes = self.regex_split.split(buffer)
            while len(partes) >= 3:
                frag = (partes[0] + partes[1]).strip()
                if frag:
                    chunks.append(frag)
                    try:
                        self.fila.put_nowait(frag)
                    except asyncio.QueueFull:
                        pass
                partes = partes[2:]
            buffer = "".join(partes)
        if buffer.strip():
            chunks.append(buffer.strip())
            try:
                self.fila.put_nowait(buffer.strip())
            except asyncio.QueueFull:
                pass
        return chunks

    async def consumir(self, timeout: float = 0.05) -> Optional[str]:
        try:
            return await asyncio.wait_for(self.fila.get(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None


class MotorQuantDesacoplado:
    """Pilar 5 — lê Gêmeo Digital / estado direto da shared memory."""

    def __init__(self) -> None:
        init_shared_memory()
        self.ring = get_ring()
        self.cfg = get_config()
        self._local_cache: Dict[str, float] = {}

    def write_prob(self, prob: float, slot: int = 0) -> None:
        self.ring[slot] = float(max(0.0, min(1.0, prob)))

    def obter_decisao(self, estado_hash: str) -> Dict[str, Any]:
        if estado_hash in self._local_cache:
            probabilidade = self._local_cache[estado_hash]
        else:
            probabilidade = float(self.ring[0])
            momentum = float(self.ring[1])
            pressure = float(self.ring[2])
            h = abs(hash(estado_hash)) % 997
            jitter = float(self.ring[min(1 + (h % 100), len(self.ring) - 1)]) * 0.01
            probabilidade = max(0.0, min(1.0, probabilidade + 0.05 * momentum + 0.02 * pressure + jitter))
            self._local_cache[estado_hash] = probabilidade
            if len(self._local_cache) > 10_000:
                self._local_cache.clear()
        buy_th = float(self.cfg[0]) if self.cfg[0] > 0 else 0.65
        watch_th = float(self.cfg[1]) if self.cfg[1] > 0 else 0.45
        if probabilidade > buy_th:
            acao = "BUY"
        elif probabilidade > watch_th:
            acao = "WATCH"
        else:
            acao = "HOLD"
        return {
            "acao": acao,
            "edge": round(probabilidade, 4),
            "hash": estado_hash[:32],
            "momentum": float(self.ring[1]),
            "pressure": float(self.ring[2]),
            "source": "shared_memory_twin",
        }


class ObservabilidadeSegura:
    """Pilar 8+10 — log em memória; flush sequencial por tempo/tamanho."""

    def __init__(self, dir_path: str = "logs_obs") -> None:
        self.dir_path = Path(dir_path)
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self._buffer: List[str] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._last_flush = time.time()
        self._max_buf = 200
        self._max_age = 5.0

    def logar(self, dados: dict, redact_keys: Optional[List[str]] = None) -> None:
        redact_keys = redact_keys or ["token", "password", "secret", "api_key"]
        safe = {k: ("***" if str(k).lower() in redact_keys else v) for k, v in dados.items()}
        safe["_ts"] = time.time()
        linha = json.dumps(safe, ensure_ascii=False)
        with self._lock:
            self._buffer.append(linha)
            if _LOG_META is not None:
                _LOG_META[0] = len(self._buffer)
            if len(self._buffer) >= self._max_buf or (time.time() - self._last_flush) > self._max_age:
                self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if not self._buffer:
            return
        self._seq += 1
        path = self.dir_path / f"evt_{int(time.time())}_{self._seq}.jsonl"
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(self._buffer) + "\n")
        except Exception:
            pass
        self._buffer.clear()
        self._last_flush = time.time()
        if _LOG_META is not None:
            _LOG_META[0] = 0
            _LOG_META[1] = self._seq

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def stats(self) -> Dict[str, Any]:
        return {"buffered": len(self._buffer), "flushed_seq": self._seq}


class AlphaLearningSharedMem:
    """Alphas em shared memory — zero disco no hot path."""

    def __init__(self) -> None:
        init_shared_memory()
        self.alphas = get_alphas()

    def atualizar(self, idx_equipe: int, resultado: float, confianca: float = 1.0) -> float:
        idx = int(idx_equipe) % len(self.alphas)
        lr = 0.05 * float(max(0.0, min(1.0, confianca)))
        atual = float(self.alphas[idx])
        alvo = float(max(0.0, min(2.0, resultado)))
        novo = atual + lr * (alvo - atual)
        self.alphas[idx] = novo
        return novo

    def obter(self, idx_equipe: int) -> float:
        return float(self.alphas[int(idx_equipe) % len(self.alphas)])


_store = DataStoreArrow(out_dir=str(Path(__file__).resolve().parent / "logs_arrow"))
_router = RoteadorVetorial()
_audio = PipelineAudioPontuacao()
_quant = MotorQuantDesacoplado()
_obs = ObservabilidadeSegura(dir_path=str(Path(__file__).resolve().parent / "logs_obs"))
_alpha = AlphaLearningSharedMem()

app = FastAPI(title="AURA QUANT-X Core System", version="13.0.0")


class TextoIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=8000)
    estado_hash: Optional[str] = None


class AlphaIn(BaseModel):
    idx_equipe: int = 0
    resultado: float = 1.0
    confianca: float = 1.0


class TwinIn(BaseModel):
    prob: float = 0.5
    momentum: float = 0.0
    pressure: float = 0.0


@app.on_event("startup")
async def _startup() -> None:
    init_shared_memory()
    _obs.logar({"event": "startup", "version": "13.0.0", "st": HAS_ST, "arrow": HAS_ARROW})


@app.get("/health")
def health() -> Dict[str, Any]:
    ring = get_ring()
    return {
        "ok": True,
        "service": "aura_core_system",
        "version": "13.0.0",
        "ring0": float(ring[0]),
        "ring1": float(ring[1]),
        "ring2": float(ring[2]),
        "store": _store.stats(),
        "obs": _obs.stats(),
        "sentence_transformers": HAS_ST,
        "pyarrow": HAS_ARROW,
        "shm_slots": SHM_FLOATS,
    }


@app.post("/api/route")
async def api_route(body: TextoIn) -> Dict[str, Any]:
    rota = _router.obter_rota(body.texto)
    scores = _router.scores(body.texto)
    await _store.inserir(rota, body.texto[:2000])
    _obs.logar({"event": "route", "rota": rota, "preview": body.texto[:120]})
    result: Dict[str, Any] = {"rota": rota, "scores": scores}
    if rota == "trading":
        h = body.estado_hash or hashlib.md5(body.texto.encode("utf-8", errors="ignore")).hexdigest()
        result["quant"] = _quant.obter_decisao(h)
    return result


@app.post("/api/quant")
def api_quant(body: TextoIn) -> Dict[str, Any]:
    h = body.estado_hash or hashlib.md5(body.texto.encode("utf-8", errors="ignore")).hexdigest()
    return _quant.obter_decisao(h)


@app.post("/api/alpha")
def api_alpha(body: AlphaIn) -> Dict[str, Any]:
    novo = _alpha.atualizar(body.idx_equipe, body.resultado, body.confianca)
    return {"idx": body.idx_equipe, "alpha": novo}


@app.post("/api/twin_sync")
def api_twin_sync(body: TwinIn) -> Dict[str, Any]:
    sync_twin_to_ring(body.prob, body.momentum, body.pressure)
    ring = get_ring()
    return {"ok": True, "ring0": float(ring[0]), "ring1": float(ring[1]), "ring2": float(ring[2])}






@app.get("/api/bandwidth")
def api_bandwidth() -> Dict[str, Any]:
    try:
        from engine.infra.network_bandwidth import collect_bandwidth_report
        return collect_bandwidth_report()
    except Exception:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from infra.network_bandwidth import collect_bandwidth_report
            return collect_bandwidth_report()
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


@app.post("/api/bandwidth/start")
def api_bandwidth_start(interval_sec: float = 2.0) -> Dict[str, Any]:
    try:
        from engine.infra.network_bandwidth import start_realtime_monitor
        return start_realtime_monitor(interval_sec)
    except Exception:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from infra.network_bandwidth import start_realtime_monitor
            return start_realtime_monitor(interval_sec)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


@app.post("/api/bandwidth/stop")
def api_bandwidth_stop() -> Dict[str, Any]:
    try:
        from engine.infra.network_bandwidth import stop_realtime_monitor
        return stop_realtime_monitor()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/latency")
def api_latency() -> Dict[str, Any]:
    try:
        from engine.infra.network_latency import collect_latency_report
        return collect_latency_report()
    except Exception:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from infra.network_latency import collect_latency_report
            return collect_latency_report()
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


@app.post("/api/latency/start")
def api_latency_start(interval_sec: float = 2.0) -> Dict[str, Any]:
    try:
        from engine.infra.network_latency import start_realtime_monitor
        return start_realtime_monitor(interval_sec)
    except Exception:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from infra.network_latency import start_realtime_monitor
            return start_realtime_monitor(interval_sec)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}


@app.post("/api/latency/stop")
def api_latency_stop() -> Dict[str, Any]:
    try:
        from engine.infra.network_latency import stop_realtime_monitor
        return stop_realtime_monitor()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "aura_core_system", "docs": "/docs", "health": "/health", "version": "13.0.0"}


if __name__ == "__main__":
    import uvicorn
    init_shared_memory()
    port = int(os.environ.get("AURA_CORE_PORT", "8088"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
