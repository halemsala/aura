#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Process Supervisor v2 — PID tracking, health, restart com backoff, circuit breaker.
Substitui orquestracao fragil so com start /MIN nos BATs.
Paper-trade only. Nao altera execution_allowed.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import urlopen
from urllib.error import URLError

ROOT = Path(os.environ.get("AURA_ROOT", Path(__file__).resolve().parents[1])).resolve()
LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)

VENV_PY = ROOT / "engine" / "venv" / "Scripts" / "python.exe"
if not VENV_PY.exists():
    VENV_PY = Path(sys.executable)


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def base_env() -> Dict[str, str]:
    e = os.environ.copy()
    e["AURA_ROOT"] = str(ROOT)
    e["PYTHONPATH"] = f"{ROOT};{ROOT / 'engine'};{ROOT / 'bridge'}"
    e["PYTHONUNBUFFERED"] = "1"
    e["PYTHONUTF8"] = "1"
    e["PAPER_TRADE"] = "true" if _env_bool("PAPER_TRADE", True) else "false"
    e["EXECUTION_ALLOWED"] = "false" if not _env_bool("EXECUTION_ALLOWED", False) else "true"
    e["AURA_LLM_BACKEND"] = e.get("AURA_LLM_BACKEND") or "hermes"
    e["CORNERAI_CHAT_MODEL"] = e.get("CORNERAI_CHAT_MODEL") or "llama3.2:3b"
    e["AURA_GLM_ENABLED"] = e.get("AURA_GLM_ENABLED") or "0"
    e["CORNERAI_BRIDGE_REQUIRE_TOKEN"] = e.get("CORNERAI_BRIDGE_REQUIRE_TOKEN") or "0"
    e["OLLAMA_KEEP_ALIVE"] = e.get("OLLAMA_KEEP_ALIVE") or "30m"
    e["CUDA_VISIBLE_DEVICES"] = e.get("CUDA_VISIBLE_DEVICES") or "0"
    e["OLLAMA_NUM_GPU"] = e.get("OLLAMA_NUM_GPU") or "99"
    return e


@dataclass
class ServiceSpec:
    name: str
    cmd: List[str]
    health_url: Optional[str]
    startup_grace: float = 12.0
    max_restarts: int = 8
    restart_window: float = 300.0
    backoff_max: float = 60.0


class CircuitBreaker:
    def __init__(self, threshold: int = 5, recovery: float = 60.0):
        self.threshold = threshold
        self.recovery = recovery
        self.failures = 0
        self.open_until = 0.0

    def ok(self) -> bool:
        return time.time() >= self.open_until

    def success(self):
        self.failures = 0
        self.open_until = 0.0

    def fail(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.time() + self.recovery
            self.failures = 0
            return True
        return False


@dataclass
class Managed:
    spec: ServiceSpec
    proc: Optional[subprocess.Popen] = None
    started_at: float = 0.0
    restarts: deque = field(default_factory=lambda: deque(maxlen=20))
    cb: CircuitBreaker = field(default_factory=CircuitBreaker)
    last_ok: bool = False

    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc and self.proc.poll() is None else None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def health(self) -> bool:
        if not self.alive():
            return False
        if time.time() - self.started_at < self.spec.startup_grace:
            return True
        if not self.spec.health_url:
            return True
        if not self.cb.ok():
            return False
        try:
            with urlopen(self.spec.health_url, timeout=4) as r:
                ok = 200 <= getattr(r, "status", 200) < 300
            if ok:
                self.cb.success()
                self.last_ok = True
            else:
                if self.cb.fail():
                    logging.warning("[%s] circuit OPEN", self.spec.name)
                self.last_ok = False
            return ok
        except Exception as ex:
            if self.cb.fail():
                logging.warning("[%s] circuit OPEN: %s", self.spec.name, ex)
            self.last_ok = False
            return False

    def start(self, env: dict):
        if self.alive():
            return
        # backoff
        now = time.time()
        recent = sum(1 for t in self.restarts if now - t < self.spec.restart_window)
        if recent >= self.spec.max_restarts:
            backoff = min(2 ** (recent - self.spec.max_restarts + 1), self.spec.backoff_max)
            logging.warning("[%s] backoff %.0fs (restarts=%s)", self.spec.name, backoff, recent)
            time.sleep(backoff)

        log_path = LOGDIR / f"{self.spec.name}.log"
        if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
            try:
                log_path.replace(log_path.with_suffix(".log.1"))
            except Exception:
                pass
        logf = open(log_path, "a", encoding="utf-8", errors="replace")
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            self.spec.cmd,
            cwd=str(ROOT),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=creation,
        )
        self.started_at = time.time()
        self.restarts.append(self.started_at)
        logging.info("[%s] started pid=%s", self.spec.name, self.proc.pid)

    def stop(self, timeout: float = 8.0):
        if not self.proc:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        logging.info("[%s] stopped", self.spec.name)
        self.proc = None


