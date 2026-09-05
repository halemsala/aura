#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Gate de incerteza Conformal + adaptador para risk gates.

Local: engine/core/conformal_gate.py
Dependencias: NENHUMA (stdlib). Python 3.9+.

Matematica (split conformal, janela rolante):
  1. Cada decisao registra p (prob prevista) e, quando o resultado resolve,
     y (1 = evento ocorreu, 0 = nao ocorreu).
  2. Score de nao-conformidade: s = |p - y|.
  3. q = k-esimo menor score, com k = ceil((n+1)*(1-alpha)).
  4. Intervalo: [p - q, p + q] com garantia P(y pertence ao intervalo) >= 1-alpha
     (sob exchangeability das amostras de calibracao).

Gate de decisao:
  ENTER  : limite inferior lo >= threshold  (mesmo no pior caso, o edge existe)
  NO_BET : limite superior hi < threshold   (mesmo no melhor caso, nao existe)
  HOLD   : intervalo atravessa o threshold  (NAO decidir E a decisao certa)

Drift: reduz o alpha efetivo -> q maior -> intervalo mais largo -> mais HOLD.
Heuristica conservadora: quando o mundo muda, confiar menos na calibracao.

Frio (n < min_samples): intervalo = [0, 1] -> HOLD. Nunca fabrica confianca.

Invariante: toda decisao e advisory-only / paper_trade.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("aura.conformal")

__version__ = "1.0.0"
__all__ = ["ConformalGate", "ConformalRiskGate", "OutcomeResolver", "GateDecision"]


def _iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)
    return dt.isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _clamp01(v: Any) -> Optional[float]:
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
@dataclass
class GateDecision:
    decision: str            # "ENTER" | "HOLD" | "NO_BET"
    p: float
    threshold: float
    lo: float
    hi: float
    alpha: float             # alpha EFETIVO usado (pos-drift)
    context: str
    pool: str                # pool de calibracao usado
    n_samples: int
    reasons: List[str] = field(default_factory=list)
    pred_id: Optional[str] = None
    paper_trade: bool = True  # invariante: sempre advisory
    ts: str = ""

    def to_dict(self) -> dict:
        return {
            "decision": self.decision, "p": round(self.p, 4),
            "threshold": round(self.threshold, 4),
            "lo": round(self.lo, 4), "hi": round(self.hi, 4),
            "alpha": round(self.alpha, 4), "context": self.context,
            "pool": self.pool, "n_samples": self.n_samples,
            "reasons": list(self.reasons), "pred_id": self.pred_id,
            "paper_trade": True, "ts": self.ts,
        }


class _Pool:
    __slots__ = ("scores", "_cache", "window", "decay", "updates")

    def __init__(self, window: int, decay: Optional[float] = None):
        self.scores: Deque[float] = deque(maxlen=window)
        self._cache: Dict[float, float] = {}
        self.window = window
        self.decay = decay if (decay is not None and 0.8 < decay < 1.0) else None
        self.updates = 0

    def add(self, score: float) -> None:
        self.scores.append(float(score))
        self.updates += 1
        self._cache.clear()

    def n(self) -> int:
        return len(self.scores)

    def quantile(self, alpha: float) -> float:
        """q com P(|p-y| <= q) >= 1-alpha (conformal finito-amostral).
        Retorna inf quando n e insuficiente para a garantia pedida."""
        a = round(float(alpha), 4)
        if a in self._cache:
            return self._cache[a]
        n = len(self.scores)
        if n == 0:
            q = float("inf")
        elif self.decay is None:
            k = math.ceil((n + 1) * (1.0 - a))
            if k > n:
                q = float("inf")
            else:
                q = sorted(self.scores)[k - 1]
        else:
            q = self._weighted_quantile(a)
        if len(self._cache) > 64:
            self._cache.clear()
        self._cache[a] = q
        return q

    def _weighted_quantile(self, alpha: float) -> float:
        items = list(self.scores)
        n = len(items)
        d = self.decay
        idx = sorted(range(n), key=lambda i: items[i])
        weights = [d ** (n - 1 - i) for i in range(n)]  # peso por antiguidade
        total = sum(weights)
        acc = 0.0
        target = (1.0 - alpha) * total
        for i in idx:
            acc += weights[i]
            if acc >= target:
                return items[i]
        return items[idx[-1]]


