#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Error Handler: elimina `except Exception: pass`.

Toda excecao e logada com traceback, contexto e contabilizada.
Instala hooks globais para excecoes nao capturadas (sys.excepthook + threading.excepthook).
"""
from __future__ import annotations
import functools
import logging
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.errors")
__version__ = "1.0.0"
__all__ = ["ErrorHandler", "ERRORS", "safe_call", "safe_decorator"]


class ErrorHandler:
    """Registro central de erros. Nunca silencia, nunca propaga."""

    def __init__(self, max_recent: int = 200):
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}
        self._recent: List[dict] = []
        self._max_recent = int(max_recent)
        self._installed = False

    def handle(self, exc: Exception, *, context: str = "",
               extra: Optional[dict] = None) -> dict:
        tb = traceback.format_exc()
        key = f"{type(exc).__name__}:{context}"
        entry = {"ts": time.time(), "type": type(exc).__name__,
                  "message": str(exc), "context": context,
                  "traceback": tb, "extra": extra or {}}
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            self._recent.append(entry)
            if len(self._recent) > self._max_recent:
                self._recent = self._recent[-self._max_recent:]
        log.error("[aura] %s em %s: %s\n%s",
                   type(exc).__name__, context or "?", exc, tb)
        return entry

    def install_global(self) -> None:
        """Instala hooks para capturar excecoes nao tratadas em qualquer thread."""
        if self._installed:
            return
        self._installed = True

        def _excepthook(exc_type, exc_value, tb):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, tb)
                return
            self.handle(exc_value, context="uncaught")

        sys.excepthook = _excepthook

        def _thread_excepthook(args):
            self.handle(args.exc_value,
                        context=f"thread:{getattr(args.thread, 'name', '?')}")

        threading.excepthook = _thread_excepthook

    def stats(self) -> dict:
        with self._lock:
            return {"total_types": len(self._counts),
                    "total_occurrences": sum(self._counts.values()),
                    "by_type": dict(self._counts),
                    "recent": len(self._recent)}

    def recent(self, n: int = 20) -> list:
        with self._lock:
            return list(self._recent[-n:])


ERRORS = ErrorHandler()


def safe_call(fn: Callable, *args, context: str = "", **kwargs) -> Any:
    """Chama fn; em excecao registra e retorna None (nunca propaga)."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        ERRORS.handle(e, context=context or getattr(fn, "__name__", "?"))
        return None


def safe_decorator(context: str = ""):
    """Decorador: captura excecoes, registra, retorna None."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                ERRORS.handle(e, context=context or fn.__name__)
                return None
        return wrapper
    return deco


if __name__ == "__main__":
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    ERRORS.handle(ValueError("teste"), context="selftest")
    check("handle registra", ERRORS.stats()["total_occurrences"] >= 1)
    check("handle conta por tipo", "ValueError:selftest" in ERRORS.stats()["by_type"])

    r = safe_call(lambda: 1 / 0, context="div")
    check("safe_call retorna None", r is None)
    check("safe_call registra", "ZeroDivisionError:div" in ERRORS.stats()["by_type"])

    @safe_decorator("deco")
    def boom():
        raise RuntimeError("boom")
    r2 = boom()
    check("decorador retorna None", r2 is None)
    check("decorador registra", "RuntimeError:deco" in ERRORS.stats()["by_type"])

    print(f"\nerror_handler selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
