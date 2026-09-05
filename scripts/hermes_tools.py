#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Tool Registry V9 — tool-use com guardrails. Nunca liga execution_allowed."""
from __future__ import annotations

import json
import shutil
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.request import Request, urlopen

from hermes_policy import PolicyGuard

TOOL_META = {
    'check_port': {'effect': 'read', 'risk': 'low'},
    'check_health': {'effect': 'read', 'risk': 'low'},
    'canary_ui_state': {'effect': 'read', 'risk': 'low'},
    'read_live_latest': {'effect': 'read', 'risk': 'low'},
    'health_score': {'effect': 'read', 'risk': 'low'},
    'deep_diagnostic': {'effect': 'read', 'risk': 'low'},
    'reinforce_safety_env': {'effect': 'env', 'risk': 'low'},
    'clear_pycache': {'effect': 'write_local', 'risk': 'low'},
    'acquire_lock': {'effect': 'write_local', 'risk': 'low'},
    'release_lock': {'effect': 'write_local', 'risk': 'low'},
    'wait_port': {'effect': 'read', 'risk': 'low'},
    'suggest_start_services': {'effect': 'read', 'risk': 'low'},
    'ensure_venv': {'effect': 'write_local', 'risk': 'medium'},
    'pip_install_critical': {'effect': 'network_install', 'risk': 'high'},
    'safe_start_bridge': {'effect': 'process', 'risk': 'medium'},
    'safe_start_engine': {'effect': 'process', 'risk': 'medium'},
    'safe_start_voice': {'effect': 'process', 'risk': 'medium'},
    'recycle_port': {'effect': 'kill_process', 'risk': 'high'},
    'canary_trader_chat': {'effect': 'post', 'risk': 'medium'},
}


@dataclass
class ToolResult:
    ok: bool
    name: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