# ---------------------------------------------------------------------------
class ConformalGate:
    """Gate conformal com persistencia (snapshot + journal replay).

    Ciclo de vida:
      evaluate/gate()  -> intervalo + decisao (consulta, rapida)
      update(p, y)     -> alimenta calibracao quando o resultado resolve
      record_prediction / resolve_prediction -> cobertura empirica rastreada
      save()/close()   -> snapshot atomico + jsonl de replay
    """

    def __init__(self, state_dir=None, *, alpha: float = 0.10, window: int = 400,
                 min_samples: int = 30, weight_decay: Optional[float] = None,
                 drift_sensitivity: float = 3.0, autosave_every: int = 25,
                 pending_max: int = 2000):
        self.alpha = float(alpha)
        self.window = int(window)
        self.min_samples = int(min_samples)
        self.drift_sensitivity = float(drift_sensitivity)
        self.autosave_every = int(autosave_every)
        self._decay = weight_decay
        self._lock = threading.RLock()
        self._pools: Dict[str, _Pool] = {"global": _Pool(self.window, weight_decay)}
        self._seq = 0
        self._updates_since_save = 0
        self._pending: "OrderedDict[str, dict]" = OrderedDict()
        self._pending_max = pending_max
        self._coverage: Deque[dict] = deque(maxlen=1000)
        self._decisions: Dict[str, int] = {"ENTER": 0, "HOLD": 0, "NO_BET": 0}
        self._last_decisions: Deque[dict] = deque(maxlen=50)
        self._started_at = time.time()
        self.state_dir = Path(state_dir) if state_dir else None
        if self.state_dir:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_path = self.state_dir / "conformal_state.jsonl"
            self._snap_path = self.state_dir / "conformal_snapshot.json"
            self._load()
        else:
            self._jsonl_path = None
            self._snap_path = None

    # -- calibracao -----------------------------------------------------------
    def update(self, p: float, y: Any, context: str = "global",
               *, ts: Optional[float] = None) -> None:
        """Alimenta a calibracao com um resultado resolvido.
        p = prob prevista NO MOMENTO DA DECISAO; y = 1/0 (ocorreu / nao ocorreu)."""
        p_c = _clamp01(p)
        if p_c is None:
            log.warning("[conformal] update ignorado: p invalido %r", p)
            return
        if isinstance(y, bool):
            y = int(y)
        if y not in (0, 1):
            y_i = _to_int(y)
            if y_i in (0, 1):
                y = y_i
            else:
                log.warning("[conformal] update ignorado: y invalido %r", y)
                return
        ctx = str(context or "global")[:64]
        with self._lock:
            self._seq += 1
            self._apply_update(p_c, int(y), ctx)
            self._journal({"seq": self._seq, "t": _iso(ts), "ev": "u",
                           "ctx": ctx, "p": p_c, "y": int(y)})
            self._updates_since_save += 1
            if self.autosave_every and self._updates_since_save >= self.autosave_every:
                self._save_locked()

    def _apply_update(self, p: float, y: int, ctx: str) -> None:
        score = abs(p - float(y))
        self._pools.setdefault("global", _Pool(self.window, self._decay)).add(score)
        if ctx and ctx != "global":
            self._pools.setdefault(ctx, _Pool(self.window, self._decay)).add(score)

    # -- consulta ---------------------------------------------------------------
    def _effective_alpha(self, drift: float) -> float:
        """Drift ALARGA o intervalo: reduz o alpha efetivo (mais cobertura exigida)."""
        try:
            d = min(1.0, max(0.0, float(drift or 0.0)))
        except (TypeError, ValueError):
            d = 0.0
        a = self.alpha / (1.0 + self.drift_sensitivity * d)
        return max(0.01, min(self.alpha, a))

    def interval(self, p: float, context: str = "global", *,
                 drift: float = 0.0) -> Tuple[float, float]:
        lo, hi, _meta = self._interval_full(p, context, drift)
        return lo, hi

    def _interval_full(self, p: Any, context: str, drift: float) -> Tuple[float, float, dict]:
        p_c = _clamp01(p)
        if p_c is None:
            return 0.0, 1.0, {"error": "p_invalido", "cold": True}
        a_eff = self._effective_alpha(drift)
        ctx = str(context or "global")[:64]
        with self._lock:
            pool_used, n, q = "none", 0, float("inf")
            pool = self._pools.get(ctx)
            if pool is not None and pool.n() >= self.min_samples:
                pool_used, n, q = ctx, pool.n(), pool.quantile(a_eff)
            else:
                g = self._pools.get("global")
                if g is not None and g.n() >= self.min_samples:
                    pool_used, n, q = "global", g.n(), g.quantile(a_eff)
        if q == float("inf"):
            return 0.0, 1.0, {"alpha": a_eff, "pool": pool_used, "n": n,
                              "q": None, "cold": True}
        lo = max(0.0, p_c - q)
        hi = min(1.0, p_c + q)
        return lo, hi, {"alpha": a_eff, "pool": pool_used, "n": n, "q": q, "cold": False}

    def gate(self, p: float, threshold: float, context: str = "global", *,
             drift: float = 0.0) -> GateDecision:
        """Gate puro: ENTER / NO_BET / HOLD pelo intervalo vs threshold."""
        lo, hi, meta = self._interval_full(p, context, drift)
        p_c = _clamp01(p)
        p_c = 0.0 if p_c is None else p_c
        thr_c = _clamp01(threshold)
        if thr_c is None:
            dec, reason = "HOLD", "threshold_invalido"
        elif meta.get("cold"):
            dec, reason = "HOLD", "cold_start: calibracao insuficiente"
        elif lo >= thr_c:
            dec = "ENTER"
            reason = (f"lo {lo:.3f} >= thr {thr_c:.3f} "
                      f"(cobertura >= {1 - meta['alpha']:.0%}, n={meta['n']}, pool={meta['pool']})")
        elif hi < thr_c:
            dec = "NO_BET"
            reason = f"hi {hi:.3f} < thr {thr_c:.3f} (sem edge mesmo no melhor caso)"
        else:
            dec = "HOLD"
            reason = f"incerteza [{lo:.3f}, {hi:.3f}] atravessa threshold {thr_c:.3f}"
        with self._lock:
            self._decisions[dec] = self._decisions.get(dec, 0) + 1
            gd = GateDecision(decision=dec, p=p_c, threshold=thr_c if thr_c is not None else 0.0,
                              lo=lo, hi=hi, alpha=meta.get("alpha", self.alpha),
                              context=str(context), pool=str(meta.get("pool", "none")),
                              n_samples=int(meta.get("n", 0)), reasons=[reason], ts=_iso())
            self._last_decisions.append(gd.to_dict())
        return gd

    # -- predicoes pendentes + cobertura empirica -------------------------------
    def record_prediction(self, pred_id: str, p: float, context: str = "global",
                          *, lo: Optional[float] = None, hi: Optional[float] = None,
                          meta: Optional[dict] = None) -> None:
        if not pred_id:
            return
        with self._lock:
            pid = str(pred_id)
            if pid in self._pending:
                return  # idempotente
            p_c = _clamp01(p)
            if p_c is None:
                return
            if lo is None or hi is None:
                lo, hi, _m = self._interval_full(p_c, context, 0.0)
            self._pending[pid] = {"p": p_c, "ctx": str(context),
                                  "lo": float(lo), "hi": float(hi),
                                  "t": time.time(), "meta": meta or {}}
            while len(self._pending) > self._pending_max:
                self._pending.popitem(last=False)
            self._seq += 1
            self._journal({"seq": self._seq, "t": _iso(), "ev": "pred", "id": pid,
                           "p": p_c, "ctx": str(context), "lo": float(lo), "hi": float(hi)})

    def resolve_prediction(self, pred_id: str, y: Any) -> Optional[dict]:
        """Resolve predicao pendente: alimenta calibracao + mede cobertura."""
        if isinstance(y, bool):
            y = int(y)
        if y not in (0, 1):
            y_i = _to_int(y)
            if y_i not in (0, 1):
                return None
            y = y_i
        pid = str(pred_id)
        with self._lock:
            pend = self._pending.pop(pid, None)
            if pend is None:
                return None
            # calibra com o p registrado NO MOMENTO DA DECISAO
            self.update(pend["p"], int(y), pend["ctx"])
            covered = (pend["lo"] - 1e-9) <= float(y) <= (pend["hi"] + 1e-9)
            cov = {"t": _iso(), "covered": bool(covered), "ctx": pend["ctx"],
                   "p": pend["p"], "y": int(y)}
            self._coverage.append(cov)
            self._seq += 1
            self._journal({"seq": self._seq, "t": cov["t"], "ev": "res", "id": pid,
                           "y": int(y), "covered": bool(covered)})
            return cov

    def expire_pending(self, ttl_seconds: float) -> int:
        """Descarta pendencias orfas SEM calibrar (resultado desconhecido
        nao vira dado — nao enviesa a calibracao)."""
        now = time.time()
        n = 0
        with self._lock:
            for pid in [k for k, v in self._pending.items() if now - v["t"] > ttl_seconds]:
                self._pending.pop(pid, None)
                self._seq += 1
                self._journal({"seq": self._seq, "t": _iso(), "ev": "exp", "id": pid})
                n += 1
        return n

    # -- persistencia -------------------------------------------------------------
    def _journal(self, ev: dict) -> None:
        if not self._jsonl_path:
            return
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            log.exception("[conformal] falha ao journalizar seq=%s", ev.get("seq"))

    def _replay_event(self, ev: dict) -> None:
        kind = ev.get("ev")
        try:
            if kind == "u":
                self._apply_update(float(ev["p"]), int(ev["y"]), str(ev.get("ctx") or "global"))
            elif kind == "pred":
                self._pending[str(ev["id"])] = {
                    "p": float(ev["p"]), "ctx": str(ev.get("ctx") or "global"),
                    "lo": float(ev.get("lo", 0.0)), "hi": float(ev.get("hi", 1.0)),
                    "t": time.time(), "meta": {}}
            elif kind == "res":
                pend = self._pending.pop(str(ev.get("id")), None)
                if pend is not None:
                    self._coverage.append({"t": str(ev.get("t", "")),
                                           "covered": bool(ev.get("covered", False)),
                                           "ctx": pend["ctx"], "p": pend["p"],
                                           "y": int(ev.get("y", 0))})
            elif kind == "exp":
                self._pending.pop(str(ev.get("id")), None)
        except Exception:
            log.exception("[conformal] evento de replay invalido ignorado: %r", ev)
        try:
            self._seq = max(self._seq, int(ev.get("seq", 0)))
        except (TypeError, ValueError):
            pass

    def _load(self) -> None:
        snap_seq = -1
        try:
            if self._snap_path and self._snap_path.exists():
                data = json.loads(self._snap_path.read_text(encoding="utf-8"))
                snap_seq = int(data.get("seq", -1))
                decay = data.get("weight_decay")
                for name, scores in (data.get("pools") or {}).items():
                    pool = _Pool(self.window, decay)
                    for s in list(scores)[-self.window:]:
                        pool.add(float(s))
                    self._pools[str(name)] = pool
                self._seq = snap_seq
                for c in (data.get("coverage") or [])[-1000:]:
                    self._coverage.append(c)
                for k, v in list((data.get("pending") or {}).items())[-self._pending_max:]:
                    self._pending[str(k)] = v
                self._decisions.update(data.get("decisions") or {})
                log.info("[conformal] snapshot carregado: seq=%d pools=%s",
                         snap_seq, {k: p.n() for k, p in self._pools.items()})
        except Exception:
            log.exception("[conformal] snapshot corrompido — recomecando do jsonl")
            snap_seq = -1
            self._pools = {"global": _Pool(self.window, self._decay)}
            self._seq = 0
            self._coverage.clear()
            self._pending.clear()
        try:
            if self._jsonl_path and self._jsonl_path.exists():
                replayed = 0
                with self._jsonl_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        try:
                            seq = int(ev.get("seq", -1))
                        except (TypeError, ValueError):
                            continue
                        if seq <= snap_seq:
                            continue
                        self._replay_event(ev)
                        replayed += 1
                if replayed:
                    log.info("[conformal] %d eventos reprocessados do journal", replayed)
        except Exception:
            log.exception("[conformal] replay do journal falhou (estado parcial)")

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        if not self.state_dir:
            return
        self._updates_since_save = 0
        data = {
            "version": 1, "seq": self._seq, "saved_at": _iso(),
            "alpha": self.alpha, "window": self.window, "weight_decay": self._decay,
            "pools": {k: list(p.scores) for k, p in self._pools.items()},
            "coverage": list(self._coverage),
            "pending": dict(list(self._pending.items())[-self._pending_max:]),
            "decisions": self._decisions,
        }
        try:
            _atomic_write_json(self._snap_path, data)
        except Exception:
            log.exception("[conformal] snapshot falhou")

    def close(self) -> None:
        with self._lock:
            self._save_locked()

    def stats(self) -> dict:
        with self._lock:
            pools = {k: {"n": p.n(), "updates": p.updates} for k, p in self._pools.items()}
            cov = list(self._coverage)[-200:]
            cov_rate = (sum(1 for c in cov if c["covered"]) / len(cov)) if cov else None
            return {
                "alpha": self.alpha, "min_samples": self.min_samples,
                "pools": pools, "pending": len(self._pending),
                "coverage_recente": round(cov_rate, 4) if cov_rate is not None else None,
                "coverage_n": len(cov),
                "decisions": dict(self._decisions),
                "seq": self._seq,
                "uptime_sec": round(time.time() - self._started_at, 1),
            }