def build_services() -> List[ServiceSpec]:
    py = str(VENV_PY)
    return [
        ServiceSpec(
            name="bridge",
            cmd=[py, "-u", str(ROOT / "bridge" / "server.py"), "--host", "127.0.0.1", "--port", "8080"],
            health_url="http://127.0.0.1:8080/health",
        ),
        ServiceSpec(
            name="engine",
            cmd=[py, "-u", str(ROOT / "engine" / "server.py"), "--host", "127.0.0.1", "--port", "8765"],
            health_url="http://127.0.0.1:8765/api/health",
            startup_grace=18.0,
        ),
        ServiceSpec(
            name="voice",
            cmd=[py, "-u", str(ROOT / "bridge" / "jarvis_voice_server.py"), "--host", "127.0.0.1", "--port", "8099", "--lazy"],
            health_url="http://127.0.0.1:8099/api/voice/health",
            startup_grace=15.0,
        ),
    ]


def warmup_ollama(env: dict):
    """Keep model in VRAM via API keep_alive (not placebo env-only)."""
    model = env.get("CORNERAI_CHAT_MODEL", "llama3.2:3b")
    keep = env.get("OLLAMA_KEEP_ALIVE", "30m")
    body = json.dumps({
        "model": model,
        "prompt": "ok",
        "stream": False,
        "keep_alive": keep,
        "options": {"num_predict": 4},
    }).encode()
    try:
        from urllib.request import Request
        req = Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=120) as r:
            r.read()
        logging.info("ollama warmup ok model=%s keep_alive=%s", model, keep)
    except Exception as ex:
        logging.warning("ollama warmup skip: %s", ex)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOGDIR / "supervisor.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    if not (ROOT / "engine" / "server.py").exists():
        logging.error("engine/server.py ausente em %s", ROOT)
        return 2
    if not (ROOT / "bridge" / "server.py").exists():
        logging.error("bridge/server.py ausente")
        return 2

    env = base_env()
    specs = build_services()
    # voice opcional
    if not (ROOT / "bridge" / "jarvis_voice_server.py").exists():
        specs = [s for s in specs if s.name != "voice"]

    managed = {s.name: Managed(spec=s) for s in specs}
    stop = threading.Event()

    def _sig(*_):
        stop.set()

    signal.signal(signal.SIGINT, _sig)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _sig)
        except Exception:
            pass

    logging.info("AURA Supervisor ROOT=%s paper=%s exec=%s", ROOT, env.get("PAPER_TRADE"), env.get("EXECUTION_ALLOWED"))
    warmup_ollama(env)

    for m in managed.values():
        m.start(env)
        time.sleep(1.5)

    # status file
    status_path = LOGDIR / "supervisor_status.json"
    while not stop.is_set():
        snapshot = {"ts": datetime.now().isoformat(), "services": {}}
        for name, m in managed.items():
            if not m.alive():
                logging.warning("[%s] dead — restart", name)
                m.start(env)
            healthy = m.health()
            snapshot["services"][name] = {
                "pid": m.pid,
                "alive": m.alive(),
                "healthy": healthy,
                "restarts": len(m.restarts),
            }
        try:
            status_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception:
            pass
        stop.wait(8.0)

    logging.info("shutdown...")
    for m in managed.values():
        m.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
