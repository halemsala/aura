"""
tab_scheduler.py — Orquestrador multi-tab priorizado por janela de valor.

MÓDULO NOVO. NÃO É o browser_agent.py — salvar com aquele nome apagaria o
browser_agent v4 (interceptação de API, HeuristicWalker, decoder WS, modo
dual). Este módulo é CONSULTADO por ele.

CORREÇÕES sobre o lote recebido:
    1. A versão recebida FALHAVA no próprio self-test: minuto 46 cai em W1
       (28-50) e o teste esperava 15 s de "halftime". Meio-tempo é ESTADO do
       jogo, não faixa de minuto — 45-50 são acréscimos do 1º tempo e
       PERTENCEM a W1 na definição do sistema (§3, mc_grid). Aqui HT vem de
       status explícito.
    2. Rank determinístico: (prioridade, minuto desc, fixture_id) — mesmo
       input, mesmo plano; testável e replayável.
    3. Orquestra ORÇAMENTO de abas (max_active), não só intervalo.
    4. W2 > W1 na prioridade: janela W2 perdida é fixture perdido (não há
       recuperação no fim do jogo); W1 perdida ainda deixa W2.

INTEGRAÇÃO (browser_agent.py v4 — mescla, não substituição):
    - loop de drenagem do driver Selenium: sleep = sched.poll_interval(...)
      (no Playwright a interceptação é push; o intervalo só regula keepalive)
    - alocação de abas: sched.plan(fixtures, max_active=N) — consulte
      hardware_governor.can_run_background() antes de abrir aba nova.

std-lib only. Python 3.9+. Windows compatível.
"""
from __future__ import annotations

import sys
import threading
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"


class TabScheduler:
    """Classificação de fixture por janela de valor + plano de abas."""

    W1 = (28, 50)
    W2 = (78, 108)

    _PRIORITY = {"W2": 4, "W1": 3, "LIVE_LOW": 2, "HT": 1, "PRE": 1,
                 "UNKNOWN": 1, "POST": 0}

    _HT = {"HT", "HALFTIME", "HALF_TIME", "INTERVALO", "INTERVAL"}
    _PRE = {"PRE", "PREMATCH", "PRE_MATCH", "AGENDADO", "SCHEDULED"}
    _POST = {"POST", "FINISHED", "FT", "ENCERRADO", "FINAL", "FIM"}

    DEFAULT_INTERVALS = {
        "W2": 1.0,        # janela decisiva: dreno agressivo
        "W1": 1.0,        # janela primária
        "LIVE_LOW": 5.0,  # fora das janelas
        "HT": 15.0,       # intervalo (por status, NUNCA por minuto)
        "PRE": 30.0,      # pré-jogo: só bootstrap de fixture
        "UNKNOWN": 5.0,
        "POST": None,     # parar de drenar
    }

    def __init__(self, intervals: Optional[Dict[str, Optional[float]]] = None) -> None:
        self._intervals: Dict[str, Optional[float]] = dict(self.DEFAULT_INTERVALS)
        if intervals:
            self._intervals.update(intervals)
        self._lock = threading.Lock()
        self._evaluations = 0
        self._plans = 0
        self._class_counts: Dict[str, int] = {}

    # ------------------------------------------------------------ classify
    @classmethod
    def classify(cls, minute: Optional[int], status: Optional[str] = None) -> str:
        s = (status or "").strip().upper()
        if s in cls._HT:
            return "HT"
        if s in cls._PRE:
            return "PRE"
        if s in cls._POST:
            return "POST"
        if minute is None:
            return "UNKNOWN"
        try:
            m = int(minute)
        except (TypeError, ValueError):
            return "UNKNOWN"
        if cls.W2[0] <= m <= cls.W2[1]:
            return "W2"
        if cls.W1[0] <= m <= cls.W1[1]:
            return "W1"
        return "LIVE_LOW"

    # ------------------------------------------------------------------ api
    def poll_interval(self, minute: Optional[int] = None,
                      status: Optional[str] = None) -> Optional[float]:
        """Intervalo de drenagem (s) para a fixture. None = parar."""
        cls_ = self.classify(minute, status)
        with self._lock:
            self._evaluations += 1
            self._class_counts[cls_] = self._class_counts.get(cls_, 0) + 1
            return self._intervals.get(cls_)

    def plan(self, fixtures: List[Dict[str, Any]], max_active: int) -> List[Dict[str, Any]]:
        """Aloca orçamento de abas. fixtures: [{fixture_id, minute, status?}].
        POST é descartado. Retorna plano ordenado por prioridade; cada item:
        {"fixture_id", "class", "mode": ACTIVE|BACKGROUND, "poll_interval"}.
        Determinístico para o mesmo input."""
        if max_active < 0:
            raise ValueError("max_active deve ser >= 0")
        scored = []
        for fx in fixtures:
            fid = str(fx.get("fixture_id"))
            minute = fx.get("minute")
            cls_ = self.classify(minute, fx.get("status"))
            if cls_ == "POST":
                continue
            try:
                m = -1 if minute is None else int(minute)
            except (TypeError, ValueError):
                m = -1
            scored.append((self._PRIORITY[cls_], -m, fid, cls_))
        # prioridade DESC, minuto DESC (via -m), fixture_id ASC
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))

        with self._lock:
            self._plans += 1

        out: List[Dict[str, Any]] = []
        for rank, (_pr, _negm, fid, cls_) in enumerate(scored):
            out.append({
                "fixture_id": fid,
                "class": cls_,
                "mode": "ACTIVE" if rank < max_active else "BACKGROUND",
                "poll_interval": self._intervals.get(cls_),
            })
        return out

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tab_scheduler": {
                    "evaluations": self._evaluations,
                    "plans": self._plans,
                    "class_counts": dict(self._class_counts),
                    "intervals": dict(self._intervals),
                }
            }