# ---------------------------------------------------------------------------
# Resolucao automatica de resultados a partir do feed
# ---------------------------------------------------------------------------
def _fixture_key(view: dict) -> Optional[str]:
    fid = view.get("fixture_id") or view.get("fixtureId") or view.get("match_id")
    if fid:
        return str(fid)
    h, a = view.get("home"), view.get("away")
    if h and a:
        return f"{h}x{a}"
    return None


def _corner_minutes(events: Any) -> List[int]:
    out: List[int] = []
    for e in events or []:
        m = None
        if isinstance(e, dict):
            m = e.get("minute", e.get("m"))
        elif isinstance(e, (list, tuple)) and e:
            m = e[0]
        mi = _to_int(m)
        if mi is not None:
            out.append(mi)
    return out


class OutcomeResolver:
    """Resolve predicoes pendentes a partir das views do feed (formato do bridge).

    Por predicao registrada no minuto M com horizonte H:
      - canto observado em (M, M+H]        -> y=1 (resolve no primeiro canto)
      - minuto atual > M+H sem canto       -> y=0
      - pendencia orfa (fixture sumiu/TTL) -> descartada SEM calibrar

    Idempotente: canto repetido entre frames nao resolve duas vezes
    (a pendencia e removida na primeira resolucao).
    Premissa: corner_events do feed e cumulativo (lista completa da partida).
    """

    def __init__(self, gate: ConformalGate, *, horizon_minutes: int = 10,
                 ttl_minutes: float = 180.0, max_span_minutes: float = 45.0,
                 max_pending: int = 1000):
        self.gate = gate
        self.horizon = int(horizon_minutes)
        self.ttl = float(ttl_minutes) * 60.0
        self.max_span = float(max_span_minutes)
        self.max_pending = int(max_pending)
        self._pending: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self.resolved = 0
        self.expired = 0

    def register(self, pred_id: str, fixture: str, minute: int) -> None:
        with self._lock:
            self._pending[str(pred_id)] = {"fixture": str(fixture),
                                           "minute": int(minute), "ts": time.time()}
            if len(self._pending) > self.max_pending:
                for k in list(self._pending.keys())[:len(self._pending) - self.max_pending]:
                    self._pending.pop(k, None)
                    self.expired += 1

    def observe(self, view: dict) -> List[dict]:
        """Chamar a CADA frame normalizado do feed. Retorna resolucoes ocorridas."""
        out: List[dict] = []
        fixture = _fixture_key(view)
        if not fixture:
            return out
        minute = _to_int(view.get("minute"))
        if minute is None:
            return out
        corner_minutes = _corner_minutes(view.get("corner_events") or view.get("ce") or [])
        now = time.time()
        with self._lock:
            for pred_id, pend in list(self._pending.items()):
                if pend["fixture"] != fixture:
                    continue
                m = pend["minute"]
                if minute < m:
                    continue  # feed voltou no tempo (dado ruim) — ignora
                hit = next((c for c in corner_minutes if m < c <= m + self.horizon), None)
                if hit is not None:
                    cov = self.gate.resolve_prediction(pred_id, 1)
                    self._pending.pop(pred_id, None)
                    self.resolved += 1
                    out.append({"pred_id": pred_id, "y": 1, "corner_minute": hit,
                                "coverage": cov})
                    continue
                if minute > m + self.horizon and (minute - m) <= self.max_span:
                    cov = self.gate.resolve_prediction(pred_id, 0)
                    self._pending.pop(pred_id, None)
                    self.resolved += 1
                    out.append({"pred_id": pred_id, "y": 0, "coverage": cov})
                    continue
                if (now - pend["ts"]) > self.ttl or (minute - m) > self.max_span:
                    self._pending.pop(pred_id, None)
                    self.expired += 1
                    out.append({"pred_id": pred_id, "y": None, "expired": True})
        return out


