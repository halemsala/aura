"""Supervisor Agent Jarvis Mode — V23 autonomia contínua (paper-trade only)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("aura.supervisor_jarvis")

STALE_CAPTURE_SEC = 45.0
POLL_INTERVAL_SEC = 4.0


class JarvisSupervisor:
    """Loop contínuo: health Bridge/Engine/Voice/Ollama + freshness de captura.

    Nunca executa ordem real. execution_allowed permanece False.
    """

    def __init__(self) -> None:
        self.is_running = False
        self.state = "OFFLINE"
        self.global_state: Dict[str, Any] = {
            "services": {},
            "capture_stale": False,
            "last_capture_ts": None,
            "last_poll_ts": None,
        }
        self._task: Optional[asyncio.Task] = None
        self._http = None

    async def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.state = "STARTING"
        try:
            import httpx
            self._http = httpx.AsyncClient(timeout=2.5)
        except Exception:
            self._http = None
        self._task = asyncio.create_task(self._loop())
        logger.info("[Jarvis] Supervisor iniciado (poll=%.1fs stale=%.0fs)", POLL_INTERVAL_SEC, STALE_CAPTURE_SEC)

    async def stop(self) -> None:
        self.is_running = False
        self.state = "STOPPING"
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
        self.state = "OFFLINE"
        logger.info("[Jarvis] Supervisor parado")

    async def _loop(self) -> None:
        self.state = "OBSERVANDO"
        while self.is_running:
            # V23 kill switch — crie KILL_JARVIS.flag na raiz do pacote
            try:
                import os
                from pathlib import Path as _P
                _roots = [_P.cwd(), _P(__file__).resolve().parents[2], _P(__file__).resolve().parents[1]]
                if any((_r / 'KILL_JARVIS.flag').exists() for _r in _roots):
                    try:
                        import logging
                        logging.getLogger('aura.jarvis').critical('KILL SWITCH ATIVADO. Desligando Jarvis.')
                    except Exception:
                        pass
                    self.is_running = False if hasattr(self, 'is_running') else None
                    if hasattr(self, 'stop'):
                        try:
                            self.stop()
                        except Exception:
                            pass
                    break
            except Exception:
                pass
            try:
                await self._tick()
            except Exception as exc:
                logger.warning("[Jarvis] tick error: %s", exc)
                self.state = "ERRO"
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _tick(self) -> None:  # prefer gather for health checks
        services = {
            "bridge": await self._health("http://127.0.0.1:8080/health"),
            "engine": await self._health("http://127.0.0.1:8765/api/health"),
            "voice": await self._health("http://127.0.0.1:8099/api/voice/health"),
            "ollama": await self._health("http://127.0.0.1:11434/api/tags"),
        }
        self.global_state["services"] = services
        self.global_state["last_poll_ts"] = time.time()

        # Freshness via /api/ui/state (sem inventar dados)
        stale = True
        try:
            if self._http:
                r = await self._http.get("http://127.0.0.1:8765/api/ui/state")
                if r.status_code == 200:
                    body = r.json()
                    snap = body.get("snapshot") or {}
                    # aceita freshness_sec / capture_ts se existirem
                    freshness = snap.get("freshness_sec")
                    if freshness is not None:
                        stale = float(freshness) > STALE_CAPTURE_SEC
                    else:
                        ts = snap.get("ts") or snap.get("received_ts") or snap.get("timestamp")
                        if ts:
                            age = time.time() - float(ts)
                            stale = age > STALE_CAPTURE_SEC
                            self.global_state["last_capture_ts"] = float(ts)
                        else:
                            # sem snapshot = considerado stale
                            stale = not bool(snap)
        except Exception:
            stale = True

        self.global_state["capture_stale"] = stale
        if not all(services.values()):
            self.state = "DEGRADADO"
        elif stale:
            self.state = "BLOCKED_BY_DATA"
        else:
            self.state = "OBSERVANDO"

    async def _health(self, url: str) -> bool:
        if not self._http:
            return False
        try:
            r = await self._http.get(url)
            return r.status_code < 500
        except Exception:
            return False


# Instância global — referenciada por engine/server.py api_ui_state
jarvis_supervisor = JarvisSupervisor()