if __name__ == "__main__":
    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            sys.exit(1)

    check("W1", TabScheduler.classify(35) == "W1")
    check("W2", TabScheduler.classify(85) == "W2")
    check("46' é W1 (acréscimos do 1º tempo) — bug da versão recebida",
          TabScheduler.classify(46) == "W1")
    check("HT por status, não por minuto", TabScheduler.classify(46, status="HT") == "HT")
    check("HT pt-br", TabScheduler.classify(50, status="intervalo") == "HT")
    check("LIVE_LOW", TabScheduler.classify(12) == "LIVE_LOW")
    check("PRE", TabScheduler.classify(None, status="agendado") == "PRE")
    check("POST vence minuto", TabScheduler.classify(90, status="FT") == "POST")

    sched = TabScheduler()
    check("poll W1", sched.poll_interval(46) == 1.0)
    check("poll HT", sched.poll_interval(None, "HT") == 15.0)
    check("poll POST é None (parar)", sched.poll_interval(90, "FT") is None)

    fixtures = [
        {"fixture_id": "fA", "minute": 85},
        {"fixture_id": "fB", "minute": 35},
        {"fixture_id": "fC", "minute": 10},
        {"fixture_id": "fD", "minute": 95},
        {"fixture_id": "fE", "minute": 60, "status": "FT"},  # descartado
    ]
    plan = sched.plan(fixtures, max_active=2)
    ids_active = [p["fixture_id"] for p in plan if p["mode"] == "ACTIVE"]
    check("POST descartado do plano", all(p["fixture_id"] != "fE" for p in plan))
    check("W2 domina o orçamento (minuto desc como desempate)", ids_active == ["fD", "fA"])
    check("W1 vira background",
          next(p for p in plan if p["fixture_id"] == "fB")["mode"] == "BACKGROUND")
    check("determinístico", sched.plan(fixtures, max_active=2) == plan)

    custom = TabScheduler(intervals={"W1": 2.0})
    check("intervalos configuráveis", custom.poll_interval(35) == 2.0)

    try:
        sched.plan([], max_active=-1)
        ok = False
    except ValueError:
        ok = True
    check("max_active negativo rejeitado", ok)

    st = sched.stats()["tab_scheduler"]
    check("stats coerente", st["evaluations"] == 3 and st["plans"] == 2)
    print("ALL TESTS PASSED - tab_scheduler.py")