# ---------------------------------------------------------------------------
# Adaptador: pluga o conformal no pipeline de risk gates existente
# ---------------------------------------------------------------------------
class ConformalRiskGate:
    """Gate FINAL do pipeline de decisao. Compoem: drift + frescor + conformal.

    Regras:
      1. drift >= drift_threshold  -> HOLD (razao: drift_alto)
      2. data_age > max_data_age   -> HOLD (razao: dados_stale)
      3. razoes extras do caller   -> HOLD (razao: extra:<...>)
      4. gate conformal decide ENTER/NO_BET/HOLD pelo intervalo vs threshold
      5. SEMPRE registra a predicao (fixture_id+minute) para calibracao futura

    Contrato: NUNCA levanta excecao; falha interna -> HOLD "internal_error".
    Invariante: advisory-only / paper_trade.
    """

    def __init__(self, gate: ConformalGate, *, drift_threshold: float = 0.6,
                 max_data_age_sec: float = 25.0, horizon_minutes: int = 10,
                 journal_bus: Any = None):
        self.gate = gate
        self.drift_threshold = float(drift_threshold)
        self.max_data_age_sec = float(max_data_age_sec)
        self.resolver = OutcomeResolver(gate, horizon_minutes=horizon_minutes)
        self.journal_bus = journal_bus  # FeedBus opcional: publica cada decisao
        self.evaluations = 0

    def evaluate(self, *, p: float, threshold: float, context: str = "global",
                 drift: float = 0.0, data_age_sec: float = 0.0,
                 fixture_id: Any = None, minute: Any = None,
                 extra_hold_reasons: Any = (), meta: Optional[dict] = None) -> GateDecision:
        try:
            reasons: List[str] = []
            try:
                drift_f = min(1.0, max(0.0, float(drift or 0.0)))
            except (TypeError, ValueError):
                drift_f = 0.0
            if drift_f >= self.drift_threshold:
                reasons.append(f"drift_alto:{drift_f:.2f}")
            try:
                age = float(data_age_sec or 0.0)
            except (TypeError, ValueError):
                age = 0.0
            if age > self.max_data_age_sec:
                reasons.append(f"dados_stale:{age:.0f}s")
            for r in (extra_hold_reasons or ()):
                reasons.append(f"extra:{r}")

            dec = self.gate.gate(p, threshold, context, drift=drift_f)

            if fixture_id is not None and minute is not None:
                m_meta = meta or {}
                fx = _fixture_key({"fixture_id": fixture_id,
                                   "home": m_meta.get("home"),
                                   "away": m_meta.get("away")}) or str(fixture_id)
                mi = _to_int(minute)
                pred_id = f"{fx}|m{mi}|{context}"
                self.gate.record_prediction(pred_id, dec.p, context,
                                            lo=dec.lo, hi=dec.hi, meta=meta)
                if mi is not None:
                    self.resolver.register(pred_id, fx, mi)
                dec.pred_id = pred_id

            if reasons and dec.decision == "ENTER":
                dec.decision = "HOLD"  # bloqueios externos nunca "abrem" entrada
            if reasons:
                dec.reasons = reasons + list(dec.reasons)

            self.evaluations += 1
            if self.journal_bus is not None:
                try:
                    self.journal_bus.publish(dec.to_dict())
                except Exception:
                    log.exception("[ConformalRiskGate] journal da decisao falhou")
            return dec
        except Exception:
            log.exception("[ConformalRiskGate] erro interno -> HOLD por seguranca")
            return GateDecision(decision="HOLD", p=0.0, threshold=0.0, lo=0.0, hi=1.0,
                                alpha=self.gate.alpha, context=str(context), pool="none",
                                n_samples=0, reasons=["internal_error"], ts=_iso())

    def observe_feed(self, view: dict) -> List[dict]:
        """Chamar a cada frame normalizado. Resolve predicoes pendentes."""
        try:
            return self.resolver.observe(view)
        except Exception:
            log.exception("[ConformalRiskGate] observe_feed falhou (frame ignorado)")
            return []


