#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Security: forca PAPER_TRADE=True e EXECUTION_ALLOWED=False.
Estas constantes nao podem ser sobrescritas por config externa.
Qualquer violacao e logada em nivel CRITICAL e pode abortar.
"""
from __future__ import annotations
import logging
import sys
import threading
import time
from typing import Any, Dict

log = logging.getLogger("aura.security")
__version__ = "1.0.0"
__all__ = ["GUARD", "assert_paper_trade", "assert_no_execution"]

# Invariantes do sistema — NUNCA devem mudar em runtime.
PAPER_TRADE: bool = True
EXECUTION_ALLOWED: bool = False
GLM_ADVISORY_ONLY: bool = True

_INVARIANTS = {"PAPER_TRADE": True, "EXECUTION_ALLOWED": False,
               "GLM_ADVISORY_ONLY": True}


class SecurityGuard:
    """Verifica em runtime que nenhuma parte tentou mudar os invariantes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._violations: list = []
        self._checks = 0

    def verify(self, namespace: dict, *, source: str = "") -> bool:
        ok = True
        with self._lock:
            self._checks += 1
            for flag, expected in _INVARIANTS.items():
                actual = namespace.get(flag)
                if actual is not None and actual != expected:
                    self._violations.append(
                        {"ts": time.time(), "flag": flag,
                         "expected": expected, "actual": actual,
                         "source": source})
                    log.critical("[security] VIOLACAO: %s=%r (esperado %r) em %s",
                                 flag, actual, expected, source)
                    ok = False
        return ok

    def assert_flags(self) -> None:
        """Levanta RuntimeError se qualquer invariante foi violada."""
        for flag, expected in _INVARIANTS.items():
            actual = globals().get(flag)
            if actual != expected:
                raise RuntimeError(
                    f"VIOLACAO DE SEGURANCA: {flag}={actual!r} (esperado {expected!r})")

    def stats(self) -> dict:
        with self._lock:
            return {"checks": self._checks,
                    "violations": len(self._violations),
                    "recent_violations": list(self._violations[-20:]),
                    "invariants": dict(_INVARIANTS)}


GUARD = SecurityGuard()


def assert_paper_trade() -> None:
    if not PAPER_TRADE:
        raise RuntimeError("PAPER_TRADE=False — violacao de seguranca")


def assert_no_execution() -> None:
    if EXECUTION_ALLOWED:
        raise RuntimeError("EXECUTION_ALLOWED=True — violacao de seguranca")


if __name__ == "__main__":
    errs = []
    def check(n, c):
        print(f"[{'PASS' if c else 'FAIL'}] {n}")
        if not c: errs.append(n)

    check("PAPER_TRADE imutavel", PAPER_TRADE is True)
    check("EXECUTION_ALLOWED imutavel", EXECUTION_ALLOWED is False)
    GUARD.verify({"PAPER_TRADE": True}, source="ok")
    check("verify aceita correto", GUARD.stats()["violations"] == 0)
    GUARD.verify({"PAPER_TRADE": False}, source="bad")
    check("verify detecta violacao", GUARD.stats()["violations"] == 1)
    assert_paper_trade()
    assert_no_execution()
    check("assert nao levanta em estado correto", True)
    print(f"\nsecurity selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
