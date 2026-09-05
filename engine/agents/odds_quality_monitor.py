#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Odds Quality Monitor

Monitora a qualidade das odds capturadas (SokkerPRO / tips / feed):
  - Freshness (idade do timestamp)
  - Estabilidade (variação entre ticks)
  - Saltos anômalos (spikes)
  - Spread / linha coerente
  - Compatibilidade de mercado (next_corner vs total — alinhado a market_edge)
  - Score 0–1 e alertas para JARVIS / Telegram / GLM

Invariante: advisory-only. Não aposta.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("aura.odds_quality")

__version__ = "1.0.0"
__all__ = [
    "OddsQualityMonitor",
    "OddsTick",
    "OddsQualityReport",
    "ODDS_MONITOR",
]

# Limites padrão (segundos / razões)
MAX_FRESH_SEC = 30.0
WARN_FRESH_SEC = 15.0
MAX_JUMP_PCT = 0.25          # 25% de salto entre ticks = alerta
MIN_ODDS = 1.01
MAX_ODDS = 100.0
HISTORY_LEN = 64

NEXT_CORNER_ALIASES = (
    "next_corner", "corner_next", "nextcorner", "escanteio_proximo",
    "proximo_escanteio", "corners_live", "escanteios_ao_vivo",
    "corner_5min", "live_corner",
)
TOTAL_ALIASES = (
    "over_9_5", "over_9.5", "under_9_5", "under_9.5", "over_8_5", "over_10_5",
    "match_total", "total_corners", "asian_total", "corners_ou",
    "corners_over", "corners_under",
)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    except (TypeError, ValueError):
        return None


def normalize_market(name: Any) -> str:
    s = str(name or "").strip().lower()
    for a, b in ((" ", "_"), ("-", "_"), ("ç", "c"), ("ã", "a"), ("á", "a"), ("é", "e")):
        s = s.replace(a, b)
    return s


def classify_market(name: Any) -> str:
    n = normalize_market(name)
    if not n:
        return "empty"
    for a in TOTAL_ALIASES:
        if a in n:
            return "total"
    for a in NEXT_CORNER_ALIASES:
        if a in n:
            return "next_corner"
    if "corner" in n or "escante" in n:
        if any(x in n for x in ("total", "over", "under", "linha")):
            return "total"
        return "next_corner"
    if any(x in n for x in ("1x2", "result", "btts", "handicap")):
        return "other"
    return "unknown"


@dataclass
class OddsTick:
    market: str
    selection: str
    price: float
    line: Optional[float] = None
    fixture_id: str = ""
    source: str = ""
    ts: float = field(default_factory=time.time)
    raw: Optional[dict] = None

    def key(self) -> str:
        return f"{self.fixture_id}|{normalize_market(self.market)}|{self.selection}|{self.line}"


@dataclass
class OddsQualityReport:
    score: float                      # 0–1
    grade: str                        # A/B/C/D/F
    flags: List[str]
    n_markets: int
    n_ticks: int
    avg_age_sec: Optional[float]
    max_jump_pct: Optional[float]
    stale_count: int
    spike_count: int
    invalid_count: int
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "grade": self.grade,
            "flags": list(self.flags),
            "n_markets": self.n_markets,
            "n_ticks": self.n_ticks,
            "avg_age_sec": self.avg_age_sec,
            "max_jump_pct": self.max_jump_pct,
            "stale_count": self.stale_count,
            "spike_count": self.spike_count,
            "invalid_count": self.invalid_count,
            "details": dict(self.details),
            "exportedAt": _iso(),
        }