# ---------------------------------------------------------------------------
# Self-test: python engine/core/conformal_gate.py
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import random
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    random.seed(42)
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as td:
        # T1: cold start
        g = ConformalGate(state_dir=None)
        lo, hi = g.interval(0.7, "W1")
        d = g.gate(0.75, 0.60, "W1")
        check("cold start -> intervalo total", (lo, hi) == (0.0, 1.0))
        check("cold start -> HOLD", d.decision == "HOLD" and "cold" in d.reasons[0].lower())

        # T2: cobertura empirica online (dados sinteticos iid)
        g2 = ConformalGate(state_dir=None, alpha=0.10, min_samples=30, window=500)
        covered = 0
        total = 0
        for _ in range(2000):
            p = random.uniform(0.05, 0.95)
            y = 1 if random.random() < p else 0
            lo, hi = g2.interval(p, "global")
            if hi - lo < 1.0:  # conta so quando nao esta frio
                total += 1
                if lo <= y <= hi:
                    covered += 1
            g2.update(p, y, "global")
        cov_rate = covered / max(1, total)
        check("cobertura empirica ~ 1-alpha", 0.84 <= cov_rate <= 0.96,
              f"cobertura={cov_rate:.3f} (n={total})")

        # T3: intervalo deterministico + decisoes exatas
        g4 = ConformalGate(state_dir=None, alpha=0.10, min_samples=30)
        for _ in range(100):
            g4.update(0.9, 1)  # scores todos 0.1 -> q=0.1
        lo, hi = g4.interval(0.75)
        check("intervalo deterministico", abs(lo - 0.65) < 1e-9 and abs(hi - 0.85) < 1e-9,
              f"({lo:.3f},{hi:.3f})")
        check("ENTER quando lo >= thr", g4.gate(0.75, 0.65).decision == "ENTER")
        check("NO_BET quando hi < thr", g4.gate(0.75, 0.90).decision == "NO_BET")
        check("HOLD quando atravessa", g4.gate(0.75, 0.72).decision == "HOLD")

        # T4: drift alarga o intervalo (ENTER -> HOLD)
        g4b = ConformalGate(state_dir=None, alpha=0.10, drift_sensitivity=3.0)
        for _ in range(95):
            g4b.update(0.95, 1)  # score 0.05
        for _ in range(5):
            g4b.update(0.4, 1)   # score 0.6
        d_no = g4b.gate(0.80, 0.72)
        d_yes = g4b.gate(0.80, 0.72, drift=1.0)
        check("drift alarga intervalo (ENTER->HOLD)",
              d_no.decision == "ENTER" and d_yes.decision == "HOLD",
              f"sem drift={d_no.decision} [{d_no.lo:.2f},{d_no.hi:.2f}] | "
              f"com drift={d_yes.decision} [{d_yes.lo:.2f},{d_yes.hi:.2f}]")

        # T5: persistencia round-trip
        sd = Path(td) / "state"
        g5 = ConformalGate(state_dir=sd, alpha=0.10, autosave_every=5)
        for i in range(120):
            g5.update(0.5 + 0.01 * (i % 10), i % 2, "W1")
        g5.record_prediction("FIX1|m82|W1", 0.7, "W1")
        g5.save()
        g5b = ConformalGate(state_dir=sd)
        st5 = g5b.stats()
        check("persistencia: pools restaurados",
              st5["pools"].get("W1", {}).get("n") == 120 and
              st5["pools"].get("global", {}).get("n") == 120)
        check("persistencia: pendencia restaurada",
              g5b.resolve_prediction("FIX1|m82|W1", 1) is not None)

        # T6: OutcomeResolver
        g6 = ConformalGate(state_dir=None)
        r6 = OutcomeResolver(g6, horizon_minutes=10)
        g6.record_prediction("F1|m82", 0.7, "W2")
        r6.register("F1|m82", "F1", 82)
        res = r6.observe({"fixture_id": "F1", "minute": 86,
                          "corner_events": [{"minute": 84, "team": "h"},
                                            {"minute": 90, "team": "a"}]})
        check("resolver: canto no horizonte -> y=1", len(res) == 1 and res[0]["y"] == 1)
        g6.record_prediction("F2|m30", 0.6, "W1")
        r6.register("F2|m30", "F2", 30)
        res2 = r6.observe({"fixture_id": "F2", "minute": 45, "corner_events": []})
        check("resolver: horizonte expirado sem canto -> y=0",
              len(res2) == 1 and res2[0]["y"] == 0)

        # T7: adaptador — bloqueios externos forcam HOLD
        g7 = ConformalGate(state_dir=None)
        for _ in range(100):
            g7.update(0.9, 1)
        rg = ConformalRiskGate(g7, drift_threshold=0.6, max_data_age_sec=25.0)
        d_ok = rg.evaluate(p=0.75, threshold=0.65, context="W1", drift=0.0, data_age_sec=2)
        d_drift = rg.evaluate(p=0.75, threshold=0.65, context="W1", drift=0.9, data_age_sec=2)
        d_stale = rg.evaluate(p=0.75, threshold=0.65, context="W1", drift=0.0, data_age_sec=120)
        check("adaptador: ENTER em condicoes ok", d_ok.decision == "ENTER")
        check("adaptador: drift alto -> HOLD",
              d_drift.decision == "HOLD" and any("drift" in r for r in d_drift.reasons))
        check("adaptador: dados stale -> HOLD", d_stale.decision == "HOLD")
        check("adaptador: invariante paper_trade", d_ok.paper_trade is True)

        # T8: determinismo do quantile
        g8 = ConformalGate(state_dir=None)
        for _ in range(200):
            v = random.random()
            g8.update(v, 1 if v > 0.5 else 0)
        q1 = g8._pools["global"].quantile(0.1)
        q2 = g8._pools["global"].quantile(0.1)
        check("quantile deterministico (cache)", q1 == q2)

    print(f"\nconformal_gate selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
