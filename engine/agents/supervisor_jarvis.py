#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Supervisor JARVIS: loop autonomo que checa servicos,
freshness dos dados e orquestra agentes sem intervencao humana.
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.jarvis")
__version__ = "1.0.0"
__all__ = ["SupervisorJarvis", "JARVIS"]


class SupervisorJarvis:
    """Loop de supervisao com checagens plugaveis e alertas em mudanca de estado."""

    def __init__(self, *, check_interval: float = 30.0,
                 alert_callback: Optional[Callable[[str, str, str], None]] = None):
        self.interval = float(check_interval)
        self.alert_cb = alert_callback
        self._lock = threading.Lock()
        self._checks: List[Dict[str, Any]] = []
        self._state: Dict[str, str] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started_at = 0.0
        self._cycles = 0

    def register_check(self, name: str,
                       check_fn: Callable[[], Dict[str, Any]]) -> None:
        """check_fn() -> {"status": "ok"|"warn"|"down", "message": str, ...}"""
        with self._lock:
            self._checks.append({"name": str(name), "fn": check_fn})

    def _evaluate(self) -> dict:
        results = {}
        with self._lock:
            checks = list(self._checks)
        for chk in checks:
            name = chk["name"]
            try:
                r = chk["fn"]() or {}
                status = r.get("status", "ok")
                results[name] = r
                prev = self._state.get(name)
                if prev != status:
                    log.info("[jarvis] %s: %s -> %s (%s)",
                             name, prev, status, r.get("message", ""))
                    self._state[name] = status
                    if status != "ok" and self.alert_cb:
                        try:
                            self.alert_cb(name, status, r.get("message", ""))
                        except Exception:
                            log.exception("[jarvis] alert callback falhou")
            except Exception as e:
                results[name] = {"status": "error", "message": str(e)}
                self._state[name] = "error"
                log.exception("[jarvis] check %s falhou", name)
        return results

    def start(self) -> "SupervisorJarvis":
        if self._running:
            return self
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._loop,
                                        name="jarvis", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while self._running:
            try:
                self._evaluate()
                with self._lock:
                    self._cycles += 1
            except Exception:
                log.exception("[jarvis] ciclo falhou")
            time.sleep(self.interval)

    def stop(self) -> None:
        self._running = False

    def run_once(self) -> dict:
        return self._evaluate()

    def status(self) -> dict:
        with self._lock:
            return {"running": self._running, "cycles": self._cycles,
                    "uptime_sec": round(time.time() - self._started_at, 1)
                    if self._started_at else 0,
                    "checks": [c["name"] for c in self._checks],
                    "states": dict(self._state)}


JARVIS = SupervisorJarvis()


if __name__ == "__main__":
    import sys
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    alerts = []
    j = SupervisorJarvis(check_interval=0.5,
                        alert_callback=lambda n, s, m: alerts.append((n, s, m)))
    state = {"up": True}
    j.register_check("svc", lambda: {
        "status": "ok" if state["up"] else "down",
        "message": "vivo" if state["up"] else "morto"})
    j.start()
    time.sleep(1.5)
    check("roda ciclos", j.status()["cycles"] >= 1)
    check("estado inicial ok", j.status()["states"].get("svc") == "ok")
    state["up"] = False
    time.sleep(1.5)
    check("detecta mudanca para down",
          j.status()["states"].get("svc") == "down")
    check("dispara alerta", len(alerts) > 0 and alerts[0][1] == "down")
    state["up"] = True
    time.sleep(1.5)
    check("detecta recuperacao",
          j.status()["states"].get("svc") == "ok")
    j.stop()
    print(f"\nsupervisor_jarvis selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
