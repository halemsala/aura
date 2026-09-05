#!/usr/bin/env python3
"""Snapshot somente leitura dos serviços AURA (health/TCP)."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

SERVICES: dict[str, tuple[str, int, str]] = {
    "ollama": ("127.0.0.1", 11434, "/api/tags"),
    "engine": ("127.0.0.1", 8765, "/api/health"),
    "bridge": ("127.0.0.1", 8080, "/health"),
    "voice": ("127.0.0.1", 8099, "/api/voice/health"),
}

# Fallbacks comuns se /api/health não existir no engine
ENGINE_FALLBACKS = ("/api/health", "/api/status", "/health")


def tcp_check(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(url: str, timeout: float = 1.8) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data: Any = json.loads(raw)
            except json.JSONDecodeError:
                data = raw[:400]
            return {
                "online": True,
                "status": getattr(resp, "status", 200),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "data": data,
            }
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def _check_service(name: str, host: str, port: int, path: str) -> dict[str, Any]:
    item: dict[str, Any] = {"online": False, "port": port, "host": host}
    if not tcp_check(host, port):
        item["error"] = "tcp_refused"
        return item
    item["online"] = True
    if name == "engine":
        health = None
        for p in ENGINE_FALLBACKS:
            health = http_get(f"http://{host}:{port}{p}")
            if health.get("online"):
                item["health_path"] = p
                break
        item["health"] = health or {"online": False, "error": "no_health_path"}
    else:
        item["health"] = http_get(f"http://{host}:{port}{path}")
    return item


def collect_snapshot(include_ui_state: bool = True) -> dict[str, Any]:
    services: dict[str, Any] = {}
    for name, (host, port, path) in SERVICES.items():
        services[name] = _check_service(name, host, port, path)

    ui_state = None
    if include_ui_state and services.get("engine", {}).get("online"):
        ui = http_get("http://127.0.0.1:8765/api/ui/state")
        if ui.get("online"):
            ui_state = ui.get("data")

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "services": services,
        "ui_state_present": ui_state is not None,
        "ui_state_keys": list(ui_state.keys())[:20] if isinstance(ui_state, dict) else None,
        "policy": {
            "paper_trade": True,
            "execution_allowed": False,
            "mode": "analise_operante",
            "lab_advisory": True,
        },
    }


def offline_services(snapshot: dict[str, Any]) -> list[str]:
    out = []
    for name, item in (snapshot.get("services") or {}).items():
        if not item.get("online"):
            out.append(name)
            continue
        health = item.get("health") or {}
        if health and health.get("online") is False:
            out.append(name)
    return out


def snapshot_hints(snapshot: dict[str, Any]) -> list[str]:
    """Gera tokens de sintoma a partir do snapshot (para match no catálogo)."""
    hints: list[str] = []
    for name in offline_services(snapshot):
        hints.append(f"{name} offline")
        if name == "engine":
            hints.append("engine porta 8765")
        if name == "bridge":
            hints.append("bridge health")
        if name == "voice":
            hints.append("voice 8099")
        if name == "ollama":
            hints.append("ollama modelo")
    eng = (snapshot.get("services") or {}).get("engine") or {}
    if eng.get("online") and not snapshot.get("ui_state_present"):
        hints.append("ui state vazio painel")
    return hints


if __name__ == "__main__":
    print(json.dumps(collect_snapshot(), ensure_ascii=False, indent=2))
