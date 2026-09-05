#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — MCGrid: grade Monte Carlo pre-computada + interpolacao O(1).

Local: engine/core/mc_grid.py
Dependencias: NENHUMA (stdlib). Python 3.9+. Windows OK.

Problema que resolve:
  Rodar Monte Carlo sob demanda no hot path gasta CPU/GPU com consultas
  repetidas do mesmo estado. Este modulo:

  1. PRE-COMPUTA, em background, uma grade 4D sobre o espaco de estado:
       (minute, lam, gap, pressure) x horizontes [5, 10, 15] min
     Cada celula = N simulacoes de um processo de cantos com clustering
     (Poisson nao-homogeneo + auto-excitacao exponencial, Hawkes-like).
  2. NO HOT PATH, consulta por interpolacao multilineal: ~10-30 microssegundos,
     zero GPU, zero alocacao pesada.
  3. Celulas parcialmente construidas sao interpoladas com pesos por n_sims;
     regiao fria -> retorna None e o caller usa o caminho lento (digital twin).

Arquitetura (importante):
  - Grade = g(minute, lam, gap, pressure) — fixa dado o SIMULADOR.
  - EffectiveRateModel = stats_do_feed -> (lam, pressure, gap) — atualizavel
    SEM rebuild da grade (lam e um input da grade, nao um coeficiente dela).
  - Pressao NAO entra no lam (evita dupla contagem): a grade tem eixo proprio
    `pressure` que multiplica lam por 0.8-1.2 dentro da simulacao.
  - Signature SHA-256 de (eixos, horizontes, dt, params do simulador, curva):
    grade salva no disco e descartada automaticamente se a fisica mudar.

Ciclo de vida:
  MC = MCGridService(state_dir=..., n_sims=400)
  MC.start_build_async()                 # thread daemon, checkpoint periodico
  res = MC.evaluate(feed_view)           # O(1); None enquanto frio
  if res: p = res.p1[10]                 # P(>=1 canto em 10 min)
  MC.close()                             # abort + save final