class OddsQualityMonitor:
    """Monitor de qualidade de odds em tempo real.

    Uso:
        mon = OddsQualityMonitor()
        mon.ingest_from_view(BROWSER.extract_view())
        report = mon.evaluate()
        if report.score < 0.5:
            JARVIS.alert(...)
    """

    def __init__(self, *, max_fresh_sec: float = MAX_FRESH_SEC,
                 warn_fresh_sec: float = WARN_FRESH_SEC,
                 max_jump_pct: float = MAX_JUMP_PCT,
                 history_len: int = HISTORY_LEN):
        self.max_fresh_sec = float(max_fresh_sec)
        self.warn_fresh_sec = float(warn_fresh_sec)
        self.max_jump_pct = float(max_jump_pct)
        self.history_len = int(history_len)

        self._hist: Dict[str, Deque[OddsTick]] = {}
        self._lock = threading.Lock()
        self._ingested = 0
        self._reports = 0
        self._last_report: Optional[OddsQualityReport] = None
        self._alerts: Deque[dict] = deque(maxlen=100)

    # ------------------------------------------------------------------ ingest
    def ingest_tick(self, tick: OddsTick) -> None:
        if tick.price is None or not (MIN_ODDS <= tick.price <= MAX_ODDS):
            return
        k = tick.key()
        with self._lock:
            if k not in self._hist:
                self._hist[k] = deque(maxlen=self.history_len)
            self._hist[k].append(tick)
            self._ingested += 1

    def ingest_odds_list(self, odds: List[dict], *, fixture_id: str = "",
                         source: str = "feed") -> int:
        n = 0
        for item in odds or []:
            if not isinstance(item, dict):
                continue
            price = _to_float(
                item.get("price") or item.get("decimalOdds")
                or item.get("odds") or item.get("odd"))
            if price is None:
                continue
            market = str(item.get("market") or item.get("marketType") or "unknown")
            selection = str(
                item.get("selection") or item.get("outcome")
                or item.get("label") or "")
            line = _to_float(item.get("line") or item.get("total") or item.get("handicap"))
            ts = _to_float(item.get("ts") or item.get("timestamp")) or time.time()
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            self.ingest_tick(OddsTick(
                market=market, selection=selection, price=price,
                line=line, fixture_id=str(fixture_id or item.get("fixture_id") or ""),
                source=source, ts=ts, raw=item))
            n += 1
        return n

    def ingest_from_view(self, view: Optional[dict]) -> int:
        """Extrai odds de um frame cornerai-analyst-1."""
        if not view or not isinstance(view, dict):
            return 0
        fid = ""
        fx = view.get("fixture") or {}
        if isinstance(fx, dict):
            fid = str(fx.get("id") or "")
        odds = view.get("odds") or []
        if isinstance(odds, dict):
            # normalizar 1x2 dict etc.
            flat = []
            for k, v in odds.items():
                if isinstance(v, (int, float)):
                    flat.append({"market": "1x2", "selection": k, "price": v})
                elif isinstance(v, dict):
                    for s, p in v.items():
                        flat.append({"market": str(k), "selection": str(s), "price": p})
            odds = flat
        return self.ingest_odds_list(list(odds) if isinstance(odds, list) else [],
                                     fixture_id=fid, source=str(view.get("source") or "view"))

    # ---------------------------------------------------------------- evaluate
    def evaluate(self, *, now: Optional[float] = None,
                 fixture_id: Optional[str] = None) -> OddsQualityReport:
        now = now if now is not None else time.time()
        flags: List[str] = []
        ages: List[float] = []
        jumps: List[float] = []
        stale = spike = invalid = 0
        n_ticks = 0
        market_types: Dict[str, int] = {}
        details: Dict[str, Any] = {"series": {}}

        with self._lock:
            items = list(self._hist.items())

        for key, series in items:
            if fixture_id and not key.startswith(f"{fixture_id}|"):
                continue
            if not series:
                continue
            last = series[-1]
            n_ticks += 1
            mtype = classify_market(last.market)
            market_types[mtype] = market_types.get(mtype, 0) + 1

            # invalid range
            if not (MIN_ODDS <= last.price <= MAX_ODDS):
                invalid += 1
                flags.append(f"invalid_price:{key}")
                continue

            age = max(0.0, now - last.ts)
            ages.append(age)
            if age > self.max_fresh_sec:
                stale += 1
                flags.append(f"stale:{key}:{age:.0f}s")
            elif age > self.warn_fresh_sec:
                flags.append(f"aging:{key}:{age:.0f}s")

            # jump vs previous
            if len(series) >= 2:
                prev = series[-2]
                if prev.price > 0:
                    jump = abs(last.price - prev.price) / prev.price
                    jumps.append(jump)
                    if jump >= self.max_jump_pct:
                        spike += 1
                        flags.append(f"spike:{key}:{jump:.0%}")

            # market class note
            if mtype == "total":
                flags.append(f"market_total:{key}")  # informativo — edge incompatível
            elif mtype == "empty":
                flags.append(f"market_empty:{key}")

            details["series"][key] = {
                "price": last.price,
                "age_sec": round(age, 1),
                "n": len(series),
                "market_class": mtype,
            }

        avg_age = sum(ages) / len(ages) if ages else None
        max_jump = max(jumps) if jumps else None

        # Score composto
        score = 1.0
        if n_ticks == 0:
            score = 0.0
            flags.append("no_odds")
        else:
            # penalidade por stale
            score -= 0.35 * min(1.0, stale / max(1, n_ticks))
            # penalidade por spikes
            score -= 0.25 * min(1.0, spike / max(1, n_ticks))
            # penalidade por inválidos
            score -= 0.30 * min(1.0, invalid / max(1, n_ticks))
            # penalidade por idade média
            if avg_age is not None:
                if avg_age > self.max_fresh_sec:
                    score -= 0.20
                elif avg_age > self.warn_fresh_sec:
                    score -= 0.08
            # bônus leve se tem next_corner fresco
            if market_types.get("next_corner", 0) > 0 and stale == 0:
                score = min(1.0, score + 0.05)
        score = max(0.0, min(1.0, score))

        if score >= 0.85:
            grade = "A"
        elif score >= 0.70:
            grade = "B"
        elif score >= 0.50:
            grade = "C"
        elif score >= 0.30:
            grade = "D"
        else:
            grade = "F"

        # dedup flags (manter únicos, limitar)
        uniq = []
        seen = set()
        for f in flags:
            if f not in seen:
                seen.add(f)
                uniq.append(f)
        flags = uniq[:40]

        report = OddsQualityReport(
            score=score, grade=grade, flags=flags,
            n_markets=len(items) if not fixture_id else sum(
                1 for k, _ in items if k.startswith(f"{fixture_id}|")),
            n_ticks=n_ticks,
            avg_age_sec=round(avg_age, 2) if avg_age is not None else None,
            max_jump_pct=round(max_jump, 4) if max_jump is not None else None,
            stale_count=stale, spike_count=spike, invalid_count=invalid,
            details={**details, "market_types": market_types},
        )
        with self._lock:
            self._last_report = report
            self._reports += 1
            if grade in ("D", "F") or stale or spike:
                self._alerts.append({
                    "ts": _iso(), "grade": grade, "score": score,
                    "flags": flags[:10],
                })
        return report

    def attach_to_view(self, view: Optional[dict]) -> Optional[dict]:
        """Injeta quality_odds no view e retorna o view."""
        if not view or not isinstance(view, dict):
            return view
        self.ingest_from_view(view)
        fid = str((view.get("fixture") or {}).get("id") or "")
        rep = self.evaluate(fixture_id=fid or None)
        view["odds_quality"] = rep.to_dict()
        return view

    def latest_alerts(self, n: int = 10) -> List[dict]:
        with self._lock:
            return list(self._alerts)[-n:]

    def clear(self, fixture_id: Optional[str] = None) -> None:
        with self._lock:
            if fixture_id is None:
                self._hist.clear()
            else:
                for k in [k for k in self._hist if k.startswith(f"{fixture_id}|")]:
                    self._hist.pop(k, None)

    def stats(self) -> dict:
        with self._lock:
            return {
                "ingested": self._ingested,
                "series": len(self._hist),
                "reports": self._reports,
                "alerts": len(self._alerts),
                "last_score": self._last_report.score if self._last_report else None,
                "last_grade": self._last_report.grade if self._last_report else None,
                "max_fresh_sec": self.max_fresh_sec,
                "max_jump_pct": self.max_jump_pct,
            }


