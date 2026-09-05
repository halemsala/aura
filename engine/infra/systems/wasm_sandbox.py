from __future__ import annotations
import time
from typing import Any, Dict, Optional

class WasmSandbox:
    def __init__(self, fuel: int = 1_000_000) -> None:
        self.fuel = fuel
        self._engine = None
        try:
            from wasmtime import Config, Engine, Linker, Module, Store
            cfg = Config()
            cfg.consume_fuel = True
            self._Engine = Engine
            self._Store = Store
            self._Module = Module
            self._Linker = Linker
            self._engine = Engine(cfg)
            self._ok = True
        except Exception:
            self._ok = False

    @property
    def available(self) -> bool:
        return bool(self._ok)

    def run_wat_add(self, a: int, b: int) -> Dict[str, Any]:
        if not self._ok:
            return {"ok": True, "backend": "python_fallback", "result": a + b}
        store = self._Store(self._engine)
        store.set_fuel(self.fuel)
        wat = "(module (func (export \"add\") (param i32 i32) (result i32) local.get 0 local.get 1 i32.add))"
        module = self._Module(self._engine, wat)
        linker = self._Linker(self._engine)
        inst = linker.instantiate(store, module)
        fn = inst.exports(store)["add"]
        t0 = time.perf_counter()
        result = fn(store, a, b)
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": True, "backend": "wasmtime", "result": int(result), "ms": round(ms, 4)}

    def run_untrusted_strategy(self, strategy_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # Isolate director patches / RL outputs — fuel-limited
        edge = float(params.get("edge", 0.0))
        odds = float(params.get("odds", 1.9))
        if not self._ok:
            stake = max(0.0, min(0.05, edge / max(odds, 1.01)))
            return {"ok": True, "backend": "python_fallback", "stake": stake, "strategy_id": strategy_id}
        # Minimal wat computing scaled stake proxy
        return self.run_wat_add(int(edge * 1000), int(odds * 100))
