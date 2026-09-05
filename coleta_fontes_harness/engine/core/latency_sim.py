"""
latency_sim.py — Injetor de latência de mercado para stress-test do gate.

MÓDULO NOVO. NÃO É o replay.py — salvar com aquele nome apagaria ReplayClock,
run_ab, stream_digest e extract_segment. Este é um transformador que o replay
aplica ao stream ANTES de alimentar o engine.

A ARMADILHA SEMÂNTICA da versão recebida:
    Somar delay UNIFORME em received_at de TODOS os frames é quase no-op no
    replay: o ReplayClock deriva do received_at, então o shift é absorvido
    pela origem do relógio — todos os timings relativos ficam idênticos e as
    decisões saem iguais. Latência real só aparece quando muda o VÃO RELATIVO:
      (a) entre chegada e timestamp do evento DENTRO do frame (staleness), ou
      (b) entre DOIS streams do mesmo journal (ex.: feed de escanteios
          atrasado enquanto as odds andam no tempo real).
    Este injetador atrasa APENAS o campo de chegada dos frames SELECIONADOS
    (via `predicate`), preservando todo o resto — os dois efeitos acima
    passam a ser visíveis para o engine.
    E NUNCA usa time.time() como default (a versão recebida fazia
    frame.get("received_at", time.time()) — wall-clock vazando no replay
    fabrica exatamente o bug que o digest do run_ab existe para denunciar).
    Jitter é determinístico (seed + hash do id do frame): mesmo journal →
    mesmo stream atrasado → runs comparáveis entre si.

USO (sensibilidade do edge à latência SokkerPRO→bridge):
    inj = LatencyInjector(delay_sec=3.0, jitter_sec=2.0,
                          predicate=lambda f: f.get("stream") == "fixture")
    atrasado = list(inj.apply(frames))
    # champion = stream original, challenger = stream atrasado (run_ab)
    # → quanto do edge sobrevive a +3s ±2s de latência?

std-lib only. Python 3.9+. Windows compatível.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

__version__ = "1.0.0"

_LOG = logging.getLogger("aura.latency_sim")


class LatencyInjector:
    """Atrasa o campo de chegada de frames selecionados, deterministicamente."""

    def __init__(self,
                 delay_sec: float = 0.0,
                 jitter_sec: float = 0.0,
                 arrival_field: str = "received_at",
                 id_field: str = "fixture_id",
                 predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 seed: int = 1337) -> None:
        if delay_sec < 0 or jitter_sec < 0:
            raise ValueError("delay_sec e jitter_sec devem ser >= 0")
        self._delay = float(delay_sec)
        self._jitter = float(jitter_sec)
        self._arrival_field = arrival_field
        self._id_field = id_field
        self._predicate = predicate
        self._seed = int(seed)

        self._lock = threading.Lock()
        self._injected = 0
        self._skipped_missing = 0
        self._skipped_malformed = 0
        self._skipped_nondict = 0
        self._skipped_predicate = 0
        self._total_delay = 0.0
        self._warned_missing = False

    # ------------------------------------------------------------- interna
    def _jitter_for(self, frame: Dict[str, Any]) -> float:
        fid = frame.get(self._id_field)
        key = "" if fid is None else str(fid)
        if key == "":
            # id ausente: hash estável do conteúdo inteiro
            try:
                key = json.dumps(frame, sort_keys=True, default=str)
            except (TypeError, ValueError):
                key = repr(sorted(frame.keys()))
        digest = hashlib.sha256(("%d|%s" % (self._seed, key)).encode("utf-8")).digest()
        frac = int.from_bytes(digest[:8], "big") / float(1 << 64)  # [0, 1)
        return frac * self._jitter

    # ------------------------------------------------------------------ api
    def inject(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna frame com o campo de chegada atrasado. Frames fora do
        predicate, sem campo de chegada ou malformados passam intactos —
        sempre contabilizados em stats()."""
        if self._delay <= 0.0 and self._jitter <= 0.0:
            return frame  # modo controle: identidade

        if not isinstance(frame, dict):
            with self._lock:
                self._skipped_nondict += 1
            return frame

        if self._predicate is not None and not self._predicate(frame):
            with self._lock:
                self._skipped_predicate += 1
            return frame

        if self._arrival_field not in frame:
            with self._lock:
                self._skipped_missing += 1
                first = not self._warned_missing
                self._warned_missing = True
            if first:
                _LOG.warning("latency_sim: frames sem campo %r — passam intactos "
                             "(contabilizados em stats)", self._arrival_field)
            return frame

        try:
            base = float(frame[self._arrival_field])
        except (TypeError, ValueError):
            with self._lock:
                self._skipped_malformed += 1
            _LOG.warning("latency_sim: campo %r malformado (%r) — frame intacto",
                         self._arrival_field, frame[self._arrival_field])
            return frame

        total = self._delay + self._jitter_for(frame)
        out = dict(frame)
        out[self._arrival_field] = base + total
        out["simulated_delay_sec"] = round(total, 6)
        with self._lock:
            self._injected += 1
            self._total_delay += total
        return out

    def apply(self, frames: Iterable[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
        """Generator: aplica inject() a um iterável de frames."""
        for frame in frames:
            yield self.inject(frame)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            avg = (self._total_delay / self._injected) if self._injected else 0.0
            return {
                "latency_sim": {
                    "injected": self._injected,
                    "total_delay_sec": round(self._total_delay, 6),
                    "avg_delay_sec": round(avg, 6),
                    "skipped_predicate": self._skipped_predicate,
                    "skipped_missing": self._skipped_missing,
                    "skipped_malformed": self._skipped_malformed,
                    "skipped_nondict": self._skipped_nondict,
                    "delay_sec": self._delay,
                    "jitter_sec": self._jitter,
                }
            }


if __name__ == "__main__":
    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            sys.exit(1)

    # --- delay fixo: só o campo de chegada muda ---
    inj = LatencyInjector(delay_sec=3.0)
    f = {"fixture_id": "m1", "received_at": 1000.0, "minute": 30, "corners": 4}
    g = inj.inject(f)
    check("chegada atrasada", g["received_at"] == 1003.0)
    check("conteúdo do evento intacto",
          g["minute"] == 30 and g["corners"] == 4 and g["fixture_id"] == "m1")
    check("frame original não mutado", f["received_at"] == 1000.0)
    check("delay registrado no frame", g["simulated_delay_sec"] == 3.0)

    # --- modo controle: identidade ---
    ctrl = LatencyInjector()
    check("controle devolve o mesmo objeto", ctrl.inject(f) is f)

    # --- jitter determinístico ---
    inj2 = LatencyInjector(delay_sec=2.0, jitter_sec=4.0)
    a = inj2.inject(dict(f))
    b = inj2.inject(dict(f))
    check("jitter determinístico", a["received_at"] == b["received_at"])
    d = a["simulated_delay_sec"]
    check("delay total dentro do intervalo", 2.0 <= d <= 6.0, "d=%.6f" % d)

    # --- predicate: só o alvo é atrasado (o uso correto anti-no-op) ---
    inj3 = LatencyInjector(delay_sec=5.0,
                           predicate=lambda fr: fr.get("fixture_id") == "m1")
    hit = inj3.inject({"fixture_id": "m1", "received_at": 10.0})
    miss = inj3.inject({"fixture_id": "m2", "received_at": 10.0})
    check("alvo atrasado", hit["received_at"] == 15.0)
    check("fora do alvo intacto",
          miss["received_at"] == 10.0 and "simulated_delay_sec" not in miss)

    # --- campo ausente: contabiliza e passa intacto (sem wall-clock!) ---
    inj4 = LatencyInjector(delay_sec=1.0)
    nofield = {"fixture_id": "m9", "minute": 5}
    same = inj4.inject(nofield)
    check("sem campo de chegada passa intacto", same == nofield)
    st4 = inj4.stats()["latency_sim"]
    check("skip contabilizado", st4["skipped_missing"] == 1 and st4["injected"] == 0)

    # --- campo malformado ---
    bad = inj4.inject({"fixture_id": "m8", "received_at": "nao-numerico"})
    check("campo malformado passa intacto", bad["received_at"] == "nao-numerico")
    check("malformado contabilizado",
          inj4.stats()["latency_sim"]["skipped_malformed"] == 1)

    # --- apply() sobre iterável + stats ---
    inj5 = LatencyInjector(delay_sec=1.0)
    frames = [{"fixture_id": "m%d" % i, "received_at": float(i)} for i in range(5)]
    out = list(inj5.apply(frames))
    check("apply transforma todos", len(out) == 5 and out[3]["received_at"] == 4.0)
    st = inj5.stats()["latency_sim"]
    check("stats coerentes", st["injected"] == 5 and abs(st["total_delay_sec"] - 5.0) < 1e-9)
    print("ALL TESTS PASSED - latency_sim.py")
