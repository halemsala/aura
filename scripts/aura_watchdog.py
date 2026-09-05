# -*- coding: utf-8 -*-
"""Watchdog AURA — monitora portas, auto-repara core (nunca mata Hermes/Ollama), grava alertas."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
ALERTS = ROOT / "logs_supervisor" / "aura_alerts.jsonl"
STATE = ROOT / "logs_supervisor" / "aura_watchdog.json"

CHECKS = {
    "bridge": "http://127.0.0.1:8080/health",
    "engine": "http://127.0.0.1:8765/api/health",
    "matriz": "http://127.0.0.1:8766/health",
    "voice": "http://127.0.0.1:8099/api/voice/health",
    "ollama": "http://127.0.0.1:11434/api/tags",
}

_lock = threading.Lock()
_thread = None
_stop = threading.Event()


def _ping(url: str, timeout: float = 2.0) -> bool:
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _alert(text: str, level: str = "warn") -> None:
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.time(), "level": level, "text": text}
    with ALERTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": False, "auto_repair": False, "last": {}, "repairs": 0}


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _try_repair(name: str) -> str:
    """Repara um servico via aura_chat_agents.restart_service (nunca hermes)."""
    if name in ("hermes", "ollama"):
        return "protegido"
    try:
        import sys
        scripts = str(ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import aura_chat_agents as ag
        return ag.restart_service(name)
    except Exception as exc:
        return f"fail:{exc}"


def _loop(auto_repair: bool) -> None:
    fail_streak = {k: 0 for k in CHECKS}
    repair_times = {k: [] for k in CHECKS}
    open_until = {k: 0.0 for k in CHECKS}
    while not _stop.is_set():
        st = _load()
        if not st.get("enabled"):
            time.sleep(3)
            continue
        last = {}
        now = time.time()
        for name, url in CHECKS.items():
            ok = _ping(url)
            last[name] = "OK" if ok else "OFF"
            if ok:
                fail_streak[name] = 0
            else:
                fail_streak[name] += 1
                if fail_streak[name] == 2:
                    _alert(f"{name} OFF (2 checks). Monitor AURA.", "error")
                if auto_repair and st.get("auto_repair") and name in ("bridge", "engine", "matriz", "voice"):
                    if open_until[name] > now:
                        continue
                    repair_times[name] = [t for t in repair_times[name] if now - t < 900]
                    if len(repair_times[name]) >= 3:
                        open_until[name] = now + 300
                        _alert(f"Circuit breaker: {name} com 3 reparos/15min — pausa 5min.", "error")
                        continue
                    if fail_streak[name] >= 2 and fail_streak[name] % 3 == 2:
                        _alert(f"Auto-reparo: a reiniciar {name}...", "info")
                        result = _try_repair(name)
                        repair_times[name].append(now)
                        st["repairs"] = int(st.get("repairs") or 0) + 1
                        _alert(f"Auto-reparo {name}: {str(result)[:160]}", "info")
        st["last"] = last
        st["last_ts"] = time.time()
        _save(st)
        time.sleep(8)


def start_watchdog(auto_repair: bool = True) -> str:
    global _thread
    st = _load()
    st["enabled"] = True
    st["auto_repair"] = bool(auto_repair)
    _save(st)
    _stop.clear()
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, args=(auto_repair,), name="aura-watchdog", daemon=True)
            _thread.start()
    return (
        "Monitor automatico ACTIVO. Verifica bridge/engine/matriz/voice/ollama a cada 8s. "
        f"Auto-reparo={'ON' if auto_repair else 'OFF'} (nunca mata Hermes/Ollama). "
        "Alertas em logs_supervisor/aura_alerts.jsonl e barra do chat."
    )


def stop_watchdog() -> str:
    st = _load()
    st["enabled"] = False
    _save(st)
    _stop.set()
    return "Monitor automatico parado."


def watchdog_status() -> str:
    st = _load()
    last = st.get("last") or {}
    line = " | ".join(f"{k} {v}" for k, v in last.items()) or "ainda sem amostras"
    return (
        f"Watchdog={'ON' if st.get('enabled') else 'OFF'} "
        f"auto_repair={'ON' if st.get('auto_repair') else 'OFF'} "
        f"repairs={st.get('repairs', 0)}. {line}"
    )


if __name__ == "__main__":
    print(start_watchdog(True))
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print(stop_watchdog())
