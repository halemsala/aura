"""Modo funcionário: pausa agentes extra do Aura para libertar CPU/GPU ao Alfred.
Nunca mata Ollama (11434), Hermes (8777) nem Alfred (8791)."""
import json
import os
import subprocess
import time
from pathlib import Path

from . import paths

STATE_PATH = paths.DATA_ROOT / "focus_mode.json"
PROTECTED_PORTS = {11434, 8777, 8791}
PAUSABLE = {
    8080: "bridge",
    8765: "engine",
    8766: "matriz",
    8099: "voice",
    8778: "hermes-dash",
}


def _load() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"active": False, "paused": [], "reason": ""}


def _save(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_on_port(port: int):
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, timeout=8, errors="replace")
    except Exception:  # noqa: BLE001
        return None
    needle = f"127.0.0.1:{port}"
    for line in out.splitlines():
        if needle in line and "LISTENING" in line.upper():
            try:
                return int(line.split()[-1])
            except ValueError:
                return None
    return None


def _kill(pid: int) -> None:
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def _pause_watchdog() -> str:
    try:
        import sys
        scripts = str(paths.PROJECT_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import aura_watchdog as wd
        return wd.stop_watchdog()
    except Exception as e:  # noqa: BLE001
        return f"watchdog skip: {e}"


def _resume_watchdog() -> str:
    try:
        import sys
        scripts = str(paths.PROJECT_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import aura_watchdog as wd
        return wd.start_watchdog(auto_repair=False)
    except Exception as e:  # noqa: BLE001
        return f"watchdog skip: {e}"


def status() -> dict:
    st = _load()
    st["protected_ports"] = sorted(PROTECTED_PORTS)
    st["pausable"] = PAUSABLE
    return st


def enter(reason: str = "trabalho desktop Alfred") -> dict:
    st = _load()
    paused = []
    wd = _pause_watchdog()
    for port, name in PAUSABLE.items():
        pid = _pid_on_port(port)
        if pid:
            _kill(pid)
            paused.append({"name": name, "port": port, "pid": pid})
    st = {"active": True, "reason": reason, "paused": paused, "watchdog": wd,
          "ts": time.time(), "protected": sorted(PROTECTED_PORTS)}
    _save(st)
    return st


def exit_focus() -> dict:
    st = _load()
    wd = _resume_watchdog()
    st["active"] = False
    st["watchdog"] = wd
    st["exited_at"] = time.time()
    st["nota"] = "agentes pausados não são relançados automaticamente; usa AURA_START_ALL se precisares da stack completa. Hermes+Alfred+Ollama ficaram vivos."
    _save(st)
    return st