def _port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _http(url: str, timeout: float = 3.0, method: str = "GET", payload: Any = None) -> tuple[int, str]:
    try:
        data = None
        headers = {"User-Agent": "HermesTools/8"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")[:800]
    except Exception as e:
        return 0, str(e)[:160]


class ToolRegistry:
    def __init__(self, root: Path):
        self.root = root
        self.history: List[ToolResult] = []
        self._tools: Dict[str, Callable[..., ToolResult]] = {
            "check_port": self.check_port,
            "check_health": self.check_health,
            "reinforce_safety_env": self.reinforce_safety_env,
            "clear_pycache": self.clear_pycache,
            "pip_install_critical": self.pip_install_critical,
            "suggest_start_services": self.suggest_start_services,
            "safe_start_bridge": self.safe_start_bridge,
            "safe_start_engine": self.safe_start_engine,
            "safe_start_voice": self.safe_start_voice,
            "canary_ui_state": self.canary_ui_state,
            "canary_trader_chat": self.canary_trader_chat,
            "read_live_latest": self.read_live_latest,
            "health_score": self.health_score,
            "acquire_lock": self.acquire_lock,
            "release_lock": self.release_lock,
            "ensure_venv": self.ensure_venv,
            "wait_port": self.wait_port,
            "recycle_port": self.recycle_port,
            "deep_diagnostic": self.deep_diagnostic,
        }

    def list_tools(self) -> List[str]:
        return sorted(self._tools)

    def run(self, name: str, **kwargs: Any) -> ToolResult:
        fn = self._tools.get(name)
        if not fn:
            r = ToolResult(False, name, f"Tool desconhecida: {name}")
            self.history.append(r)
            return r
        try:
            r = fn(**kwargs)
        except Exception as e:
            r = ToolResult(False, name, f"Exceção: {e}")
        self.history.append(r)
        return r

    def check_port(self, port: int = 8765) -> ToolResult:
        open_ = _port_open(int(port))
        return ToolResult(open_, "check_port", f"porta {port} {'OPEN' if open_ else 'CLOSED'}",
                          {"port": port, "open": open_})

    def check_health(self, service: str = "engine") -> ToolResult:
        urls = {
            "bridge": "http://127.0.0.1:8080/health",
            "engine": "http://127.0.0.1:8765/api/health",
            "voice": "http://127.0.0.1:8099/api/voice/health",
        }
        url = urls.get(service, urls["engine"])
        code, body = _http(url)
        ok = code == 200
        return ToolResult(ok, "check_health", f"{service} HTTP {code}",
                          {"service": service, "code": code, "body": body[:150]})

    def reinforce_safety_env(self) -> ToolResult:
        snap = PolicyGuard(self.root).enforce_env()
        return ToolResult(snap.ok(), "reinforce_safety_env",
                          "PAPER_TRADE=true EXECUTION_ALLOWED=false",
                          {"PAPER_TRADE": "true", "EXECUTION_ALLOWED": "false"})

    def clear_pycache(self) -> ToolResult:
        n = 0
        for p in self.root.rglob("__pycache__"):
            if "venv" in p.parts:
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        return ToolResult(True, "clear_pycache", f"removidos {n} __pycache__", {"count": n})

    def pip_install_critical(self) -> ToolResult:
        venv = self.root / "engine" / "venv" / "Scripts" / "python.exe"
        if not venv.exists():
            return ToolResult(False, "pip_install_critical", "venv ausente")
        try:
            r = subprocess.run(
                [str(venv), "-m", "pip", "install",
                 "fastapi", "uvicorn[standard]", "httpx", "requests", "pydantic", "psutil"],
                capture_output=True, text=True, timeout=120,
            )
            return ToolResult(r.returncode == 0, "pip_install_critical",
                              "deps OK" if r.returncode == 0 else (r.stderr or "")[:120])
        except Exception as e:
            return ToolResult(False, "pip_install_critical", str(e)[:120])

    def suggest_start_services(self) -> ToolResult:
        plan = []
        if not _port_open(8080):
            plan.append("Bridge OFF → safe_start_bridge")
        if not _port_open(8765):
            plan.append("Engine OFF → safe_start_engine")
        if not _port_open(8099):
            plan.append("Voice OFF → safe_start_voice")
        if not plan:
            plan.append("Serviços principais em LISTEN")
        return ToolResult(True, "suggest_start_services", "; ".join(plan), {"plan": plan})

    def _venv_python(self) -> str:
        v = self.root / "engine" / "venv" / "Scripts" / "python.exe"
        return str(v) if v.exists() else sys.executable

    def _spawn(self, script: Path, cwd: Path, extra_env: Dict[str, str] | None = None) -> None:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS  # type: ignore
        env = {**os.environ, "PAPER_TRADE": "true", "EXECUTION_ALLOWED": "false", "PYTHONUTF8": "1"}
        if extra_env:
            env.update(extra_env)
        subprocess.Popen(
            [self._venv_python(), str(script)],
            cwd=str(cwd),
            env=env,
            creationflags=flags if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def safe_start_bridge(self) -> ToolResult:
        if _port_open(8080):
            return ToolResult(True, "safe_start_bridge", "Bridge já em 8080")
        script = self.root / "bridge" / "server.py"
        if not script.exists():
            return ToolResult(False, "safe_start_bridge", "bridge/server.py ausente")
        try:
            self._spawn(script, self.root / "bridge")
            waited = self.wait_port(8080, timeout=6.0)
            ok = waited.ok or _port_open(8080)
            return ToolResult(ok, "safe_start_bridge",
                              "Bridge arrancado" if ok else "Bridge iniciado mas porta ainda fechada")
        except Exception as e:
            return ToolResult(False, "safe_start_bridge", str(e)[:120])

    def safe_start_engine(self) -> ToolResult:
        if _port_open(8765):
            return ToolResult(True, "safe_start_engine", "Engine já em 8765")
        script = self.root / "engine" / "server.py"
        if not script.exists():
            return ToolResult(False, "safe_start_engine", "engine/server.py ausente")
        try:
            self._spawn(script, self.root / "engine")
            waited = self.wait_port(8765, timeout=8.0)
            ok = waited.ok or _port_open(8765)
            return ToolResult(ok, "safe_start_engine",
                              "Engine arrancado" if ok else "Engine iniciado mas porta ainda fechada")
        except Exception as e:
            return ToolResult(False, "safe_start_engine", str(e)[:120])

    def safe_start_voice(self) -> ToolResult:
        if _port_open(8099):
            return ToolResult(True, "safe_start_voice", "Voice já em 8099")
        candidates = [
            self.root / "bridge" / "jarvis_voice_server.py",
            self.root / "voice" / "server.py",
            self.root / "engine" / "voice_server.py",
        ]
        script = next((p for p in candidates if p.exists()), None)
        if not script:
            return ToolResult(False, "safe_start_voice", "script voice ausente")
        try:
            self._spawn(script, script.parent)
            waited = self.wait_port(8099, timeout=5.0)
            ok = waited.ok or _port_open(8099)
            return ToolResult(ok, "safe_start_voice",
                              "Voice arrancado" if ok else "Voice iniciado mas porta ainda fechada")
        except Exception as e:
            return ToolResult(False, "safe_start_voice", str(e)[:120])

    def canary_ui_state(self) -> ToolResult:
        code, body = _http("http://127.0.0.1:8765/api/ui/state")
        if code != 200:
            return ToolResult(False, "canary_ui_state", f"ui/state HTTP {code}", {"code": code})
        has_view = False
        try:
            data = json.loads(body)
            snap = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else data
            view = snap.get("view") if isinstance(snap, dict) and isinstance(snap.get("view"), dict) else snap
            has_view = bool(isinstance(view, dict) and (view.get("home") or view.get("home_team")))
        except Exception:
            has_view = "home" in body.lower()
        return ToolResult(has_view, "canary_ui_state",
                          "view.home presente" if has_view else "sem view.home",
                          {"code": code, "has_view": has_view})

    def canary_trader_chat(self) -> ToolResult:
        """POST /api/trader/chat — efeito possivel no engine. Nao e read-only. Nunca inventa placar."""
        msg = "Liste corner_events com minuto e time"
        live = self.root / "bridge" / "live_latest.json"
        if live.exists() and live.stat().st_size > 10:
            try:
                data = json.loads(live.read_text(encoding="utf-8", errors="replace"))
                home = data.get("home") or data.get("home_team")
                away = data.get("away") or data.get("away_team")
                if home and away:
                    msg = f"Liste corner_events com minuto e time de {home} x {away}"
            except Exception:
                pass
        code, body = _http(
            "http://127.0.0.1:8765/api/trader/chat",
            timeout=8.0,
            method="POST",
            payload={"message": msg, "fixtureId": ""},
        )
        if code == 0:
            return ToolResult(False, "canary_trader_chat", f"chat unreachable: {body[:80]}")
        ok = code in (200, 400, 422)
        return ToolResult(ok, "canary_trader_chat", f"chat HTTP {code}",
                          {"code": code, "body": body[:200]})

    def read_live_latest(self) -> ToolResult:
        p = self.root / "bridge" / "live_latest.json"
        if not p.exists() or p.stat().st_size < 10:
            return ToolResult(False, "read_live_latest", "live_latest vazio/ausente")
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            home = data.get("home") or data.get("home_team")
            away = data.get("away") or data.get("away_team")
            age = int(time.time() - p.stat().st_mtime)
            ok = bool(home and away) and age <= 45
            msg = f"{home} x {away} age={age}s" if home and away else "sem times"
            return ToolResult(ok, "read_live_latest", msg,
                              {"home": home, "away": away, "age_s": age})
        except Exception as e:
            return ToolResult(False, "read_live_latest", str(e)[:100])

    def health_score(self) -> ToolResult:
        score = 0
        details: Dict[str, Any] = {}
        for name, port, weight in [("bridge", 8080, 22), ("engine", 8765, 26), ("voice", 8099, 4)]:
            if _port_open(port):
                score += weight
                details[name] = "up"
            else:
                details[name] = "down"
        code, _ = _http("http://127.0.0.1:8765/api/health")
        if code == 200:
            score += 12
            details["engine_health"] = "ok"
        can = self.canary_ui_state()
        if can.ok:
            score += 16
            details["ui_state"] = "ok"
        live = self.root / "bridge" / "live_latest.json"
        if live.exists() and live.stat().st_size > 10:
            age = time.time() - live.stat().st_mtime
            if age <= 45:
                score += 12
                details["live"] = "fresh"
            else:
                score += 4
                details["live"] = f"stale_{int(age)}s"
        if os.environ.get("PAPER_TRADE", "true").lower() == "true" and \
                os.environ.get("EXECUTION_ALLOWED", "false").lower() == "false":
            score += 8
            details["policy"] = "ok"
        score = min(100, score)
        return ToolResult(score >= 70, "health_score", f"score={score}",
                          {"score": score, "details": details})


    def wait_port(self, port: int = 8765, timeout: float = 15.0) -> ToolResult:
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            if _port_open(int(port)):
                return ToolResult(True, "wait_port", f"porta {port} OPEN", {"port": port})
            time.sleep(0.6)
        return ToolResult(False, "wait_port", f"timeout à espera da porta {port}", {"port": port})

    def ensure_venv(self) -> ToolResult:
        win_py = self.root / "engine" / "venv" / "Scripts" / "python.exe"
        nix_py = self.root / "engine" / "venv" / "bin" / "python"
        if win_py.exists() or nix_py.exists():
            return ToolResult(True, "ensure_venv", "venv já existe")
        engine = self.root / "engine"
        engine.mkdir(parents=True, exist_ok=True)
        bins = []
        if sys.platform == "win32":
            for spec in (("py", "-3.11"), ("py", "-3.10"), ("python",)):
                if shutil.which(spec[0]):
                    bins.append(list(spec))
        else:
            for name in ("python3.11", "python3.10", "python3", "python"):
                if shutil.which(name):
                    bins.append([name])
                    break
        last = "sem python no PATH"
        for spec in bins:
            cmd = spec + ["-m", "venv", str(engine / "venv")]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if r.returncode == 0 and (win_py.exists() or nix_py.exists()):
                    return ToolResult(True, "ensure_venv", f"venv criado via {' '.join(spec)}")
                last = (r.stderr or r.stdout or "")[:160]
            except Exception as e:
                last = str(e)[:160]
                break
        return ToolResult(False, "ensure_venv", f"falhou criar venv: {last}")

    def recycle_port(self, port: int = 8765) -> ToolResult:
        """Liberta ocupante da porta se health falhou. Não toca em 11434."""
        port = int(port)
        if port not in (8080, 8765, 8099, 8766):
            return ToolResult(False, "recycle_port", f"porta {port} fora da allowlist")
        if sys.platform == "win32":
            ps = (
                f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                "ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }"
            )
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=20)
            except Exception as e:
                return ToolResult(False, "recycle_port", str(e)[:120])
        else:
            try:
                subprocess.run(["bash", "-lc", f"fuser -k {port}/tcp || true"],
                               capture_output=True, text=True, timeout=10)
            except Exception:
                pass
        time.sleep(1.0)
        open_ = _port_open(port)
        return ToolResult(not open_, "recycle_port",
                          f"porta {port} {'livre' if not open_ else 'ainda ocupada'}",
                          {"port": port, "open": open_})

    def deep_diagnostic(self) -> ToolResult:
        code, body = _http("http://127.0.0.1:8765/api/diagnostics/deep", timeout=6.0)
        if code != 200:
            return ToolResult(False, "deep_diagnostic", f"HTTP {code}", {"code": code})
        return ToolResult(True, "deep_diagnostic", "diagnostics/deep OK", {"body": body[:300]})

    def acquire_lock(self) -> ToolResult:
        lock = self.root / "logs_supervisor" / "hermes.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.exists():
            try:
                age = time.time() - lock.stat().st_mtime
                if age < 90:
                    return ToolResult(False, "acquire_lock", f"outro Hermes activo ({int(age)}s)")
            except Exception:
                pass
        lock.write_text(str(os.getpid()), encoding="utf-8")
        return ToolResult(True, "acquire_lock", "lock adquirido")

    def release_lock(self) -> ToolResult:
        lock = self.root / "logs_supervisor" / "hermes.lock"
        try:
            if lock.exists():
                lock.unlink()
        except Exception:
            pass
        return ToolResult(True, "release_lock", "lock libertado")