ODDS_MONITOR = OddsQualityMonitor()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    errs: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        s = "PASS" if cond else "FAIL"
        print(f"[{s}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            errs.append(name)

    mon = OddsQualityMonitor(max_fresh_sec=30, warn_fresh_sec=10, max_jump_pct=0.20)

    # T1: empty
    r0 = mon.evaluate()
    check("empty: score 0", r0.score == 0.0)
    check("empty: grade F", r0.grade == "F")
    check("empty: flag no_odds", "no_odds" in r0.flags)

    # T2: good odds
    now = time.time()
    mon.ingest_odds_list([
        {"market": "next_corner", "selection": "Yes", "price": 1.85, "ts": now},
        {"market": "corners", "selection": "Over 9.5", "price": 1.95, "line": 9.5, "ts": now},
        {"market": "1x2", "selection": "home", "price": 2.10, "ts": now},
    ], fixture_id="100")
    r1 = mon.evaluate(now=now)
    check("good: score alto", r1.score >= 0.7, f"score={r1.score}")
    check("good: grade A/B", r1.grade in ("A", "B"), f"grade={r1.grade}")
    check("good: n_ticks 3", r1.n_ticks == 3)
    check("good: sem stale", r1.stale_count == 0)

    # T3: stale
    mon2 = OddsQualityMonitor(max_fresh_sec=30)
    mon2.ingest_odds_list([
        {"market": "next_corner", "selection": "Yes", "price": 1.80, "ts": now - 120},
    ], fixture_id="200")
    r2 = mon2.evaluate(now=now)
    check("stale: stale_count", r2.stale_count >= 1)
    check("stale: score baixo", r2.score < 0.7, f"score={r2.score}")
    check("stale: flag", any("stale" in f for f in r2.flags))

    # T4: spike
    mon3 = OddsQualityMonitor(max_jump_pct=0.20)
    mon3.ingest_tick(OddsTick(market="next_corner", selection="Yes",
                               price=1.80, fixture_id="300", ts=now - 2))
    mon3.ingest_tick(OddsTick(market="next_corner", selection="Yes",
                               price=2.50, fixture_id="300", ts=now))  # +39%
    r3 = mon3.evaluate(now=now)
    check("spike: detectado", r3.spike_count >= 1)
    check("spike: flag", any("spike" in f for f in r3.flags))

    # T5: invalid
    mon4 = OddsQualityMonitor()
    mon4.ingest_tick(OddsTick(market="x", selection="y", price=0.5, fixture_id="4"))  # rejected
    check("invalid: nao ingere <1.01", mon4.stats()["ingested"] == 0)
    mon4.ingest_odds_list([{"market": "x", "selection": "y", "price": 1.50, "ts": now}])
    check("valid: ingere 1.50", mon4.stats()["ingested"] == 1)

    # T6: from view
    mon5 = OddsQualityMonitor()
    view = {
        "schema": "cornerai-analyst-1",
        "source": "test",
        "fixture": {"id": "999", "home": "A", "away": "B"},
        "odds": [
            {"market": "corners", "selection": "Over 8.5", "price": 1.75, "line": 8.5},
            {"decimalOdds": 2.05, "selection": "Under 8.5", "market": "corners", "line": 8.5},
        ],
    }
    n = mon5.ingest_from_view(view)
    check("view: 2 odds", n == 2)
    view2 = mon5.attach_to_view(view)
    check("view: odds_quality anexado", "odds_quality" in (view2 or {}))
    check("view: grade presente", view2["odds_quality"]["grade"] in list("ABCDF"))

    # T7: market classify
    check("class: next_corner", classify_market("next_corner") == "next_corner")
    check("class: total over_9_5", classify_market("over_9_5") == "total")
    check("class: 1x2", classify_market("1x2") == "other")

    # T8: stats
    st = mon.stats()
    check("stats: campos", all(k in st for k in
          ("ingested", "series", "reports", "last_score", "last_grade")))

    # T9: clear
    mon.clear("100")
    r_clear = mon.evaluate(fixture_id="100")
    check("clear: fixture vazia", r_clear.n_ticks == 0)

    print(f"\nodds_quality_monitor selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
