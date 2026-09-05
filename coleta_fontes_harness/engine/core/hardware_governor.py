#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Hardware Governor: monitora CPU/VRAM e BLOQUEIA
agentes de fundo quando ultrapassa 85%. Protege a RTX 4050 de travar
o Windows. pynvml/psutil opcionais — fallback nvidia-smi (stdlib).
"""
from __future__ import annotations
import logging
import subprocess
import threading
import time
from typing import Any, Dict, Optional

log = logging.getLogger("aura.governor")
__version__ = "1.0.0"
__all__ = ["HardwareGovernor", "GOVERNOR"]


class HardwareGovernor:
    """Monitor de hardware com limiar de bloqueio."""

    def __init__(self, *, vram_limit_pct: float = 85.0,
                 cpu_limit_pct: float = 85.0,
                 check_interval: float = 5.0):
        self.vram_limit = float(vram_limit_pct)
        self.cpu_limit = float(cpu_limit_pct)
        self.interval = float(check_interval)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._vram_pct = 0.0
        self._vram_total_mb = 0
        self._vram_used_mb = 0
        self._cpu_pct = 0.0
        self._blocks = 0
        self._checks = 0
        self._last_check = 0.0
        self._pynvml = None
        self._psutil = None
        self._nvidia_smi = self._find_nvidia_smi()
        self._init_libs()

    def _find_nvidia_smi(self) -> Optional[str]:
        for p in ("nvidia-smi",
                  r"C:\Windows\System32\nvidia-smi.exe",
                  r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
            try:
                subprocess.run([p, "--query-gpu=name", "--format=csv,noheader"],
                               capture_output=True, timeout=3)
                return p
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        return None

    def _init_libs(self) -> None:
        try:
            import pynvml
            pynvml.nvmlInit()
            self._pynvml = pynvml
            log.info("[governor] pynvml ativo")
        except Exception:
            pass
        try:
            import psutil
            self._psutil = psutil
            log.info("[governor] psutil ativo")
        except Exception:
            pass

    def _sample(self) -> None:
        # VRAM via pynvml
        if self._pynvml is not None:
            try:
                h = self._pynvml.nvmlDeviceGetHandleByIndex(0)
                info = self._pynvml.nvmlDeviceGetMemoryInfo(h)
                self._vram_total_mb = int(info.total // (1024 * 1024))
                self._vram_used_mb = int(info.used // (1024 * 1024))
                self._vram_pct = 100.0 * info.used / max(info.total, 1)
                return
            except Exception:
                self._pynvml = None
        # VRAM via nvidia-smi
        if self._nvidia_smi:
            try:
                r = subprocess.run(
                    [self._nvidia_smi,
                     "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5)
                parts = r.stdout.strip().split(",")
                if len(parts) >= 2:
                    self._vram_used_mb = int(parts[0].strip())
                    self._vram_total_mb = int(parts[1].strip())
                    self._vram_pct = (100.0 * self._vram_used_mb
                                      / max(self._vram_total_mb, 1))
                return
            except Exception:
                pass
        # CPU via psutil
        if self._psutil is not None:
            try:
                self._cpu_pct = float(self._psutil.cpu_percent(interval=0.5))
            except Exception:
                pass

    def can_run_background(self) -> bool:
        """True se agentes de fundo podem rodar (abaixo do limite)."""
        with self._lock:
            ok = (self._vram_pct < self.vram_limit
                  and self._cpu_pct < self.cpu_limit)
            if not ok:
                self._blocks += 1
            return ok

    def wait_if_busy(self, max_wait: float = 30.0) -> bool:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if self.can_run_background():
                return True
            time.sleep(1.0)
        return False

    def start(self) -> "HardwareGovernor":
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._loop,
                                        name="hw-governor", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while self._running:
            try:
                self._sample()
                with self._lock:
                    self._checks += 1
                    self._last_check = time.time()
            except Exception:
                log.exception("[governor] amostragem falhou")
            time.sleep(self.interval)

    def stop(self) -> None:
        self._running = False

    def stats(self) -> dict:
        with self._lock:
            return {
                "vram_pct": round(self._vram_pct, 1),
                "vram_used_mb": self._vram_used_mb,
                "vram_total_mb": self._vram_total_mb,
                "vram_limit_pct": self.vram_limit,
                "cpu_pct": round(self._cpu_pct, 1),
                "cpu_limit_pct": self.cpu_limit,
                "blocks": self._blocks, "checks": self._checks,
                "can_run_background": (self._vram_pct < self.vram_limit
                                       and self._cpu_pct < self.cpu_limit),
                "running": self._running}

    def pre_warm_llm(self, target_minute: int, current_minute: int,
                     *, enabled: bool = False, model: str = "llama3.2:3b",
                     timeout: float = 5.0) -> bool:
        """Pre-warm opt-in do Ollama; por padrão não faz rede nem subprocesso."""
        import json
        import os
        import urllib.request
        if not enabled or os.getenv("AURA_OLLAMA_PREWARM_ENABLED", "0") != "1":
            return False
        approaching = ((target_minute == 35 and 30 <= current_minute <= 34) or
                       (target_minute == 85 and 80 <= current_minute <= 84))
        if not approaching or not self.can_run_background():
            return False
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps({"model": model, "keep_alive": "10m", "prompt": ""}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=float(timeout)) as response:
                return 200 <= int(response.status) < 300
        except Exception:
            return False


GOVERNOR = HardwareGovernor()


if __name__ == "__main__":
    import sys
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    gov = HardwareGovernor(check_interval=1.0)
    gov.start()
    time.sleep(3)
    st = gov.stats()
    check("governor amostra VRAM", st["vram_total_mb"] > 0,
          f"{st['vram_used_mb']}/{st['vram_total_mb']}MB ({st['vram_pct']}%)")
    check("limite 85%", st["vram_limit_pct"] == 85.0)
    check("can_run_background bool", isinstance(st["can_run_background"], bool))
    gov.stop()
    print(f"\nhardware_governor selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