Invariante: advisory-only / paper_trade. Este modulo apenas ESTIMA
probabilidades; decisao fica a cargo do risk gate (ConformalRiskGate).
"""
from __future__ import annotations

import atexit
import bisect
import collections
import gzip
import hashlib
import json
import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger("aura.mcgrid")

__version__ = "1.0.0"
__all__ = [
    "MinuteRateCurve", "EffectiveRateModel", "CornerSimulator",
    "MCGrid", "MCGridBuilder", "MCGridService", "MCResult", "StatePoint",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc)
    return dt.isoformat(timespec="seconds")


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _stable_signature(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Curva de taxa de cantos por minuto do jogo (combinada, ambos os times)
# ---------------------------------------------------------------------------
_DEFAULT_CURVE_POINTS: List[Tuple[float, float]] = [
    (0.0, 0.075), (10.0, 0.082), (20.0, 0.088), (30.0, 0.095),
    (40.0, 0.104), (45.0, 0.110), (50.0, 0.090), (60.0, 0.098),
    (70.0, 0.108), (80.0, 0.122), (90.0, 0.140), (100.0, 0.150),
    (120.0, 0.150),
]


class MinuteRateCurve:
    """Taxa de cantos (combinada) por minuto de jogo, interpolacao linear.

    Valores default = prior sensato editavel. Recalibre com `fit_from_events`
    usando os corner_events acumulados pelo bridge (dado real do seu sistema).
    """

    def __init__(self, points: Optional[Sequence[Tuple[float, float]]] = None):
        pts = list(points) if points else list(_DEFAULT_CURVE_POINTS)
        if len(pts) < 2:
            raise ValueError("curva precisa de >= 2 pontos")
        self.points = sorted((float(m), max(0.0, float(r))) for m, r in pts)
        self._mean_cache: Dict[float, float] = {}

    def rate(self, minute: float) -> float:
        pts = self.points
        m = float(minute)
        if m <= pts[0][0]:
            return pts[0][1]
        if m >= pts[-1][0]:
            return pts[-1][1]
        j = bisect.bisect_right(pts, (m, float("inf"))) - 1
        if j < 0:
            j = 0
        if j > len(pts) - 2:
            j = len(pts) - 2
        m0, r0 = pts[j]
        m1, r1 = pts[j + 1]
        if m1 <= m0:
            return r1
        f = (m - m0) / (m1 - m0)
        return r0 + (r1 - r0) * f

    def mean_rate(self, minutes: float = 90.0) -> float:
        """Media trapezoidal da taxa em [0, minutes] (referencia da grade)."""
        key = float(minutes)
        if key in self._mean_cache:
            return self._mean_cache[key]
        xs = [0.0] + [m for m, _ in self.points if 0.0 < m < key] + [key]
        total = 0.0
        for a, b in zip(xs, xs[1:]):
            if b <= a:
                continue
            total += 0.5 * (self.rate(a) + self.rate(b)) * (b - a)
        v = total / key if key > 0 else 0.0
        self._mean_cache[key] = v
        return v

    @classmethod
    def fit_from_events(cls, corner_minutes: Sequence[float], n_matches: int,
                        *, bucket: float = 10.0, prior_strength: float = 2.0,
                        base: Optional["MinuteRateCurve"] = None) -> "MinuteRateCurve":
        """Ajusta a curva com dados reais (minutos de canto de N partidas).

        Shrinkage: prior = curva default como se fossem `prior_strength`
        partidas ficticias por bucket. Buckets sem dado derivam para o prior.
        """
        base = base or cls()
        if n_matches <= 0 or not corner_minutes:
            return cls(list(base.points))
        cnt = collections.Counter(int(m // bucket) for m in corner_minutes)
        pts: List[Tuple[float, float]] = []
        n_buckets = int(math.ceil(120.0 / bucket))
        for b in range(n_buckets):
            mid = b * bucket + bucket / 2.0
            emp = cnt.get(b, 0) / (n_matches * bucket)
            pri = base.rate(mid)
            w = n_matches / (n_matches + prior_strength)
            pts.append((mid, w * emp + (1.0 - w) * pri))
        return cls(pts)

    def to_dict(self) -> dict:
        return {"points": [[m, r] for m, r in self.points]}

    @classmethod
    def from_dict(cls, data: dict) -> "MinuteRateCurve":
        return cls([(float(m), float(r)) for m, r in data.get("points", [])])


# ---------------------------------------------------------------------------
# Estado efetivo derivado do feed
# ---------------------------------------------------------------------------
@dataclass
class StatePoint:
    minute: float
    lam: float        # taxa MEDIA de referencia do jogo (cantos/min combinados)
    gap: float        # minutos desde o ultimo canto
    pressure: float   # 0..1 (indice de pressao normalizado)

    def to_dict(self) -> dict:
        return {"minute": round(self.minute, 2), "lam": round(self.lam, 5),
                "gap": round(self.gap, 2), "pressure": round(self.pressure, 3)}


class EffectiveRateModel:
    """Mapeia a view do bridge -> StatePoint. Barato, deterministico, sem estado.

    Contrato (evita dupla contagem):
      - lam  = taxa MEDIA do jogo (shrinkage bayesiano vs prior), SEM pressao.
      - pressure = indice [0,1] de ataques perigosos por minuto vs esperado.
      - gap = minutos desde o ultimo canto (ou desde o inicio se nao houve).

    A curva por minuto NAO e aplicada aqui — a simulacao aplica adiante.
    """

    def __init__(self, curve: Optional[MinuteRateCurve] = None,
                 params: Optional[dict] = None):
        self.curve = curve or MinuteRateCurve()
        p = {
            "prior_corners": 3.5,        # pseudo-contagem de cantos do prior
            "prior_minutes": 35.0,       # pseudo-minutos do prior (=> 0.10/min)
            "expected_dang_per_min": 0.55,  # dangerous attacks combinados/min
            "lam_clamp": (0.02, 0.35),
        }
        if params:
            p.update(params)
        self.params = p

    def from_view(self, view: dict) -> StatePoint:
        minute = _to_float(view.get("minute")) or 0.0
        ch = _to_float(view.get("corners_home")) or 0.0
        ca = _to_float(view.get("corners_away")) or 0.0
        total = ch + ca
        mef = max(minute, 1.0)
        P = self.params
        shrunk = (total + P["prior_corners"]) / (mef + P["prior_minutes"])
        lam = _clamp(shrunk, P["lam_clamp"][0], P["lam_clamp"][1])

        dh = _to_float(view.get("dangerous_home"))
        da = _to_float(view.get("dangerous_away"))
        if dh is None and da is None:
            pressure = 0.5
        else:
            dang = (dh or 0.0) + (da or 0.0)
            z = (dang / mef) / P["expected_dang_per_min"] - 1.0
            pressure = _clamp(0.5 + 0.5 * z, 0.0, 1.0)

        gap = self._gap_from_view(view, minute)
        return StatePoint(minute=minute, lam=lam, gap=gap, pressure=pressure)

    def _gap_from_view(self, view: dict, minute: float) -> float:
        events = view.get("corner_events") or view.get("ce") or []
        last: Optional[float] = None
        for e in events:
            m: Any = None
            if isinstance(e, dict):
                m = e.get("minute", e.get("m"))
            elif isinstance(e, (list, tuple)) and e:
                m = e[0]
            mi = _to_float(m)
            if mi is not None and (last is None or mi > last):
                last = mi
        if last is None:
            return max(0.0, minute)  # sem canto no jogo: boost residual ~ 0
        return max(0.0, minute - last)


# ---------------------------------------------------------------------------
# Simulador embutido (substituivel pelo digital twin do V25)
# ---------------------------------------------------------------------------
class CornerSimulator:
    """Processo de cantos: Poisson nao-homogeneo + auto-excitacao exponencial.

    Fisica por passo dt:
      lam(t) = lam * press_factor * (curva(minute+t)/curva_ref) + boost
      P(canto no passo) = 1 - exp(-lam*dt)      [exato p/ Poisson piecewise-cte]
      boost += alpha a cada canto; boost *= exp(-dt/tau) por passo
      boost inicial = alpha * exp(-gap/tau)     [clustering do ultimo canto]

    Aproximacao declarada: maximo 1 canto por passo (dt=0.5 min). Impacto em
    P(>=1): nulo. Impacto em mean/P(>=2): <0.5% para taxas tipicas.

    Contrato p/ simulador externo (plugar o digital twin do V25):
      callable(minute, lam, gap, pressure, n_sims, seed) ->
          {"n": int, "p1": [float]*H, "p2": [float]*H, "mean": [float]*H}
      com H = len(horizontes), ordenado como self.horizons.
    """

    def __init__(self, curve: MinuteRateCurve, *,
                 horizons: Sequence[float] = (5.0, 10.0, 15.0),
                 dt: float = 0.5, alpha: float = 0.06, tau: float = 3.0):
        pairs = sorted((float(h), h) for h in {float(h) for h in horizons})
        if not pairs or pairs[0][0] <= 0.0:
            raise ValueError("horizontes devem ser > 0")
        self.dt = float(dt)
        if self.dt <= 0:
            raise ValueError("dt deve ser > 0")
        hs: List[int] = []
        hor: List[float] = []
        for hf, _ in pairs:
            r = hf / self.dt
            ri = int(round(r))
            if abs(r - ri) > 1e-6 or ri < 1:
                raise ValueError(f"horizonte {hf} nao e multiplo de dt={dt}")
            hs.append(ri)
            hor.append(hf)
        self.horizons = tuple(hor)
        self._h_steps = hs
        self._n_steps = max(hs)
        self.alpha = float(alpha)
        self.tau = float(tau)
        self.curve = curve
        self.curve_ref = curve.mean_rate(90.0) or 0.1

    def params(self) -> dict:
        return {"alpha": self.alpha, "tau": self.tau, "dt": self.dt,
                "horizons": list(self.horizons)}

    def simulate_cell(self, minute: float, lam: float, gap: float,
                      pressure: float, n_sims: int, seed: int) -> dict:
        n_sims = int(n_sims)
        H = len(self.horizons)
        if n_sims <= 0:
            return {"n": 0, "p1": [0.0] * H, "p2": [0.0] * H, "mean": [0.0] * H}
        rng = random.Random(seed)
        rnd = rng.random
        expm1 = math.expm1
        exp = math.exp
        dt = self.dt
        curve_rate = self.curve.rate
        cref = self.curve_ref
        press_factor = 0.8 + 0.4 * _clamp(float(pressure), 0.0, 1.0)
        n_steps = self._n_steps
        h_steps = self._h_steps
        m0 = float(minute)
        lam0 = max(0.0, float(lam))
        env = [lam0 * press_factor * (curve_rate(m0 + i * dt) / cref)
               for i in range(n_steps)]
        decay = exp(-dt / self.tau)
        alpha = self.alpha
        boost0 = alpha * exp(-max(0.0, float(gap)) / self.tau)
        c1 = [0] * H
        c2 = [0] * H
        sm = [0] * H
        for _ in range(n_sims):
            boost = boost0
            first = -1
            second = -1
            n = 0
            hi = 0
            for i in range(n_steps):
                lam_i = env[i] + boost
                if lam_i > 0.0 and rnd() < -expm1(-lam_i * dt):
                    n += 1
                    boost += alpha
                    if first < 0:
                        first = i
                    elif second < 0:
                        second = i
                boost *= decay
                while hi < H and (i + 1) >= h_steps[hi]:
                    sm[hi] += n
                    hi += 1
            for j in range(H):
                hs = h_steps[j]
                if 0 <= first < hs:
                    c1[j] += 1
                if 0 <= second < hs:
                    c2[j] += 1
        inv = 1.0 / n_sims
        return {"n": n_sims,
                "p1": [x * inv for x in c1],
                "p2": [x * inv for x in c2],
                "mean": [x * inv for x in sm]}


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
@dataclass
class MCResult:
    p1: Dict[int, float]       # P(>=1 canto) por horizonte (min)
    p2: Dict[int, float]       # P(>=2 cantos) por horizonte
    mean: Dict[int, float]     # E[cantos] por horizonte
    mc_se: float               # erro-padrao MC combinado (dominante p1)
    n_sims_eff: float          # n_sims efetivo ponderado
    coverage: float            # fracao do peso bilinear com dados [0..1]
    clamped: List[str]         # dims clampadas nas bordas dos eixos
    elapsed_us: int
    source: str = "grid"

    def to_dict(self) -> dict:
        return {"p1": self.p1, "p2": self.p2, "mean": self.mean,
                "mc_se": round(self.mc_se, 5),
                "n_sims_eff": round(self.n_sims_eff, 1),
                "coverage": round(self.coverage, 3),
                "clamped": self.clamped, "elapsed_us": self.elapsed_us,
                "source": self.source}


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------
AXES_ORDER = ("minute", "lam", "gap", "pressure")
_GRID_FORMAT = "aura-mc-grid-1"


class MCGrid:
    """Grade 4D com interpolação multilineal ponderada por n_sims.

    Layout flat row-major: idx = ((mi*L + li)*G + gi)*P + pi.
    Célula = [n, p1*H, p2*H, mean*H]  (1 + 3H floats).

    Thread-safety (CPython): escrita = atribuicao de item de lista (atomica);
    leitura do lookup nao usa lock — consistente por celula. Lock apenas para
    save/contadores.
    """

    def __init__(self, axes: Dict[str, List[float]], horizons: Sequence[float],
                 dt: float, sim_params: dict, curve_points: List[List[float]],
                 cells: Optional[List[Optional[List[float]]]] = None):
        for name in AXES_ORDER:
            ax = axes.get(name)
            if not ax or len(ax) < 2:
                raise ValueError(f"eixo {name} precisa de >= 2 pontos")
            if any(b <= a for a, b in zip(ax, ax[1:])):
                raise ValueError(f"eixo {name} deve ser estritamente crescente")
        self.axes = {name: [float(x) for x in axes[name]] for name in AXES_ORDER}
        self.horizons = [float(h) for h in horizons]
        self.dt = float(dt)
        self.sim_params = dict(sim_params)
        self.curve_points = [[float(m), float(r)] for m, r in curve_points]
        self.signature = _stable_signature({
            "axes": self.axes, "horizons": self.horizons, "dt": self.dt,
            "sim": self.sim_params, "curve": self.curve_points,
        })
        nM, nL, nG, nP = (len(self.axes[k]) for k in AXES_ORDER)
        self.shape = (nM, nL, nG, nP)
        self._s_m = nL * nG * nP
        self._s_l = nG * nP
        self._s_g = nP
        total = nM * nL * nG * nP
        if cells is not None:
            if len(cells) != total:
                raise ValueError("cells com tamanho inconsistente")
            self.cells: List[Optional[List[float]]] = list(cells)
        else:
            self.cells = [None] * total
        self._lock = threading.Lock()
        self._done = sum(1 for c in self.cells if c and c[0] > 0)

    # -- indexacao ----------------------------------------------------------
    def flat(self, mi: int, li: int, gi: int, pi: int) -> int:
        return mi * self._s_m + li * self._s_l + gi * self._s_g + pi

    def cell(self, mi: int, li: int, gi: int, pi: int) -> Optional[List[float]]:
        return self.cells[self.flat(mi, li, gi, pi)]

    def set_cell(self, idx: int, stats: dict, *, merge: bool = True) -> None:
        n = int(stats.get("n", 0))
        H = len(self.horizons)
        if n <= 0:
            return
        vals = ([float(x) for x in stats["p1"]] +
                [float(x) for x in stats["p2"]] +
                [float(x) for x in stats["mean"]])
        if len(vals) != 3 * H:
            raise ValueError("stats com horizontes inconsistentes")
        old = self.cells[idx]
        if old is None or old[0] <= 0 or not merge:
            new = [float(n)] + vals
            if old is None or old[0] <= 0:
                with self._lock:
                    self._done += 1
            self.cells[idx] = new
        else:
            n1, n2 = old[0], n
            nt = n1 + n2
            merged = [float(nt)]
            for c in range(3 * H):
                merged.append((old[1 + c] * n1 + vals[c] * n2) / nt)
            self.cells[idx] = merged

    # -- lookup ---------------------------------------------------------------
    def lookup(self, minute: float, lam: float, gap: float, pressure: float,
               *, min_coverage: float = 1.0) -> Optional[MCResult]:
        t0 = time.perf_counter()
        clamped: List[str] = []
        i0, fx = self._axis_pos("minute", minute, clamped)
        j0, fy = self._axis_pos("lam", lam, clamped)
        k0, fz = self._axis_pos("gap", gap, clamped)
        l0, fw = self._axis_pos("pressure", pressure, clamped)
        H = len(self.horizons)
        acc1 = [0.0] * H
        acc2 = [0.0] * H
        accm = [0.0] * H
        wsum = 0.0
        wdata = 0.0
        n_eff = 0.0
        se_acc = 0.0
        cells = self.cells
        for a, wa in ((i0, 1.0 - fx), (i0 + 1, fx)):
            if wa <= 0.0:
                continue
            for b, wb in ((j0, 1.0 - fy), (j0 + 1, fy)):
                if wb <= 0.0:
                    continue
                for c, wc in ((k0, 1.0 - fz), (k0 + 1, fz)):
                    if wc <= 0.0:
                        continue
                    for d, wd in ((l0, 1.0 - fw), (l0 + 1, fw)):
                        if wd <= 0.0:
                            continue
                        w = wa * wb * wc * wd
                        cell = cells[a * self._s_m + b * self._s_l +
                                     c * self._s_g + d]
                        wsum += w
                        if cell is None or cell[0] <= 0:
                            continue
                        wn = w * cell[0]
                        wdata += w
                        n_eff += wn
                        for h in range(H):
                            pv = cell[1 + h]
                            acc1[h] += wn * pv
                            acc2[h] += wn * cell[1 + H + h]
                            accm[h] += wn * cell[1 + 2 * H + h]
                            se_acc += wn * math.sqrt(max(pv * (1.0 - pv), 0.0)
                                                     / cell[0])
        if wsum <= 0.0 or n_eff <= 0.0 or (wdata / wsum) < min_coverage:
            return None
        inv = 1.0 / n_eff
        p1 = {int(self.horizons[h]): acc1[h] * inv for h in range(H)}
        p2 = {int(self.horizons[h]): acc2[h] * inv for h in range(H)}
        mean = {int(self.horizons[h]): accm[h] * inv for h in range(H)}
        return MCResult(
            p1=p1, p2=p2, mean=mean, mc_se=se_acc * inv, n_sims_eff=n_eff * inv,
            coverage=wdata / wsum, clamped=clamped,
            elapsed_us=int((time.perf_counter() - t0) * 1e6))

    def _axis_pos(self, name: str, x: float,
                  clamped: List[str]) -> Tuple[int, float]:
        ax = self.axes[name]
        if x <= ax[0]:
            if x < ax[0] - 1e-9:
                clamped.append(name)
            return 0, 0.0
        if x >= ax[-1]:
            if x > ax[-1] + 1e-9:
                clamped.append(name)
            return len(ax) - 2, 1.0
        j = bisect.bisect_right(ax, x) - 1
        if j > len(ax) - 2:
            j = len(ax) - 2
        if j < 0:
            j = 0
        span = ax[j + 1] - ax[j]
        f = (x - ax[j]) / span if span > 0 else 0.0
        return j, _clamp(f, 0.0, 1.0)

    # -- persistencia -----------------------------------------------------------
    def stats(self) -> dict:
        with self._lock:
            done = self._done
        total = len(self.cells)
        return {"shape": list(self.shape), "cells_total": total,
                "cells_done": done, "pct": round(100.0 * done / max(1, total), 1),
                "signature": self.signature,
                "horizons": list(self.horizons)}

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        with self._lock:
            snapshot = list(self.cells)
        payload = {
            "format": _GRID_FORMAT, "signature": self.signature,
            "axes": self.axes, "horizons": self.horizons, "dt": self.dt,
            "sim_params": self.sim_params, "curve_points": self.curve_points,
            "created": _iso(),
            "cells": [[round(x, 6) for x in c] if c else None for c in snapshot],
        }
        try:
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
            os.replace(str(tmp), str(p))
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: Path) -> "MCGrid":
        p = Path(path)
        opener = gzip.open if p.suffix == ".gz" else open
        with opener(p, "rt", encoding="utf-8") as f:  # type: ignore[operator]
            data = json.load(f)
        if data.get("format") != _GRID_FORMAT:
            raise ValueError("formato de grade desconhecido")
        grid = cls(
            axes=data["axes"], horizons=data["horizons"], dt=data["dt"],
            sim_params=data["sim_params"], curve_points=data["curve_points"],
            cells=data.get("cells"))
        return grid


# ---------------------------------------------------------------------------
# Builder (background, prioridade W1/W2, checkpoint, deterministico)
# ---------------------------------------------------------------------------
def _default_priority(minute: float) -> bool:
    return 28.0 <= minute <= 50.0 or 78.0 <= minute <= 108.0


class MCGridBuilder:
    """Construcao incremental da grade em thread propria.

    Determinismo: seed da celula = f(seed_base, idx) — independente da ordem,
    do checkpoint e de quantas vezes retomou.
    Refino: rodar de novo com n_sims maior e min_n_sims=novo valor — células
    com n < min_n_sims recebem sims extras e sao MERGADAS (media ponderada).
    """

    def __init__(self, grid: MCGrid, simulator: Callable[..., dict], *,
                 n_sims: int = 400, seed_base: int = 987654321,
                 checkpoint_every: int = 2000, save_path: Optional[Path] = None,
                 chunk: int = 64,
                 is_priority: Callable[[float], bool] = _default_priority):
        self.grid = grid
        self.simulator = simulator
        self.n_sims = int(n_sims)
        self.min_n_sims = int(n_sims)
        self.seed_base = int(seed_base)
        self.checkpoint_every = int(checkpoint_every)
        self.save_path = Path(save_path) if save_path else None
        self.chunk = int(chunk)
        self._is_priority = is_priority
        self._order = self._compute_order()
        self._pos = 0
        self._built = 0
        self._skipped = 0
        self._thread: Optional[threading.Thread] = None
        self._abort = threading.Event()
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._finished_at: Optional[float] = None
        self._since_checkpoint = 0

    def _compute_order(self) -> List[int]:
        g = self.grid
        nM, nL, nG, nP = g.shape
        m_ax = g.axes["minute"]
        pri = [i for i, m in enumerate(m_ax) if self._is_priority(m)]
        rest = [i for i in range(nM) if i not in set(pri)]
        order: List[int] = []
        for mi in pri + rest:
            for li in range(nL):
                for gi in range(nG):
                    for pi in range(nP):
                        order.append(g.flat(mi, li, gi, pi))
        self._n_priority = len(pri) * nL * nG * nP
        return order

    def _cell_seed(self, idx: int) -> int:
        return (self.seed_base + idx * 2654435761) % (2 ** 32)

    def build_some(self, k: int) -> int:
        """Constroi ate k celulas pendentes. Retorna qtas foram simuladas."""
        g = self.grid
        m_ax, l_ax, gp_ax, pr_ax = (g.axes[n] for n in AXES_ORDER)
        nM, nL, nG, nP = g.shape
        built = 0
        with self._lock:
            start = self._pos
        order = self._order
        i = start
        while i < len(order) and built < k and not self._abort.is_set():
            idx = order[i]
            cell = g.cells[idx]
            if cell is not None and cell[0] >= self.min_n_sims:
                with self._lock:
                    self._skipped += 1
                i += 1
                continue
            mi = idx // g._s_m
            rem = idx % g._s_m
            li = rem // g._s_l
            rem = rem % g._s_l
            gi = rem // g._s_g
            pi = rem % g._s_g
            stats = self.simulator(m_ax[mi], l_ax[li], gp_ax[gi], pr_ax[pi],
                                   self.n_sims, self._cell_seed(idx))
            g.set_cell(idx, stats, merge=True)
            built += 1
            i += 1
            with self._lock:
                self._built += 1
                self._since_checkpoint += 1
                need_ckpt = self._since_checkpoint >= self.checkpoint_every
                self._since_checkpoint = 0 if need_ckpt else self._since_checkpoint
            if need_ckpt and self.save_path is not None:
                try:
                    g.save(self.save_path)
                except Exception:
                    log.exception("[mcgrid] checkpoint falhou (build continua)")
        with self._lock:
            self._pos = i
        return built

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._abort.clear()
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._run,
                                        name="mcgrid-builder", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        total = len(self._order)
        log.info("[mcgrid] build iniciado: %d celulas, n_sims=%d",
                 total, self.n_sims)
        while not self._abort.is_set():
            built = self.build_some(self.chunk)
            with self._lock:
                pos = self._pos
            if pos >= total:
                break
            if built == 0:
                break
        self._finished_at = time.time()
        if self.save_path is not None and not self._abort.is_set():
            try:
                self.grid.save(self.save_path)
                log.info("[mcgrid] build concluido e salvo: %s", self.save_path)
            except Exception:
                log.exception("[mcgrid] save final falhou")
        elif self._abort.is_set():
            log.info("[mcgrid] build abortado pelo operator")

    def abort(self, timeout: float = 5.0) -> None:
        self._abort.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def status(self) -> dict:
        with self._lock:
            pos, built, skipped = self._pos, self._built, self._skipped
        total = len(self._order)
        pri_pending = max(0, self._n_priority - min(pos, self._n_priority))
        st: Dict[str, Any] = {
            "cells_total": total, "cursor": pos, "built": built,
            "skipped": skipped, "pct": round(100.0 * pos / max(1, total), 1),
            "priority_pending": pri_pending, "n_sims": self.n_sims,
            "building": self._thread is not None and self._thread.is_alive(),
        }
        if self._started_at and pos > 0 and self._finished_at is None:
            rate = pos / max(1e-9, time.time() - self._started_at)
            st["eta_sec"] = round((total - pos) / max(rate, 1e-9), 0)
        return st


# ---------------------------------------------------------------------------
# Service (fachada)
# ---------------------------------------------------------------------------
def _default_axes() -> Dict[str, List[float]]:
    return {
        "minute": [25.0 + 3.5 * i for i in range(24)],          # 25 .. 103.5
        "lam": [0.02 + (0.35 - 0.02) * i / 23.0 for i in range(24)],
        "gap": [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 11.0, 15.0],
        "pressure": [0.0, 0.25, 0.5, 0.75, 1.0],
    }


class MCGridService:
    """Fachada: load/build da grade + evaluate(feed_view) em O(1).

    - state_dir/mcgrid.json.gz: grade persistida (checkpoint + retomada).
    - Signature mismatch (fisica mudou) -> grade descartada e rebuild.
    - evaluate() retorna None enquanto a regiao consultada esta fria:
      o caller DEVE ter fallback (digital twin existente do V25).
    - simulator custom: plugar o digital twin com o contrato documentado
      na docstring do CornerSimulator.
    """

    def __init__(self, state_dir=None, *, n_sims: int = 400,
                 horizons: Sequence[float] = (5.0, 10.0, 15.0),
                 dt: float = 0.5, alpha: float = 0.06, tau: float = 3.0,
                 curve: Optional[MinuteRateCurve] = None,
                 axes_config: Optional[Dict[str, List[float]]] = None,
                 simulator: Optional[Callable[..., dict]] = None,
                 model: Optional[EffectiveRateModel] = None,
                 min_coverage: float = 0.75, autosave_every: int = 2000):
        self.state_dir = Path(state_dir) if state_dir else None
        self.n_sims = int(n_sims)
        self.min_coverage = float(min_coverage)
        self.curve = curve or MinuteRateCurve()
        self.model = model or EffectiveRateModel(curve=self.curve)
        self.simulator = simulator or CornerSimulator(
            self.curve, horizons=horizons, dt=dt, alpha=alpha, tau=tau)
        if hasattr(self.simulator, "params"):
            sim_params = self.simulator.params()
        else:
            sim_params = {"custom": str(self.simulator)}
        self._grid_path = (self.state_dir / "mcgrid.json.gz"
                           if self.state_dir else None)
        self.grid: MCGrid = self._load_or_create(axes_config, sim_params)
        self.builder: Optional[MCGridBuilder] = None
        if self.state_dir is not None:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        atexit.register(self._atexit_close)

    # -- setup ----------------------------------------------------------------
    def _load_or_create(self, axes_config, sim_params) -> MCGrid:
        if self._grid_path is not None and self._grid_path.exists():
            try:
                grid = MCGrid.load(self._grid_path)
                if grid.signature == _stable_signature({
                        "axes": grid.axes, "horizons": grid.horizons,
                        "dt": grid.dt, "sim": grid.sim_params,
                        "curve": grid.curve_points}):
                    log.info("[mcgrid] grade carregada: %s", grid.stats())
                    return grid
                log.warning("[mcgrid] signature divergente (fisica mudou) "
                            "— grade descartada, rebuild necessario")
            except Exception:
                log.exception("[mcgrid] carga falhou — rebuild do zero")
        axes = axes_config or _default_axes()
        horizons = list(getattr(self.simulator, "horizons", (5.0, 10.0, 15.0)))
        return MCGrid.create(axes=axes, horizons=horizons,
                             dt=sim_params.get("dt", 0.5),
                             sim_params=sim_params,
                             curve_points=self.curve.points)

    def start_build_async(self) -> None:
        if self.builder is not None and self.builder.status()["building"]:
            return
        if self._grid_path is None:
            log.warning("[mcgrid] sem state_dir — build sem checkpoint")
        # Aceita CornerSimulator (metodo) ou callable no contrato documentado
        sim = self.simulator
        if hasattr(sim, "simulate_cell") and callable(sim.simulate_cell):
            sim_fn = sim.simulate_cell
        else:
            sim_fn = sim
        self.builder = MCGridBuilder(
            self.grid, sim_fn, n_sims=self.n_sims,
            checkpoint_every=2000, save_path=self._grid_path)
        self.builder.min_n_sims = self.n_sims
        self.builder.start()

    # -- consulta ---------------------------------------------------------------
    def state_point(self, view: dict) -> StatePoint:
        return self.model.from_view(view)

    def lookup(self, minute: float, lam: float, gap: float,
               pressure: float) -> Optional[MCResult]:
        return self.grid.lookup(minute, lam, gap, pressure,
                                min_coverage=self.min_coverage)

    def evaluate(self, view: dict) -> Optional[MCResult]:
        """Feed view (formato do bridge) -> MCResult ou None (regiao fria)."""
        try:
            sp = self.state_point(view)
            return self.lookup(sp.minute, sp.lam, sp.gap, sp.pressure)
        except Exception:
            log.exception("[mcgrid] evaluate falhou — retornando None "
                          "(caller deve usar fallback)")
            return None

    def p_at_least_one(self, view: dict, horizon: int = 10) -> Optional[float]:
        res = self.evaluate(view)
        if res is None:
            return None
        return res.p1.get(int(horizon))

    # -- diagnose ----------------------------------------------------------------
    def status(self) -> dict:
        st = self.grid.stats()
        if self.builder is not None:
            st["builder"] = self.builder.status()
        st["min_coverage"] = self.min_coverage
        return st

    def sanity_check(self) -> dict:
        """Monotonicidade em lam e consistencia p2<=p1<=mean.

        Violacoes de monotonia em lam sao ruido MC: com n_sims=400 espere
        ~0-2%. Acima de ~5%, aumente n_sims e rode refine (rebuild com
        min_n_sims maior).
        """
        g = self.grid
        m_ax, l_ax, gp_ax, pr_ax = (g.axes[n] for n in AXES_ORDER)
        H = len(g.horizons)
        hl = H - 1
        gi = min(range(len(gp_ax)), key=lambda i: abs(gp_ax[i] - 6.0))
        pi = min(range(len(pr_ax)), key=lambda i: abs(pr_ax[i] - 0.5))
        viol_lam = 0
        viol_p2 = 0
        viol_mean = 0
        checked = 0
        done = 0
        for mi in range(len(m_ax)):
            prev: Optional[float] = None
            for li in range(len(l_ax)):
                cell = g.cell(mi, li, gi, pi)
                if cell is None or cell[0] <= 0:
                    continue
                done += 1
                v = cell[1 + hl]
                if prev is not None and v < prev - 1e-9:
                    viol_lam += 1
                prev = v
                for h in range(H):
                    if cell[1 + H + h] > cell[1 + h] + 1e-9:
                        viol_p2 += 1
                    if cell[1 + h] > cell[1 + 2 * H + h] + 1e-9:
                        viol_mean += 1
                checked += 1
        return {"cells_checked": checked, "cells_done": done,
                "viol_lam_monotonic": viol_lam,
                "viol_p2_gt_p1": viol_p2, "viol_p1_gt_mean": viol_mean,
                "note": "viol_lam <=2% = ruido MC ok; >5% = subir n_sims"}

    def close(self) -> None:
        if self.builder is not None:
            self.builder.abort(timeout=3.0)
        if self._grid_path is not None:
            try:
                self.grid.save(self._grid_path)
            except Exception:
                log.exception("[mcgrid] save no close falhou")

    def _atexit_close(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# MCGrid.create classmethod (referenciado pelo service)
def _mcgrid_create(cls, *, axes, horizons, dt, sim_params, curve_points):
    return cls(axes=axes, horizons=horizons, dt=dt, sim_params=sim_params,
               curve_points=curve_points)


MCGrid.create = classmethod(_mcgrid_create)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Self-test: python engine/core/mc_grid.py
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    # ---- T1/T2/T3: interpolacao em grade sintetica linear ----
    axes = {"minute": [30.0, 50.0, 70.0], "lam": [0.05, 0.15, 0.25],
            "gap": [2.0, 8.0], "pressure": [0.25, 0.75]}
    grid = MCGrid.create(axes=axes, horizons=[5.0, 10.0, 15.0], dt=0.5,
                         sim_params={"alpha": 0.06, "tau": 3.0},
                         curve_points=list(_DEFAULT_CURVE_POINTS))

    def f(m, l, g, p):
        return 0.001 * m + 0.5 * l + 0.02 * g + 0.1 * p

    nM, nL, nG, nP = grid.shape
    for mi in range(nM):
        for li in range(nL):
            for gi in range(nG):
                for pi in range(nP):
                    v = f(axes["minute"][mi], axes["lam"][li],
                          axes["gap"][gi], axes["pressure"][pi])
                    grid.cells[grid.flat(mi, li, gi, pi)] = \
                        [1000] + [v] * 9
    r = grid.lookup(41.7, 0.112, 5.5, 0.6)
    expected = f(41.7, 0.112, 5.5, 0.6)
    check("interp multilineal exata (funcao linear)",
          r is not None and abs(r.p1[5] - expected) < 1e-9,
          f"esperado={expected:.6f}" if r else "None")
    r2 = grid.lookup(200.0, 0.112, 5.5, 0.6)  # clamp em minute
    check("clamp nas bordas + flag", r2 is not None and
          "minute" in r2.clamped and abs(r2.p1[5] - f(70.0, 0.112, 5.5, 0.6)) < 1e-9)

    # T3: cobertura parcial (celula do meio de minute sem dados)
    for li in range(nL):
        for gi in range(nG):
            for pi in range(nP):
                grid.cells[grid.flat(1, li, gi, pi)] = None
    r_full_req = grid.lookup(41.7, 0.112, 5.5, 0.6, min_coverage=1.0)
    r_part = grid.lookup(41.7, 0.112, 5.5, 0.6, min_coverage=0.3)
    check("cobertura insuficiente -> None", r_full_req is None)
    ok_part = (r_part is not None and 0.3 < r_part.coverage < 0.6 and
               abs(r_part.p1[5] - f(30.0, 0.112, 5.5, 0.6)) < 1e-9)
    check("interp parcial renormalizada correta", ok_part,
          f"coverage={r_part.coverage:.3f}" if r_part else "None")

    # ---- T4: simulador vs analitico (sem clustering) ----
    flat = MinuteRateCurve([(0.0, 0.1), (130.0, 0.1)])
    sim = CornerSimulator(flat, horizons=(10.0,), dt=0.5, alpha=0.0, tau=3.0)
    lam, press = 0.1, 0.5  # press=0.5 -> fator 1.0; curva flat -> razao 1.0
    st = sim.simulate_cell(80.0, lam, gap=15.0, pressure=press,
                           n_sims=20000, seed=7)
    analytic = 1.0 - math.exp(-lam * 10.0)
    se = math.sqrt(analytic * (1 - analytic) / 20000)
    check("P(>=1) converge p/ 1-exp(-lambda*k)",
          abs(st["p1"][0] - analytic) < 4 * se,
          f"mc={st['p1'][0]:.4f} analitico={analytic:.4f} tol={4 * se:.4f}")

    # T4b: clustering via gap (gap=0 deve aumentar p1)
    sim_c = CornerSimulator(flat, horizons=(10.0,), dt=0.5, alpha=0.06, tau=3.0)
    st_g0 = sim_c.simulate_cell(80.0, 0.1, gap=0.0, pressure=0.5,
                                n_sims=20000, seed=11)
    st_g15 = sim_c.simulate_cell(80.0, 0.1, gap=15.0, pressure=0.5,
                                 n_sims=20000, seed=12)
    check("clustering: gap=0 aumenta P(>=1)",
          st_g0["p1"][0] > st_g15["p1"][0] + 0.02,
          f"gap0={st_g0['p1'][0]:.3f} gap15={st_g15['p1'][0]:.3f}")

    # ---- T5: determinismo por celula ----
    st_a = sim_c.simulate_cell(85.0, 0.12, gap=4.0, pressure=0.7,
                               n_sims=500, seed=999)
    st_b = sim_c.simulate_cell(85.0, 0.12, gap=4.0, pressure=0.7,
                               n_sims=500, seed=999)
    check("simulate_cell deterministico (mesma seed)",
          st_a["p1"] == st_b["p1"] and st_a["mean"] == st_b["mean"])

    # ---- T6: grade mini end-to-end + monotonicidade ----
    mini_axes = {"minute": [30.0, 50.0, 70.0, 85.0, 100.0],
                 "lam": [0.03, 0.12, 0.25, 0.35],
                 "gap": [1.0, 6.0, 12.0], "pressure": [0.0, 0.5, 1.0]}
    mgrid = MCGrid.create(axes=mini_axes, horizons=[5.0, 10.0, 15.0], dt=0.5,
                          sim_params={"alpha": 0.06, "tau": 3.0},
                          curve_points=list(_DEFAULT_CURVE_POINTS))
    msim = CornerSimulator(MinuteRateCurve(list(_DEFAULT_CURVE_POINTS)),
                           horizons=(5.0, 10.0, 15.0), dt=0.5)
    for mi in range(mgrid.shape[0]):
        for li in range(mgrid.shape[1]):
            for gi in range(mgrid.shape[2]):
                for pi in range(mgrid.shape[3]):
                    idx = mgrid.flat(mi, li, gi, pi)
                    stats = msim.simulate_cell(
                        mini_axes["minute"][mi], mini_axes["lam"][li],
                        mini_axes["gap"][gi], mini_axes["pressure"][pi],
                        n_sims=2000, seed=idx + 5)
                    mgrid.set_cell(idx, stats)
    r_lo = mgrid.lookup(85.0, 0.03, 6.0, 0.5)
    r_hi = mgrid.lookup(85.0, 0.35, 6.0, 0.5)
    check("monotonicidade em lam (extremos)",
          r_lo is not None and r_hi is not None and
          r_hi.p1[15] > r_lo.p1[15] + 0.2,
          f"lam_baixo={r_lo.p1[15]:.3f} lam_alto={r_hi.p1[15]:.3f}")
    check("monotonicidade em horizonte (por construcao)",
          r_lo.p1[5] <= r_lo.p1[10] <= r_lo.p1[15])
    check("p2 <= p1 e p1 <= mean",
          r_lo.p2[10] <= r_lo.p1[10] + 1e-9 and
          r_lo.p1[10] <= r_lo.mean[10] + 1e-9)

    # ---- T7: save/load round-trip ----
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "g.json.gz"
        mgrid.save(p)
        g2 = MCGrid.load(p)
        ra = mgrid.lookup(85.0, 0.2, 4.0, 0.6)
        rb = g2.lookup(85.0, 0.2, 4.0, 0.6)
        check("save/load round-trip identico",
              ra is not None and rb is not None and
              abs(ra.p1[10] - rb.p1[10]) < 2e-6 and
              g2.signature == mgrid.signature)

    # ---- T8: build priorizado (W1/W2 primeiro) + regiao fria ----
    b_axes = {"minute": [25.0, 35.0, 45.0, 55.0, 65.0, 75.0, 85.0, 95.0],
              "lam": [0.05, 0.15, 0.25], "gap": [2.0, 8.0],
              "pressure": [0.25, 0.75]}
    bgrid = MCGrid.create(axes=b_axes, horizons=[10.0], dt=0.5,
                          sim_params={"alpha": 0.06, "tau": 3.0},
                          curve_points=list(_DEFAULT_CURVE_POINTS))
    bsim = CornerSimulator(MinuteRateCurve(list(_DEFAULT_CURVE_POINTS)),
                           horizons=(10.0,), dt=0.5)
    builder = MCGridBuilder(bgrid, bsim.simulate_cell, n_sims=30,
                            checkpoint_every=10 ** 9)
    n_priority = builder._n_priority
    total = len(builder._order)
    builder.build_some(n_priority)  # so as prioritarias
    st_w2 = bgrid.lookup(90.0, 0.15, 5.0, 0.5, min_coverage=0.75)
    st_cold = bgrid.lookup(60.0, 0.15, 5.0, 0.5, min_coverage=0.75)
    check("build priorizado: W2 quente",
          st_w2 is not None and st_w2.coverage >= 0.99)
    check("build priorizado: fora das janelas continua frio -> None",
          st_cold is None,
          f"prioritarias={n_priority}/{total}")
    # completa o resto e verifica que esquenta
    builder.build_some(total)
    st_cold2 = bgrid.lookup(60.0, 0.15, 5.0, 0.5, min_coverage=0.75)
    check("build completo: tudo quente", st_cold2 is not None)

    # ---- T9: EffectiveRateModel.from_view ----
    model = EffectiveRateModel()
    view = {"minute": 82, "corners_home": 5, "corners_away": 4,
            "dangerous_home": 30, "dangerous_away": 22,
            "corner_events": [{"minute": 70, "team": "h"},
                              {"minute": 78, "team": "a"}]}
    sp = model.from_view(view)
    lam_exp = (9 + 3.5) / (82 + 35)
    check("from_view: lam com shrinkage",
          abs(sp.lam - lam_exp) < 1e-9, f"lam={sp.lam:.4f}")
    check("from_view: gap do ultimo canto", abs(sp.gap - 4.0) < 1e-9)
    check("from_view: pressure plausivel", 0.4 < sp.pressure < 0.7,
          f"pressure={sp.pressure:.3f}")
    sp2 = model.from_view({"minute": 40, "corners_home": 2, "corners_away": 1})
    check("from_view: sem canto -> gap = minute", abs(sp2.gap - 40.0) < 1e-9)
    check("from_view: sem dangerous -> pressure neutra",
          abs(sp2.pressure - 0.5) < 1e-9)

    # ---- T10: performance do lookup ----
    t0 = time.perf_counter()
    N = 2000
    for i in range(N):
        mgrid.lookup(80.0 + (i % 20) * 0.5, 0.05 + (i % 30) * 0.008,
                     1.0 + (i % 12), 0.1 + (i % 8) * 0.1)
    avg_us = (time.perf_counter() - t0) * 1e6 / N
    check("lookup O(1) rapido", avg_us < 100.0, f"avg={avg_us:.1f} us")

    # ---- T11: service end-to-end com state_dir (load + retomada) ----
    with tempfile.TemporaryDirectory() as td:
        svc = MCGridService(state_dir=Path(td) / "mc", n_sims=25,
                            axes_config={"minute": [30.0, 60.0, 85.0],
                                         "lam": [0.05, 0.20],
                                         "gap": [2.0, 10.0],
                                         "pressure": [0.25, 0.75]})
        svc.start_build_async()
        # build sincrono pequeno para o teste (direto no builder)
        svc.builder.abort(timeout=2.0)
        svc.builder.build_some(len(svc.builder._order))
        res = svc.evaluate(view)
        check("service.evaluate retorna resultado pos-build",
              res is not None and 0.0 <= res.p1[10] <= 1.0,
              f"p1@10={res.p1[10]:.3f}" if res else "None")
        check("service.p_at_least_one consistente",
              svc.p_at_least_one(view, 10) == res.p1[10])
        sc = svc.sanity_check()
        check("sanity_check roda sem violacoes estruturais",
              sc["viol_p2_gt_p1"] == 0 and sc["viol_p1_gt_mean"] == 0)
        svc.close()
        # retomada: nova instancia carrega do disco
        svc2 = MCGridService(state_dir=Path(td) / "mc", n_sims=25,
                             axes_config={"minute": [30.0, 60.0, 85.0],
                                          "lam": [0.05, 0.20],
                                          "gap": [2.0, 10.0],
                                          "pressure": [0.25, 0.75]})
        res2 = svc2.evaluate(view)
        check("retomada do disco: mesmo resultado",
              res2 is not None and abs(res2.p1[10] - res.p1[10]) < 2e-6)
        svc2.close()

    print(f"\nmc_grid selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
