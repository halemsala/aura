#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra â€” Chat API v2 (Final Integrada)
FastAPI + WebSocket + Memory + Digital Twin + Alert Manager + JWT Auth + Prometheus
"""
import os
import re
import sys
import json
import asyncio
import time
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

_HERMES_ROOT = Path(__file__).resolve().parent.parent
# Prefer package root that actually contains core/hermes_llm_engine.py
_aura = Path(os.getenv("AURA_ROOT", "") or ".")
for _cand in (_HERMES_ROOT, _aura / "hermes_v10", _aura):
    if (_cand / "core" / "hermes_llm_engine.py").is_file():
        _HERMES_ROOT = _cand.resolve()
        break
if str(_HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMES_ROOT))
if _aura.is_dir() and str(_aura) not in sys.path:
    sys.path.insert(0, str(_aura.resolve()))
os.chdir(str(_HERMES_ROOT))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
except ImportError:
    class _NoopMetric:
        def labels(self, *a, **k): return self
        def inc(self, *a, **k): pass
        def dec(self, *a, **k): pass
        def set(self, *a, **k): pass
        def observe(self, *a, **k): pass
        def time(self):
            from contextlib import contextmanager
            @contextmanager
            def _c():
                yield
            return _c()
    def Counter(*a, **k): return _NoopMetric()
    def Histogram(*a, **k): return _NoopMetric()
    def generate_latest(): return b""
    CONTENT_TYPE_LATEST = "text/plain"
    def Gauge(*a, **k): return _NoopMetric()

import os, sys
from pathlib import Path
# Bootstrap: resolve hermes package root that contains core/hermes_llm_engine.py
_HERE = Path(__file__).resolve().parent
_CANDIDATES = [
    _HERE.parent,  # hermes_v10/ when script is hermes_v10/scripts/
    _HERE.parent / "hermes_v10",
    Path(os.getenv("AURA_ROOT", "") or ".") / "hermes_v10",
    Path(os.getenv("AURA_ROOT", "") or "."),
    Path(r"C:\aura") / "hermes_v10",
    Path(r"C:\aura"),
]
_HERMES_ROOT = None
for _c in _CANDIDATES:
    try:
        if (_c / "core" / "hermes_llm_engine.py").is_file():
            _HERMES_ROOT = _c.resolve()
            break
    except Exception:
        pass
if _HERMES_ROOT is None:
    _HERMES_ROOT = (_HERE.parent).resolve()
if str(_HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMES_ROOT))
_aura = Path(os.getenv("AURA_ROOT", "") or r"C:\aura")
if _aura.is_dir() and str(_aura.resolve()) not in sys.path:
    sys.path.insert(0, str(_aura.resolve()))
try:
    os.chdir(str(_HERMES_ROOT))
except Exception:
    pass

# Soft imports: allow /health + operator chat even if optional core modules fail.
_HERMES_CORE_ERRORS: list = []

try:
    from core.hermes_llm_engine import HermesLLMEngine
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"hermes_llm_engine:{_e}")
    class HermesLLMEngine:  # type: ignore
        def __init__(self, *a, **k):
            self.available = False
        async def chat(self, *a, **k):
            return {"reply": "", "model": "offline", "error": "llm_engine_unavailable"}

try:
    from core.hermes_constitution_engine import ConstitutionEngine
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"constitution:{_e}")
    class ConstitutionEngine:  # type: ignore
        def __init__(self, *a, **k): pass
        def check(self, *a, **k): return True

try:
    from core.hermes_anomaly_detector import AnomalyDetector
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"anomaly:{_e}")
    class AnomalyDetector:  # type: ignore
        def __init__(self, *a, **k): self.score = 0.0
        def score_now(self, *a, **k): return 0.0

try:
    from core.hermes_self_healing import SelfHealingEngine
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"self_healing:{_e}")
    class SelfHealingEngine:  # type: ignore
        def __init__(self, *a, **k): pass

try:
    from core.hermes_memory_engine import MemoryEngine, MemoryEntry
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"memory:{_e}")
    class MemoryEntry:  # type: ignore
        def __init__(self, **k): self.__dict__.update(k)
    class MemoryEngine:  # type: ignore
        def __init__(self, *a, **k): self._items = []
        def add(self, *a, **k): pass
        def search(self, *a, **k): return []

try:
    from core.hermes_digital_twin import DigitalTwin
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"digital_twin:{_e}")
    class DigitalTwin:  # type: ignore
        def __init__(self, *a, **k): pass

try:
    from core.hermes_alert_manager import AlertManager
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"alert_manager:{_e}")
    class AlertManager:  # type: ignore
        def __init__(self, *a, **k): pass
        def recent(self, *a, **k): return []

try:
    from core.hermes_mcp_bridge import MCPBridge
except Exception as _e:  # noqa: BLE001
    _HERMES_CORE_ERRORS.append(f"mcp_bridge:{_e}")
    class MCPBridge:  # type: ignore
        def __init__(self, *a, **k): pass

try:
    from core.hermes_prompt_guard import build_safe_prompt, detect_injection
except ImportError:
    def build_safe_prompt(system_prompt, user_input, tool_outputs=None):
        return system_prompt
    def detect_injection(text):
        return None

if _HERMES_CORE_ERRORS:
    sys.stderr.write("[Hermes] core soft-import warnings: %s\n" % "; ".join(_HERMES_CORE_ERRORS[:8]))

# --- AURA patch: JSON-safe payloads (numpy.bool_ / numpy scalars) ---
def sanitize_payload(data):
    """Converte tipos numpy/nÃ£o-JSON em tipos Python nativos."""
    try:
        import numpy as np
        _np = True
    except Exception:
        _np = False
        np = None  # type: ignore
    if isinstance(data, dict):
        return {str(k): sanitize_payload(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [sanitize_payload(v) for v in data]
    if _np and isinstance(data, getattr(np, "bool_", bool)):
        return bool(data)
    if _np and isinstance(data, getattr(np, "generic", ())):
        try:
            return data.item()
        except Exception:
            return float(data) if hasattr(data, "dtype") else data
    if isinstance(data, Path):
        return str(data)
    return data


# â”€â”€â”€ MÃ©tricas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _metric(factory, name, documentation, labelnames=()):
    try:
        return factory(name, documentation, labelnames) if labelnames else factory(name, documentation)
    except ValueError:
        try:
            from prometheus_client import REGISTRY
            return REGISTRY._names_to_collectors.get(name) or factory(name, documentation)
        except Exception:
            return factory(name, documentation)

REQUEST_COUNT = _metric(Counter, "hermes_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = _metric(Histogram, "hermes_request_duration_seconds", "Request latency", ["endpoint"])
WS_CONNECTIONS = _metric(Counter, "hermes_websocket_connections_total", "WebSocket connections accepted")
WS_ACTIVE = _metric(Gauge, "hermes_websocket_connections", "Active WebSocket connections")
WS_MESSAGES = _metric(Counter, "hermes_websocket_messages_total", "WebSocket messages")
MEMORY_OPS = _metric(Counter, "hermes_memory_ops_total", "Memory operations", ["op"])

# â”€â”€â”€ Logger (stdlib-safe; evita kwargs structlog em logging.Logger) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
import logging
logging.basicConfig(level=logging.INFO)
_base_log = logging.getLogger("hermes.chat_api")

class _SafeLog:
    """Aceita logger.info("msg %s", x) e logger.info("msg", name=x) sem rebentar."""
    def _fmt(self, msg, args, kwargs):
        if kwargs:
            extra = " ".join("%s=%s" % (k, v) for k, v in kwargs.items())
            msg = "%s %s" % (msg, extra) if msg else extra
        if args:
            try:
                msg = msg % args
            except Exception:
                msg = "%s %s" % (msg, args)
        return msg
    def debug(self, msg, *a, **k): _base_log.debug(self._fmt(msg, a, k))
    def info(self, msg, *a, **k): _base_log.info(self._fmt(msg, a, k))
    def warning(self, msg, *a, **k): _base_log.warning(self._fmt(msg, a, k))
    def error(self, msg, *a, **k): _base_log.error(self._fmt(msg, a, k))
    def exception(self, msg, *a, **k): _base_log.exception(self._fmt(msg, a, k))

logger = _SafeLog()

# â”€â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_AURA = Path(os.getenv("AURA_ROOT", ".")).resolve()
_HERMES_PKG = Path(__file__).resolve().parent.parent
ROOT = _HERMES_PKG if (_HERMES_PKG / "hermes_config_ultra.json").exists() else _AURA
if not (ROOT / "hermes_config_ultra.json").exists() and (_AURA / "hermes_v10" / "hermes_config_ultra.json").exists():
    ROOT = _AURA / "hermes_v10"
API_PORT = int(os.getenv("HERMES_API_PORT", "8777"))
PAPER_TRADE = os.getenv("PAPER_TRADE", "true").lower() == "true"
EXECUTION_ALLOWED = os.getenv("EXECUTION_ALLOWED", "false").lower() == "true"
JWT_SECRET = os.getenv("HERMES_JWT_SECRET", secrets.token_hex(32))
AUTH_REQUIRED = os.getenv("HERMES_REQUIRE_AUTH", "0").strip() not in ("0", "false", "False", "")

# Pending confirmation of destructive chat actions (session_id -> intent)
_PENDING_AUTH: Dict[str, Dict[str, Any]] = {}
_RUNBOOK_CACHE = {"ts": 0.0, "text": ""}
_URLLIB_REQ = None


def _aura_root() -> Path:
    """Single root resolver used by alerts, runbook, gym, catalog and correct."""
    env = (os.getenv("AURA_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p
    try:
        cand = Path(__file__).resolve().parents[2]
        if cand.exists():
            return cand
    except Exception:
        pass
    if ROOT and Path(str(ROOT)).exists():
        # ROOT is hermes package; parent is AURA when layout is AURA/hermes_v10
        parent = Path(str(ROOT)).resolve().parent
        if (parent / "scripts").is_dir() or (parent / "engine").is_dir():
            return parent
        return Path(str(ROOT)).resolve()
    return Path(".").resolve()


def _iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _has_auth_token(message: str) -> bool:
    low = (message or "").lower()
    if re.search(r"\b(n[aÃ£]o|nunca|jamais|proib)\w*\s+(autoriz|permit)\w*", low):
        return False
    return bool(re.search(r"\b(autorizo|autorizado|eu\s+autorizo|com\s+autoriza[cÃ§][aÃ£]o)\b", low))


def _strip_auth_token(message: str) -> str:
    return re.sub(
        r"\b(autorizo|autorizado|eu\s+autorizo|com\s+autoriza[cÃ§][aÃ£]o)\b[:\s-]*",
        " ",
        message or "",
        flags=re.IGNORECASE,
    ).strip()


def _urllib():
    global _URLLIB_REQ
    if _URLLIB_REQ is None:
        import urllib.request as _u
        _URLLIB_REQ = _u
    return _URLLIB_REQ


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


def _mem_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time()*1000)}_{secrets.token_hex(4)}"


# â”€â”€â”€ Estado Global â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
engine: Optional[HermesLLMEngine] = None
constitution: Optional[ConstitutionEngine] = None
anomaly_detector: Optional[AnomalyDetector] = None
healing: Optional[SelfHealingEngine] = None
memory: Optional[MemoryEngine] = None
digital_twin: Optional[DigitalTwin] = None
alerts: Optional[AlertManager] = None
mcp: Optional[MCPBridge] = None
error_catalog = None  # type: ignore
AUTONOMY = None  # type: ignore

security = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, constitution, anomaly_detector, healing, memory, digital_twin, alerts, mcp, error_catalog, AUTONOMY

    # Arranque resiliente: falha de um componente nao derruba a API inteira
    try:
        engine = HermesLLMEngine(
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL") or os.getenv("AURA_OLLAMA_MODEL") or os.getenv("AURA_JARVIS_MODEL") or "qwen3:8b",
            openai_key=os.getenv("OPENAI_API_KEY"),
        )
    except Exception as exc:
        logger.error("llm_engine_init_failed error=%s", exc)
        engine = None

    def _safe(name, factory):
        try:
            return factory()
        except Exception as exc:
            logger.warning("component_skip name=%s error=%s", name, exc)
            return None

    constitution = _safe("constitution", lambda: ConstitutionEngine(root=str(ROOT)))
    anomaly_detector = _safe("anomaly", lambda: AnomalyDetector(root=str(ROOT)))
    healing = _safe("healing", lambda: SelfHealingEngine(root=str(ROOT)))
    memory = _safe("memory", lambda: MemoryEngine(root=str(ROOT)))
    digital_twin = _safe("digital_twin", lambda: DigitalTwin(root=str(ROOT)))
    alerts = _safe("alerts", lambda: AlertManager(root=str(ROOT)))
    mcp = _safe("mcp", lambda: MCPBridge(root=str(ROOT)))

    # Registra tools (so se engine OK)
    if engine is not None:
        try:
            from core.hermes_llm_engine import (
                tool_system_status, tool_read_file, tool_list_dir,
                tool_search_logs, tool_check_constitution,
            )
            engine.register_tool("system_status", tool_system_status, "Status do sistema", {"type": "object", "properties": {}})
            engine.register_tool("read_file", tool_read_file, "LÃª arquivo", {
                "type": "object", "properties": {"path": {"type": "string"}, "root": {"type": "string"}},
                "required": ["path"],
            })
            engine.register_tool("list_dir", tool_list_dir, "Lista diretÃ³rio", {
                "type": "object", "properties": {"path": {"type": "string"}, "root": {"type": "string"}},
            })
            engine.register_tool("search_logs", tool_search_logs, "Busca em logs", {
                "type": "object",
                "properties": {"keyword": {"type": "string"}, "root": {"type": "string"}, "max_lines": {"type": "integer"}},
                "required": ["keyword"],
            })
            engine.register_tool("check_constitution", tool_check_constitution, "Verifica constituiÃ§Ã£o", {
                "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
            })
        except Exception as _exc:
            logger.warning("std_tools_skip error=%s", _exc)
        try:
            import sys as _sys
            from pathlib import Path as _P
            _root = _P(__file__).resolve().parents[2]
            _scripts = _root / "scripts"
            if str(_scripts) not in _sys.path:
                _sys.path.insert(0, str(_scripts))
            import aura_chat_agents as _ag

            async def _t_status():
                return _ag.status_text()

            async def _t_diagnose():
                return _ag.deep_diagnose()

            async def _t_restart(service: str = "engine"):
                return _ag.restart_service(service)

            async def _t_fix():
                return _ag.fix_common()

            async def _t_desktop():
                return _ag.open_desktop()

            async def _t_gpu(pct: int = 0):
                if pct and int(pct) >= 20:
                    return _ag.set_gpu_cap(int(pct))
                return _ag.gpu_status()

            engine.register_tool("aura_status", _t_status, "Status das portas AURA e fixture", {"type": "object", "properties": {}})
            engine.register_tool("aura_diagnose", _t_diagnose, "Diagnostico profundo AURA", {"type": "object", "properties": {}})
            engine.register_tool("aura_restart", _t_restart, "Reinicia servico AURA (bridge|engine|matriz|hermes|voice|all). Nunca mata Ollama.", {
                "type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"],
            })
            engine.register_tool("aura_fix", _t_fix, "Reparo seguro: libera portas AURA e sobe OFF", {"type": "object", "properties": {}})
            engine.register_tool("aura_desktop", _t_desktop, "Abre Desktop AURA ou Matriz", {"type": "object", "properties": {}})
            engine.register_tool("aura_gpu", _t_gpu, "Estado ou limite GPU dedicada (pct 20-100)", {
                "type": "object", "properties": {"pct": {"type": "integer"}},
            })
        except Exception as _tool_exc:
            logger.warning("aura_operator_tools_skip error=%s", _tool_exc)

    if digital_twin is not None:
        try:
            from core.hermes_digital_twin import sim_domain_lock, sim_rotate_logs
            digital_twin.register_simulator("domain_lock", sim_domain_lock)
            digital_twin.register_simulator("rotate_logs", sim_rotate_logs)
        except Exception as _exc:
            logger.warning("digital_twin_skip error=%s", _exc)
    if healing is not None:
        try:
            from core.hermes_self_healing import handler_domain_lock, handler_rotate_logs, handler_set_execution_false
            healing.register_handler("domain_lock", handler_domain_lock)
            healing.register_handler("rotate_logs", handler_rotate_logs)
            healing.register_handler("set_execution_false", handler_set_execution_false)
        except Exception as _exc:
            logger.warning("healing_skip error=%s", _exc)

    logger.info("hermes_v10_startup_complete root=%s paper_trade=%s", str(ROOT), PAPER_TRADE)
    # Restaura watcher se estava activo
    try:
        import sys as _s
        _sc = str(Path(os.getenv("AURA_ROOT", str(ROOT))).resolve() / "scripts")
        if _sc not in _s.path:
            _s.path.insert(0, _sc)
        import aura_game_watch as _gw
        _st = _gw._load()
        if _st.get("enabled"):
            _gw.start_watch(voice_alerts=bool(_st.get("voice_alerts")))
            logger.info("game_watch_restored voice=%s", _st.get("voice_alerts"))
    except Exception as _gw_exc:
        logger.warning("game_watch_restore_skip error=%s", _gw_exc)
    try:
        import sys as _s2
        _sc2 = str(Path(os.getenv("AURA_ROOT", str(ROOT))).resolve() / "scripts")
        if _sc2 not in _s2.path:
            _s2.path.insert(0, _sc2)
        import aura_watchdog as _awd
        _awd.start_watchdog(auto_repair=True)
        logger.info("watchdog_started")
    except Exception as _wd_exc:
        logger.warning("watchdog_skip error=%s", _wd_exc)


    # Error Catalog (KEDB)
    try:
        import sys as _sys
        _ar = Path(os.getenv("AURA_ROOT", ".")).resolve()
        if str(_ar) not in _sys.path:
            _sys.path.insert(0, str(_ar))
        if str(_ar / "core") not in _sys.path:
            _sys.path.insert(0, str(_ar / "core"))
        from aura_error_catalog import ErrorCatalog
        error_catalog = ErrorCatalog(root=str(_ar))
        def _reg_handlers():
            try:
                ag = _load_agents()
                error_catalog.register_fix("E-NET-004", lambda: ag.restart_service("engine"))
                error_catalog.register_fix("E-NET-003", lambda: ag.restart_service("bridge"))
                error_catalog.register_fix("E-NET-005", lambda: ag.restart_service("matriz"))
                error_catalog.register_fix("E-NET-006", lambda: ag.fix_common())
                error_catalog.register_fix("restart_engine", lambda: ag.restart_service("engine"))
                error_catalog.register_fix("restart_bridge", lambda: ag.restart_service("bridge"))
                error_catalog.register_fix("restart_matriz", lambda: ag.restart_service("matriz"))
                error_catalog.register_fix("fix_common", lambda: ag.fix_common())
            except Exception:
                pass
        _reg_handlers()
        logger.info("error_catalog_loaded entries=%s", len(error_catalog.entries))
        try:
            from core.aura_autonomy import AutonomyEngine
            global AUTONOMY
            _aroot = _aura_root()
            AUTONOMY = AutonomyEngine(
                catalog=error_catalog,
                alerts=alerts,
                memory=memory,
                root=str(_aroot),
                load_agents=_load_agents,
            )
            AUTONOMY.start()
            logger.info("autonomy_engine_started")
        except Exception as _au_exc:
            logger.warning("autonomy_engine_skip error=%s", _au_exc)

        # â”€â”€â”€ AURA GYM â€” auto-treino no primeiro boot + refresh â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Nunca bloqueia a API. Simulador only. Usa o mesmo error_catalog.
        try:
            import threading as _gym_threading

            def _run_gym_background():
                try:
                    _groot = Path(os.getenv("AURA_ROOT") or str(Path(__file__).resolve().parents[2]))
                    if str(_groot) not in sys.path:
                        sys.path.insert(0, str(_groot))
                    from core.aura_gym import GymTrainer, distill_playbooks, export_alpaca_dataset

                    gym_ledger = _groot / "logs_supervisor" / "gym_ledger.jsonl"
                    first_run = (not gym_ledger.exists()) or gym_ledger.stat().st_size < 100
                    n_scen = 500 if first_run else 200
                    logger.info(
                        "gym_%s_training starting (%s scenarios)",
                        "first_boot" if first_run else "daily_refresh",
                        n_scen,
                    )
                    trainer = GymTrainer(
                        catalog=error_catalog,
                        ledger=str(gym_ledger),
                        root=str(_groot),
                    )
                    report = trainer.run_session(n=n_scen)
                    logger.info("gym_session_complete %s", report)
                    playbooks = distill_playbooks(str(gym_ledger))
                    logger.info("gym_playbooks_distilled count=%s", len(playbooks))
                    if gym_ledger.exists():
                        nlines = sum(1 for _ in gym_ledger.open("r", encoding="utf-8", errors="ignore"))
                        if nlines > 1000:
                            nexp = export_alpaca_dataset(str(gym_ledger))
                            logger.info("gym_dataset_exported records=%s alpaca=%s", nlines, nexp)
                except Exception as _gym_exc:
                    logger.warning("gym_background_skip error=%s", _gym_exc)

            _gym_threading.Thread(
                target=_run_gym_background, daemon=True, name="aura-gym-boot"
            ).start()
            logger.info("gym_background_thread_started")

            # Scheduler diÃ¡rio ~06:00 (refresh, nÃ£o bloqueia event loop)
            async def _gym_daily_scheduler():
                while True:
                    try:
                        now = datetime.now()
                        next_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
                        if next_6am <= now:
                            next_6am = next_6am + timedelta(days=1)
                        wait_s = (next_6am - now).total_seconds()
                        await asyncio.sleep(wait_s)
                        _gym_threading.Thread(
                            target=_run_gym_background, daemon=True, name="aura-gym-daily"
                        ).start()
                    except Exception as _sch_exc:
                        logger.warning("gym_scheduler_error %s", _sch_exc)
                        await asyncio.sleep(3600)

            try:
                asyncio.get_event_loop().create_task(_gym_daily_scheduler())
            except Exception:
                pass
        except Exception as _gym_boot_exc:
            logger.warning("gym_boot_skip error=%s", _gym_boot_exc)
    except Exception as _ec_exc:
        error_catalog = None
        logger.warning("error_catalog_skip error=%s", _ec_exc)

    yield

    if engine:
        await engine.close()
    if mcp:
        await mcp.close()

app = FastAPI(
    title="Hermes V10 Ultra API",
    version="10.1.1-ULTRA-AUDIT47",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("HERMES_DEBUG") else None,
    redoc_url="/redoc" if os.getenv("HERMES_DEBUG") else None,
)

# â”€â”€â”€ Middleware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_LOCAL_ORIGINS = [
    "http://127.0.0.1:8777",
    "http://localhost:8777",
    "http://127.0.0.1:8778",
    "http://localhost:8778",
    "http://127.0.0.1:8766",
    "http://localhost:8766",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

# Rate limiting + mÃ©tricas
_rate_limit_store: Dict[str, List[float]] = {}
RATE_LIMIT = 60

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    # localhost / operador local â€” sem rate limit agressivo (evita Failed to fetch)
    if client in ("127.0.0.1", "::1", "localhost", "unknown"):
        start = time.time()
        response = await call_next(request)
        try:
            duration = time.time() - start
            REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
            REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
        except Exception:
            pass
        return response
    now = time.time()
    _rate_limit_store.setdefault(client, [])
    _rate_limit_store[client] = [t for t in _rate_limit_store[client] if now - t < 60]
    if len(_rate_limit_store[client]) >= RATE_LIMIT:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    _rate_limit_store[client].append(now)

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    return response

# â”€â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")
    token = credentials.credentials
    # Simples HMAC verification (em produÃ§Ã£o, use JWT library)
    expected = hashlib.sha256(f"hermes:{JWT_SECRET}".encode()).hexdigest()[:32]
    if not secrets.compare_digest(token[:32], expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    return token


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


async def require_local_or_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Loopback operator UI stays usable; non-local clients need HERMES token."""
    if _is_loopback(request) and not AUTH_REQUIRED:
        return "loopback"
    return await verify_token(credentials)


def _aura_service_catalog() -> str:
    """Catalogo fixo dos servicos AURA â€” nunca inventar portas a partir do codigo."""
    rows = [
        ("8080", "Bridge", "http://127.0.0.1:8080/health", "ingestao feed"),
        ("8765", "Engine", "http://127.0.0.1:8765/api/health", "analise / risk / API"),
        ("8766", "Matriz / Hub", "http://127.0.0.1:8766/tools-hub.html", "UI operador"),
        ("8777", "Hermes", "http://127.0.0.1:8777/health", "chat / ops"),
        ("8790", "Control API", "http://127.0.0.1:8790/health", "painel tools-hub"),
        ("8099", "Voice", "http://127.0.0.1:8099/api/voice/health", "STT/TTS"),
        ("11434", "Ollama", "http://127.0.0.1:11434/api/tags", "LLM local"),
    ]
    lines = [
        "Servicos AURA (catalogo oficial â€” paper_trade=true, execution_allowed=false):",
        "",
        "| Porta  | Servico      | Health | Funcao |",
        "|--------|--------------|--------|--------|",
    ]
    for port, name, health, fn in rows:
        lines.append(f"| {port:6} | {name:12} | {health} | {fn} |")
    lines += [
        "",
        "Notas:",
        "- Numeros tipo 1024/5555/6379 no codigo NAO sao servicos AURA a ativar.",
        "- Voz OK na porta != TTS a falar: valide /api/voice/health e logs_supervisor\\voice.log.",
        "- Para subir stack: AURA_SUBIR_STACK_PAPER.bat | voz: AURA_SUBIR_VOZ.bat / AURA_INSTALAR_VOZ.bat",
        "- Comandos uteis: status | diagnostico | programador | reinicia engine | voz status",
    ]
    return "\n".join(lines)


def _wants_service_catalog(low: str) -> bool:
    keys = (
        "liste todas", "listar todas", "lista todas", "catalogar", "catalogue",
        "portas desconhec", "servicos desconhec", "serviÃ§os desconhec",
        "todas as portas", "todos os servicos", "todos os serviÃ§os",
        "liste os servicos", "liste os serviÃ§os", "liste servicos", "liste serviÃ§os",
        "ferramentas", "que portas", "quais portas", "quais servicos", "quais serviÃ§os",
    )
    if any(k in low for k in keys):
        return True
    if re.search(r"\b(portas?|servi[cÃ§]os?)\b", low) and re.search(r"\b(list|tod|ativ|catalog)", low):
        return True
    return False


def _wants_voice_diag(low: str) -> bool:
    return bool(re.search(
        r"^\s*(voz|voice)\s*(status|diag|diagnostico|health|teste|test)?\s*$",
        low,
    ) or low.strip() in ("voz status", "voice status", "status voz", "diagnostico voz", "testar voz"))


def _voice_diag_sync() -> str:
    import urllib.request
    lines = ["Diagnostico VOZ AURA (paper-only):"]
    for url in (
        "http://127.0.0.1:8099/api/voice/health",
        "http://127.0.0.1:8099/health",
        "http://127.0.0.1:8099/api/health",
    ):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as r:
                body = r.read()[:800].decode("utf-8", "replace")
            lines.append(f"OK {url}")
            lines.append(body)
        except Exception as e:
            lines.append(f"OFF {url} â€” {e}")
    logp = Path(os.getenv("AURA_ROOT", "C:\\aura")) / "logs_supervisor" / "voice.log"
    if logp.is_file():
        try:
            tail = logp.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
            lines.append("voice.log (tail):")
            lines.extend(tail)
        except Exception as e:
            lines.append(f"voice.log legivel? {e}")
    else:
        lines.append(f"Sem log em {logp} â€” suba com AURA_SUBIR_VOZ.bat")
    lines.append("Instalar/reparar: AURA_INSTALAR_VOZ.bat depois AURA_SUBIR_VOZ.bat")
    return "\n".join(lines)


# â”€â”€â”€ Modelos Pydantic â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    stream: bool = False
    use_memory: bool = True

class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: float
    timestamp: str
    session_id: str
    memory_used: bool = False
    suggestions: List[str] = []
    alerts: List[str] = []

class CorrectRequest(BaseModel):
    code: str = Field(..., pattern=r"^(domain_lock|fix_desktop_json|train_v9|run_v9_max|run_swarm|run_supervisor|run_deep|full_stack|status|latest|rotate_logs|set_execution_false|restart_api|clear_cache)$")
    target: Optional[str] = "."
    confidence: float = Field(0.9, ge=0.0, le=1.0)
    simulate_first: bool = True

class SimulateRequest(BaseModel):
    action_type: str
    params: Dict[str, Any] = {}
    depth: int = Field(2, ge=1, le=3)

class FSReadRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)

    @field_validator("path")
    @classmethod
    def _safe_read_path(cls, v: str) -> str:
        s = (v or "").replace("\\", "/")
        if ".." in s:
            raise ValueError("path traversal blocked")
        if s.startswith("/") or (len(s) >= 2 and s[1] == ":"):
            raise ValueError("absolute path blocked")
        if not re.match(r"^[a-zA-Z0-9_/.\\-]+$", v or ""):
            raise ValueError("path has invalid characters")
        return v


class FSListRequest(BaseModel):
    path: str = Field(default=".", min_length=0, max_length=512)

    @field_validator("path")
    @classmethod
    def _safe_list_path(cls, v: str) -> str:
        s = (v or "").replace("\\", "/")
        if ".." in s:
            raise ValueError("path traversal blocked")
        if s.startswith("/") or (len(s) >= 2 and s[1] == ":"):
            raise ValueError("absolute path blocked")
        if v and not re.match(r"^[a-zA-Z0-9_/.\\-]*$", v):
            raise ValueError("path has invalid characters")
        return v


class MemoryStoreRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    role: str = "user"
    source: str = "api"
    tags: List[str] = []

# â”€â”€â”€ Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _system_snapshot():
    cpu = mem = disk = None
    try:
        import psutil
        cpu = float(psutil.cpu_percent(interval=0.05))
        mem = float(psutil.virtual_memory().percent)
        disk = float(psutil.disk_usage("C:\\" if os.name == "nt" else "/").percent)
    except Exception:
        pass
    ollama_ok = False
    ollama_ms = None
    ollama_model = os.getenv("AURA_OLLAMA_MODEL") or os.getenv("AURA_JARVIS_MODEL") or os.getenv("CORNERAI_CHAT_MODEL") or "qwen3:8b"
    try:
        t0 = time.time()
        _u = _urllib()
        req = _u.Request(
            "http://127.0.0.1:11434/api/tags", headers={"Accept": "application/json"}
        )
        with _u.urlopen(req, timeout=5.0) as resp:
            raw = resp.read()
        ollama_ok = True
        ollama_ms = int((time.time() - t0) * 1000)
        try:
            names = [m.get("name") for m in (__import__("json").loads(raw).get("models") or []) if isinstance(m, dict)]
            if names:
                want = (os.getenv("AURA_OLLAMA_MODEL") or os.getenv("AURA_JARVIS_MODEL") or os.getenv("OLLAMA_MODEL") or "qwen3:8b")
                ollama_model = next((n for n in names if want in str(n)), names[0])
        except Exception:
            pass
    except Exception:
        ollama_ok = False
    return {
        "cpu": cpu,
        "memory": mem,
        "disk": disk,
        "ollama_ok": ollama_ok,
        "ollama_ms": ollama_ms,
        "model": ollama_model,
    }



_anomaly_cache = {"ts": 0.0, "data": (False, 0.0)}

def _cached_anomaly(max_age: float = 60.0):
    """detect() no maximo 1x/min â€” impede poll do dashboard de poluir o historico."""
    now = time.time()
    if now - float(_anomaly_cache["ts"]) > max_age:
        try:
            if anomaly_detector:
                is_a, score, _ = anomaly_detector.detect()
                _anomaly_cache["data"] = (bool(is_a), float(score or 0.0))
            else:
                _anomaly_cache["data"] = (False, 0.0)
        except Exception:
            _anomaly_cache["data"] = (False, 0.0)
        _anomaly_cache["ts"] = now
    return _anomaly_cache["data"]


@app.get("/health")
async def health():
    """Health minimalista + dados opcionais. Nunca propaga numpy; nunca 500 por anomalia."""
    env_safe, env_violations = True, []
    is_anomaly, score = False, 0.0
    try:
        if constitution:
            env_safe, env_violations = constitution.check_environment_invariants()
            env_safe = bool(env_safe)
            env_violations = [str(x) for x in (env_violations or [])]
    except Exception as exc:
        env_safe, env_violations = False, [str(exc)]
    try:
        is_anomaly, score = _cached_anomaly(60.0)
        is_anomaly = bool(is_anomaly)
        score = float(score or 0.0)
    except Exception:
        is_anomaly, score = False, 0.0
    try:
        snap = _system_snapshot()
    except Exception:
        snap = {"cpu": None, "memory": None, "disk": None, "ollama_ok": False, "ollama_ms": None, "model": "unknown"}
    payload = {
        "status": "ok" if (env_safe and not is_anomaly) else "degraded",
        "ok": True,
        "paper_trade": bool(PAPER_TRADE),
        "execution_allowed": bool(EXECUTION_ALLOWED),
        "env_safe": bool(env_safe),
        "env_violations": list(env_violations or []),
        "anomaly_detected": bool(is_anomaly),
        "anomaly_score": round(float(score or 0), 4),
        "cpu": snap.get("cpu"),
        "memory": snap.get("memory"),
        "disk": snap.get("disk"),
        "ollama_ok": bool(snap.get("ollama_ok")),
        "ollama_ms": snap.get("ollama_ms"),
        "model": snap.get("model"),
        "glm_enabled": False,
        "hermes_llm": True,
        "timestamp": _iso_utc(),
    }
    return sanitize_payload(payload)


@app.get("/health/live")
async def health_live():
    """Liveness puro â€” nunca falha, sem anomalia/psutil."""
    return {"status": "ok", "ok": True, "hermes_llm": True, "glm_enabled": False}



@app.get("/api/system")
async def api_system():
    snap = _system_snapshot()
    h = await health()
    if isinstance(h, dict):
        h.update(snap)
        h["glm_enabled"] = False
        h["hermes_llm"] = True
        return sanitize_payload(h)
    return sanitize_payload({"ok": True, **snap, "glm_enabled": False, "hermes_llm": True})


@app.get("/api/diagnose")
async def coded_diagnose():
    """Diagnostico completo com codigos de erro e localizacao."""
    evidence = {"snapshot": _system_snapshot()}
    try:
        ag = _load_agents()
        evidence["port_status"] = await asyncio.to_thread(ag.status_text)
    except Exception as e:
        evidence["port_status"] = f"status_unavailable: {e}"
    # tail logs
    try:
        log_dir = _aura_root() / "logs_supervisor"
        tails = []
        if log_dir.exists():
            for f in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:4]:
                try:
                    tails.append(f.name + ":\n" + f.read_text(encoding="utf-8", errors="ignore")[-4000:])
                except Exception:
                    pass
        evidence["log_tail"] = "\n".join(tails)[:12000]
    except Exception:
        evidence["log_tail"] = ""
    if error_catalog:
        diag = error_catalog.diagnose(evidence)
        return sanitize_payload({
            "diagnosis": diag,
            "formatted": error_catalog.format_for_chat(diag),
            "coverage_24h": error_catalog.coverage(24),
            "pending_triage": len(error_catalog.pending_triage()),
        })
    return {"error": "catalog_unavailable", "snapshot": evidence.get("snapshot")}


@app.get("/api/allowlist")
async def allowlist():
    from agents.hermes_correction_agent_llm import CorrectionAgent
    return {
        "allowlist": CorrectionAgent.ALLOWLIST,
        "paper_trade_enforced": PAPER_TRADE,
        "execution_blocked": not EXECUTION_ALLOWED,
    }

def _local_chat_fallback(message: str) -> str:
    return (
        "Hermes local no ar (fallback sem Ollama). "
        "paper_trade=true, execution_allowed=false. "
        "Abra a Matriz F1 e SokkerPRO F2 para fixture real. "
        "Pedido: " + (message or "")[:240]
    )


def _ping(url, timeout=2.0):
    try:
        _u = _urllib()
        req = _u.Request(url, headers={"Accept": "application/json"})
        with _u.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception:
        return 0, ""


def _load_agents():
    import sys
    root = _aura_root()
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import aura_chat_agents as _ag
    return _ag


def _chat_suggestions(message: str, reply: str) -> List[str]:
    """Botoes de resposta rapida conforme contexto."""
    low = (message or "").lower()
    base = ["status", "diagnostico", "corrige", "reinicia engine", "abra desktop", "ativa agentes"]
    if reply and "AUTORIZO" in (reply or "").upper():
        base = ["AUTORIZO", "cancelar", "status"] + base
    if any(k in low for k in ("jogo", "partida", "fixture", "analisa")):
        base = ["analisa a partida", "acompanha o jogo", "status", "corrige"] + base
    if any(k in low for k in ("engine", "offline", "off", "verde", "carrega")):
        base = ["reinicia engine", "corrige", "fecha e abre", "abra desktop", "status"] + base
    if any(k in low for k in ("autorizo", "apagar", "delete")):
        base = ["AUTORIZO corrige", "cancelar", "status"] + base
    # unique preserve order
    seen, out = set(), []
    for b in base:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out[:8]


def _read_recent_alerts(n: int = 5) -> List[str]:
    n = max(1, min(int(n or 5), 50))
    fp = _aura_root() / "logs_supervisor" / "aura_alerts.jsonl"
    if not fp.exists():
        return []
    try:
        size = fp.stat().st_size
        with fp.open("rb") as fh:
            if size > 65536:
                fh.seek(max(0, size - 65536))
                blob = fh.read()
                if b"\n" in blob:
                    blob = blob.split(b"\n", 1)[-1]
            else:
                blob = fh.read()
        lines = blob.decode("utf-8", "ignore").splitlines()[-n:]
        out = []
        for ln in lines:
            try:
                d = json.loads(ln)
                out.append(str(d.get("text") or d.get("msg") or ln)[:200])
            except Exception:
                out.append(ln[:200])
        return out
    except Exception:
        return []


def _operator_reply(message: str) -> str:

    """Acoes reais do sistema (reinicio, gpu, desktop, diag). None/vazio = conversar."""
    try:
        ag = _load_agents()
        out = ag.handle_operator_intent(message or "")
        if out:
            return out
    except Exception as exc:
        low = (message or "").lower()
        if any(k in low for k in ("reinic", "gpu", "desktop", "diagnost", "corrig", "agente")):
            return "Operador local falhou: %s. Tenta: status | diagnostico profundo | reinicia engine." % exc
    return ""


def _live_context_block() -> str:
    """Bloco factual injectado no system prompt (portas + fixture reais)."""
    try:
        ag = _load_agents()
        return ag.status_text()
    except Exception:
        b, _ = _ping("http://127.0.0.1:8080/health", timeout=1.0)
        e, _ = _ping("http://127.0.0.1:8765/api/health", timeout=1.0)
        m, _ = _ping("http://127.0.0.1:8766/health", timeout=1.0)
        o, _ = _ping("http://127.0.0.1:11434/api/tags", timeout=5.0)
        return (
            "AURA paper-trade | exec bloqueada. "
            "Bridge {0} | Engine {1} | Matriz {2} | Hermes OK | Ollama {3}.".format(
                "OK" if b else "OFF", "OK" if e else "OFF", "OK" if m else "OFF", "OK" if o else "OFF",
            )
        )


def _execute_tool_dump(raw: str, message: str) -> str:
    """Se o LLM so vomitou JSON de tool, NAO executa acao destrutiva sem AUTORIZO."""
    import json as _json
    data = None
    try:
        data = _json.loads(raw.strip())
    except Exception:
        import re as _re
        m = _re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw)
        if not m:
            return ""
        try:
            data = _json.loads(m.group(0))
        except Exception:
            return ""
    if not isinstance(data, dict):
        return ""
    name = str(data.get("name") or data.get("tool") or "").strip().lower()
    params = data.get("parameters") or data.get("arguments") or {}
    if not isinstance(params, dict):
        params = {}
    destructive = name in ("aura_fix", "fix", "fix_common", "aura_restart", "restart", "aura_gpu")
    if destructive and not _has_auth_token(message):
        return (
            f"Tool {name} bloqueada sem AUTORIZO. "
            f"Repete com: AUTORIZO {name}"
        )
    allowed_svc = {"bridge", "engine", "matriz", "hermes", "voice", "voz", "all", "core", "tudo"}
    try:
        ag = _load_agents()
        if name in ("aura_fix", "fix", "fix_common"):
            return ag.handle_operator_intent(message) or ag.fix_common()
        if name in ("aura_status", "system_status", "status"):
            return ag.status_text()
        if name in ("aura_diagnose", "diagnose"):
            return ag.deep_diagnose()
        if name in ("aura_restart", "restart"):
            svc = str(params.get("service") or "engine").strip().lower()
            if svc not in allowed_svc:
                return f"Servico nao permitido no restart: {svc}"
            return ag.restart_service(svc)
        if name in ("aura_desktop", "desktop"):
            return ag.open_desktop()
        if name in ("aura_gpu", "gpu"):
            pct = params.get("pct") or 0
            try:
                pct_i = int(pct)
            except Exception:
                pct_i = 0
            pct_i = max(0, min(100, pct_i))
            if pct_i >= 20:
                return ag.set_gpu_cap(pct_i)
            return ag.gpu_status()
    except Exception as exc:
        return f"Tool {name} falhou: {exc}"
    return _operator_reply(message) or ""


def _sanitize_llm(text: str, message: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    # Dump de tool-call em texto (modelo fraco)
    if raw.startswith("{") or ('"name"' in raw and "aura_" in raw.lower()):
        executed = _execute_tool_dump(raw, message)
        if executed:
            return executed
    if raw.startswith("{") and ("system_status" in raw or "search_logs" in raw or "aura_" in raw):
        return _operator_reply(message) or _live_context_block()
    low = raw.lower()
    bad = (
        "nao posso ajudar", "nÃ£o posso ajudar", "desculpe, mas nÃ£o posso",
        "credenciais", "/hermes on", "gerenciador de tarefas",
        "nÃ£o posso fornecer", "nao posso fornecer", "suporte tÃ©cnico",
        "suporte tecnico", "caminho de sistema", "c:\\usr\\local",
        "unix/linux", "atualize o sistema aura", "versÃ£o mais recente",
        "desculpe pelo", "para acessar o desktop", "porta aura: 200",
        "i cannot", "i'm sorry, but i", "as an ai",
    )
    if any(k in low for k in bad):
        op = _operator_reply(message)
        if op:
            return op
        return (
            _live_context_block()
            + "\n\nPosso diagnosticar, reiniciar servicos AURA (sem matar Ollama), "
            "ajustar GPU, abrir o Desktop e listar agentes. Diz o que precisas."
        )
    if len(raw) > 280 and any(k in low for k in ("windows", "caminho", "tutorial", "credencial", "task manager")):
        return _operator_reply(message) or _live_context_block()
    # Conversacional: permite respostas longas (ate ~1200 chars)
    if len(raw) > 1200:
        raw = raw[:1197] + "..."
    return raw



def _load_runbook() -> str:
    """Carrega RUNBOOK + mapa + trecho do catalogo (cache 60s, so 4k uteis)."""
    now = time.time()
    if _RUNBOOK_CACHE["text"] and (now - float(_RUNBOOK_CACHE["ts"])) < 60:
        return _RUNBOOK_CACHE["text"]
    root = _aura_root()
    chunks = []
    for rel in ("RUNBOOK_OPERACAO.md", "AURA_MAPA_DO_SISTEMA.md"):
        p = root / rel
        if p.exists():
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="ignore")[:4000])
            except Exception:
                pass
    cat = root / "core" / "aura_error_catalog.json"
    if cat.exists():
        try:
            data = json.loads(cat.read_text(encoding="utf-8"))
            raw_entries = data.get("entries", [])
            if isinstance(raw_entries, dict):
                iterable = list(raw_entries.values())[:20]
            else:
                iterable = list(raw_entries)[:20]
            lines = []
            for e in iterable:
                if not isinstance(e, dict):
                    continue
                fx = e.get("fix") or {}
                action = fx.get("action", "") if isinstance(fx, dict) else ""
                lines.append(f"{e.get('code')}: {e.get('title')} â†’ {action}")
            chunks.append("CATALOGO DE ERROS:\n" + "\n".join(lines))
        except Exception:
            pass
    out = "\n\n".join(chunks)[:4000]
    _RUNBOOK_CACHE["ts"] = now
    _RUNBOOK_CACHE["text"] = out
    return out


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatMessage):
    """Router explicito: 1 mensagem = 1 intencao = 1 caminho.
    Backend decide/executa; LLM explica com fatos. Sem cascata de remendos.
    """
    t0 = time.time()
    session_id = req.session_id or _mem_id("sess")
    msg = (req.message or "").strip()
    low = msg.lower()
    route, model, reply = "llm", "hermes", ""

    # Catalogo oficial â€” nao deixar o LLM inventar portas
    if _wants_service_catalog(low):
        return ChatResponse(
            reply=_aura_service_catalog(),
            model="aura:catalog",
            latency_ms=int((time.time() - t0) * 1000),
            timestamp=_iso_utc(),
            session_id=session_id,
            suggestions=["status", "diagnostico", "voz status", "programador"],
        )
    if _wants_voice_diag(low):
        return ChatResponse(
            reply=await asyncio.to_thread(_voice_diag_sync),
            model="aura:voice",
            latency_ms=int((time.time() - t0) * 1000),
            timestamp=_iso_utc(),
            session_id=session_id,
            suggestions=["AURA_SUBIR_VOZ.bat", "status", "diagnostico"],
        )

    # â”€â”€ CAMADA 0 â€” Operador humano WhatsApp/Telegram (macros fora do event loop) â”€â”€
    try:
        from bridge.jarvis.router.voice_skill_bridge import SKILL_BRIDGE
        skill_spoken = await asyncio.to_thread(SKILL_BRIDGE.handle, msg)
        if skill_spoken is not None:
            return ChatResponse(
                reply=skill_spoken,
                model="skill:operator",
                latency_ms=int((time.time() - t0) * 1000),
                timestamp=_iso_utc(),
                session_id=session_id,
                memory_used=False,
                suggestions=["confirmo", "cancela", "status"],
                alerts=await asyncio.to_thread(_read_recent_alerts, 5),
            )
    except Exception as _sk_exc:
        logger.warning("skill_bridge_skip error=%s", _sk_exc)

    FIX_CODE_RE = re.compile(r"^\s*(?:autorizo\s+|autoriso\s+)?fix\s+(e-[a-z]+-\d+)\s*$", re.IGNORECASE)
    mfix = FIX_CODE_RE.match(msg) if error_catalog else None
    if error_catalog and mfix:
        code = mfix.group(1).upper()
        entry = error_catalog.entries.get(code) or error_catalog.entries.get(code.lower()) or {}
        loc = (entry or {}).get("location", {}) if isinstance(entry, dict) else {}
        if not _has_auth_token(msg):
            preview = error_catalog.apply_fix(code, dry_run=True)
            reply = (
                f"{code} â€” simulacao (dry-run). Nao apliquei no sistema vivo.\n"
                f"Onde: {loc.get('file') or loc.get('service', '?')}\n"
                f"Plano: {json.dumps(preview, ensure_ascii=False)[:800]}\n"
                f"Para aplicar: AUTORIZO fix {code}"
            )
            return ChatResponse(
                reply=reply, model=f"catalog:{code}:dry",
                latency_ms=int((time.time() - t0) * 1000),
                timestamp=_iso_utc(),
                session_id=session_id, memory_used=False,
                suggestions=[f"AUTORIZO fix {code}", "cancelar", "status"],
                alerts=await asyncio.to_thread(_read_recent_alerts, 5),
            )
        result = await asyncio.to_thread(error_catalog.apply_fix, code, False)
        reply = (
            f"{code} â€” fix autorizado\n"
            f"Onde: {loc.get('file') or loc.get('service', '?')}\n"
            f"Resultado: {json.dumps(result, ensure_ascii=False)[:800]}"
        )
        try:
            if memory:
                await asyncio.to_thread(memory.store, MemoryEntry(
                    id=_mem_id(f"mem_{session_id}"),
                    ts=_iso_utc(),
                    role="user", content=msg[:2000], source="chat_api",
                    tags=["chat", session_id, "fix-code"],
                ))
                await asyncio.to_thread(memory.store, MemoryEntry(
                    id=_mem_id(f"mem_{session_id}_r"),
                    ts=_iso_utc(),
                    role="assistant", content=reply[:2000], source="chat_api",
                    tags=["chat", session_id, "fix-code"],
                ))
        except Exception:
            pass
        return ChatResponse(
            reply=reply, model=f"catalog:{code}",
            latency_ms=int((time.time() - t0) * 1000),
            timestamp=_iso_utc(),
            session_id=session_id, memory_used=bool(memory),
            suggestions=["status", "diagnostico", f"fix {code}"],
            alerts=await asyncio.to_thread(_read_recent_alerts, 5),
        )

    # Comando PURO: frase curta sÃ³ com a aÃ§Ã£o (ex: "status", "reinicia engine").
    # Perguntas longas com a palavra "status" vÃ£o para o LLM (conversa).
    ACTION_RE = re.compile(
        r"^\s*(?:autori[sz][oa]\s+|pode\s+|podes\s+)?"
        r"(corrige?|conserta?|arruma?|repara?|fix|diagn[oÃ³]stic\w*|diag|"
        r"status|estado|reinicia?|restart|religa?|abre?|abra?|gpu|placa)"
        r"(?:\s+(?:engine|bridge|matriz|hermes|voz|voice|all|tudo|desktop|o\s+desktop|a\s+matriz|[0-9]{2,3}%?))?"
        r"\s*$",
        re.IGNORECASE,
    )
    QUESTION_HINT_RE = re.compile(
        r"(\?|\bqual\b|\bquem\b|\bo\s+que\b|\bcomo\b|\bpor\s+que\b|\bporque\b|"
        r"\bexplica\b|\bme\s+diz\b|\bconte\b|\bpode\s+explicar\b|\bapresent)",
        re.IGNORECASE,
    )
    PROBLEM_RE = re.compile(
        r"(ca[iÃ­]u|caiu|offline|fora do ar|n[aÃ£]o (?:funciona|responde|abre|carrega|sobe)|"
        r"(?:deu|ocorreu|apareceu)\s+(?:um\s+)?(?:erro|error)|failed|falhou|falhando|quebrou|parou|travou|congelou|"
        r"\b(?:404|500)\b|fechou sozinho)",
        re.IGNORECASE,
    )

    def _is_pure_command(text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) > 80:
            return False
        if QUESTION_HINT_RE.search(t):
            return False
        return bool(ACTION_RE.match(t))

    def _sanitize_reply(text: str, mdl: str) -> str:
        """Corta alucinacoes comuns de modelos 3B sobre identidade (so AFIRMACAO)."""
        import re as _re
        s = (text or "").strip()
        if not s:
            return s
        bad = _re.compile(
            r"(desenvolvid[oa]\s+pela\s+microsoft|llm\s+da\s+microsoft|"
            r"plataforma\s+da\s+microsoft|produto\s+da\s+microsoft|"
            r"microsoft\s+copilot|sou\s+o\s+chatgpt|sou\s+o\s+copilot|"
            r"criado\s+pela\s+openai|modelo\s+da\s+openai|"
            r"sou\s+o\s+qwen|da\s+alibaba)",
            _re.IGNORECASE,
        )
        m = bad.search(s)
        if m:
            window = s[max(0, m.start() - 16): m.end() + 8]
            if _re.search(r"n[Ã£a]o\s+(sou|sou\s+o|perten[cÃ§]o|fui)", window, _re.IGNORECASE):
                return s  # negacao honesta â€” nao censurar
            return (
                f"Sou o Hermes, copiloto local do AURA QUANT-X (paper-trade no teu PC). "
                f"O modelo Ollama ativo e {mdl}. AURA nao e um produto Microsoft nem um LLM de nuvem."
            )
        return s

    try:
        # CAMADA 1 â€” COMANDO DIRETO (so se for comando puro)
        # cancelar confirmacao pendente
        if low.strip() in ("cancelar", "cancela", "cancel", "nao autorizo", "nÃ£o autorizo"):
            _PENDING_AUTH.pop(session_id, None)
            return ChatResponse(
                reply="Pedido pendente cancelado. Nenhuma acao destrutiva foi executada.",
                model="aura:gate", latency_ms=int((time.time() - t0) * 1000),
                timestamp=_iso_utc(), session_id=session_id, memory_used=False,
                suggestions=["status", "diagnostico"],
                alerts=await asyncio.to_thread(_read_recent_alerts, 5),
            )
        # AUTORIZO sozinho executa o pedido pendente
        if re.match(r"^\s*autori[sz][oa]\s*$", low) and session_id in _PENDING_AUTH:
            pending = _PENDING_AUTH.pop(session_id)
            msg = "AUTORIZO " + str(pending.get("command") or "corrige")
            low = msg.lower()

        # AUTONOMIA (maestro) â€” kill switch + relatorio
        if low.strip() in ("para autonomia", "desliga autonomia") or re.match(r"^\s*(?:autori[sz][oa]\s+)?(para|desliga|desativar)\s+autonomia\s*$", low):
            reply = await asyncio.to_thread(AUTONOMY.toggle, False) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["liga autonomia", "status"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))
        if low.strip() in ("liga autonomia", "ativa autonomia") or re.match(r"^\s*(?:autori[sz][oa]\s+)?(liga|ativa|ativar)\s+autonomia\s*$", low):
            if not _has_auth_token(msg):
                _PENDING_AUTH[session_id] = {"command": "liga autonomia", "ts": time.time()}
                reply = "Ligar autonomia (auto-fix) precisa de AUTORIZO. Envia: AUTORIZO liga autonomia"
                return ChatResponse(reply=reply, model="aura:autonomy:gate", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["AUTORIZO liga autonomia", "cancelar", "status"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))
            reply = await asyncio.to_thread(AUTONOMY.toggle, True) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["para autonomia", "autonomia"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))
        if low.strip() in ("autonomia", "relatorio autonomia", "relatÃ³rio autonomia") or re.match(r"^\s*autonomia\s*$", low):
            reply = await asyncio.to_thread(AUTONOMY.report) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["liga autonomia", "para autonomia"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))

        if low.strip() in ("modo manutencao", "modo manutenÃ§Ã£o", "entra manutencao", "entra manutenÃ§Ã£o") or re.match(
            r"^\s*(modo\s+manuten[cÃ§][aÃ£]o|entra\s+manuten[cÃ§][aÃ£]o)\s*$", low
        ):
            reply = await asyncio.to_thread(AUTONOMY.set_maintenance, True) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["sai do modo manutencao", "autonomia"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))
        if low.strip() in ("sai do modo manutencao", "sai do modo manutenÃ§Ã£o", "sai manutencao", "sai manutenÃ§Ã£o") or re.match(
            r"^\s*sai\s+(do\s+)?modo\s+manuten[cÃ§][aÃ£]o\s*$", low
        ):
            reply = await asyncio.to_thread(AUTONOMY.set_maintenance, False) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["modo manutencao", "autonomia"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))
        if low.strip() in ("postmortem", "post-mortem", "ultimo postmortem", "Ãºltimo postmortem") or re.match(
            r"^\s*(post[- ]?mortem|ultimo\s+post[- ]?mortem)\s*$", low
        ):
            reply = await asyncio.to_thread(AUTONOMY.last_postmortem) if AUTONOMY else "Autonomia indisponivel."
            return ChatResponse(reply=reply, model="aura:autonomy", latency_ms=int((time.time() - t0) * 1000), timestamp=_iso_utc(), session_id=session_id, memory_used=False, suggestions=["autonomia", "status"], alerts=await asyncio.to_thread(_read_recent_alerts, 5))

        # AURA GYM â€” treino offline no simulador (nunca no sistema vivo)
        if low.strip() in ("gym", "treinar gym", "academia", "aura gym") or re.match(
            r"^\s*(gym|treinar\s+gym|academia|aura\s+gym)(\s+\d+)?\s*$", low
        ):
            try:
                n_match = re.search(r"(\d+)", low)
                n_scen = min(int(n_match.group(1)), 200) if n_match else 50
                from core.aura_gym import GymTrainer, distill_playbooks
                _aroot = _aura_root()
                def _run_gym():
                    t = GymTrainer(catalog=error_catalog, root=str(_aroot))
                    rep = t.run_session(n=n_scen)
                    pb = distill_playbooks(str(t.ledger))
                    return rep + f"\nPlaybooks >=90%: {len(pb)}"
                reply = await asyncio.to_thread(_run_gym)
            except Exception as e:
                reply = f"Gym indisponivel: {e}. Use: AURA_GYM_TREINAR.bat"
            return ChatResponse(
                reply=reply, model="aura:gym",
                latency_ms=int((time.time() - t0) * 1000),
                timestamp=_iso_utc(),
                session_id=session_id, memory_used=False,
                suggestions=["autonomia", "status", "gym 100"],
                alerts=await asyncio.to_thread(_read_recent_alerts, 5),
            )

        # frases de operador que nao passam no ACTION_RE (programador / agentes / fecha e abre)
        _op_extra = any(k in low for k in (
            "programador", "ativa agentes", "ativar agentes", "ative os agentes",
            "fecha e abre", "fechar e abrir", "reabre tudo",
        ))
        if _is_pure_command(msg) or _op_extra:
            route, model = "action", "aura-operator"
            ag = _load_agents()
            destructive = bool(re.match(
                r"^\s*(?:autori[sz][oa]\s+|pode\s+|podes\s+)?(corrige?|conserta?|arruma?|repara?|fix|reinicia?|restart|religa?)",
                low,
            )) or any(k in low for k in ("fecha e abre", "fechar e abrir", "reabre tudo"))
            if destructive and not _has_auth_token(msg):
                _PENDING_AUTH[session_id] = {"command": _strip_auth_token(msg) or "corrige", "ts": time.time()}
                reply = (
                    "Acao destrutiva pedida. Confirma com AUTORIZO (ou envia cancelar). "
                    f"Exemplo: AUTORIZO {_strip_auth_token(msg) or 'corrige'}"
                )
                model = "aura:gate"
            elif _op_extra or destructive:
                # Um unico caminho: gate do operador (handle_operator_intent)
                reply = await asyncio.to_thread(ag.handle_operator_intent, msg)
                if not reply:
                    if "programador" in low:
                        try:
                            import aura_programmer_agent as _prog
                            reply = await asyncio.to_thread(_prog.run_operator, msg)
                            model = "aura:programmer"
                        except Exception as exc:
                            reply = f"Programador indisponivel: {exc}"
                    elif any(k in low for k in ("agente",)):
                        reply = await asyncio.to_thread(ag.handle_operator_intent, "ativa agentes") or "Agentes: comando nao reconhecido."
                    else:
                        reply = await asyncio.to_thread(ag.status_text)
                else:
                    model = "aura:operator"
            elif re.match(r"^\s*(?:autori[sz][oa]\s+|pode\s+|podes\s+)?(abre?|abra?)", low):
                reply = await asyncio.to_thread(ag.open_desktop)
                model = "aura:desktop"
            elif low.startswith(("gpu", "placa")) or low.lstrip().startswith("autorizo gpu") or low.lstrip().startswith("autoriso gpu"):
                m = re.search(r"(\d{2,3})", low)
                pct = min(int(m.group(1)), 100) if m else 0
                if 20 <= pct <= 100:
                    reply = await asyncio.to_thread(ag.set_gpu_cap, pct)
                else:
                    reply = await asyncio.to_thread(ag.gpu_status)
                model = "aura:gpu"
            elif re.match(r"^\s*(?:autori[sz][oa]\s+|pode\s+|podes\s+)?(diagn[oÃ³]stic|diag|an[aÃ¡]lise)", low):
                reply = await asyncio.to_thread(ag.deep_diagnose)
                model = "aura:diagnose"
            else:
                reply = await asyncio.to_thread(ag.status_text)
                model = "aura:status"

        # CAMADA 2 â€” RELATO DE PROBLEMA
        elif PROBLEM_RE.search(msg):
            route, model = "diagnose+explain", "hermes+diag"
            try:
                ag = _load_agents()
                facts = await asyncio.to_thread(ag.deep_diagnose)
                facts = str(facts) + "\n" + str(await asyncio.to_thread(_live_context_block))
            except Exception as e:
                facts = f"(diagnostico automatico falhou: {e})\n{await asyncio.to_thread(_live_context_block)}"
            if engine:
                rb = await asyncio.to_thread(_load_runbook)
                system = (
                    "Voce e o Hermes, copiloto LOCAL do AURA QUANT-X (paper-trade).\n"
                    "AURA nao e LLM da Microsoft. Voce nao e ChatGPT/Copilot.\n"
                    "Recebe FATOS do diagnostico automatico. Sua funcao:\n"
                    "1) explicar em portugues claro o que esta errado;\n"
                    "2) dizer o comando exato para corrigir (ex: 'corrige' ou 'reinicia engine').\n"
                    "NAO invente fatos fora do relatorio. Se o relatorio nao explica, diga isso.\n"
                    f"\n=== RELATORIO DE DIAGNOSTICO (fatos) ===\n{str(facts)[:6000]}\n=== FIM ===\n\n=== RUNBOOK ===\n{rb[:4000]}"
                )
                try:
                    safe_system = build_safe_prompt(system, msg)
                    resp = await asyncio.wait_for(engine.chat(
                        [{"role": "system", "content": safe_system}, {"role": "user", "content": msg}],
                        use_tools=False,
                    ), timeout=90)
                    reply = str(getattr(resp, "content", "") or "").strip()[:4000]
                    model = getattr(resp, "model", None) or "hermes+diag"
                except Exception as e:
                    reply = str(facts)[:4000] + f"\n\n(LLM indisponivel: {e})"
                    model = "aura:diagnose"
            else:
                reply = str(facts)[:4000]
                model = "aura:diagnose"

        # CAMADA 3 â€” CONVERSA GERAL
        else:
            live = str(await asyncio.to_thread(_live_context_block))
            memory_ctx = ""
            if memory and getattr(req, "use_memory", True):
                try:
                    memory_ctx = await asyncio.to_thread(memory.get_context_for_prompt, msg, 800)
                except Exception:
                    memory_ctx = ""
            if memory_ctx:
                live = live + "\n\nMemoria recente:\n" + str(memory_ctx)[:800]
            if engine:
                rb = await asyncio.to_thread(_load_runbook)
                _mdl = (
                    __import__("os").getenv("AURA_JARVIS_MODEL")
                    or __import__("os").getenv("AURA_OLLAMA_MODEL")
                    or "qwen3:8b"
                )
                system = (
                    "Voce e o HERMES, copiloto tecnico LOCAL do AURA QUANT-X.\n"
                    "IDENTIDADE OBRIGATORIA (nao invente fora disto):\n"
                    "- AURA nao e um LLM da Microsoft nem de nenhuma empresa.\n"
                    "- AURA e o sistema local do usuario (paper-trade, bridge, engine, matriz).\n"
                    f"- O modelo de linguagem ATIVO neste chat e: {_mdl} (Ollama local).\n"
                    "- Secundario para contexto longo: llama3.2:3b. GLM nao roda no AURA.\n"
                    "- Voce NAO e ChatGPT, Copilot, Gemini nem produto Microsoft.\n"
                    "Estilo: portugues do Brasil, curto, direto, sem enrolacao.\n"
                    f"Estado factual agora:\n{live}\n"
                    "Comandos do usuario: status, corrige, diagnostico, reinicia engine, desktop, gpu.\n"
                    "Invariantes: paper_trade=true, execution_allowed=false. Nunca invente fixtures, odds ou servicos.\n"
                    "Se nao souber um dado, diga que nao esta disponivel.\n"
                    f"\n=== RUNBOOK ===\n{rb[:4000]}"
                )
                try:
                    safe_system = build_safe_prompt(system, msg)
                    resp = await asyncio.wait_for(engine.chat(
                        [{"role": "system", "content": safe_system}, {"role": "user", "content": msg}],
                        use_tools=False,
                    ), timeout=90)
                    reply = str(getattr(resp, "content", "") or "").strip()[:4000]
                    model = getattr(resp, "model", None) or "hermes"
                except Exception as e:
                    reply = live + f"\n\nLLM indisponivel ({e}). Comandos: status | corrige | diagnostico."
                    model = "aura-operator"
            else:
                reply = live + "\n\nEnvie: status | corrige | diagnostico."
                model = "aura-operator"

        if not reply:
            reply = str(await asyncio.to_thread(_live_context_block)) + "\n\nEnvie: status | corrige | diagnostico."
        if route in ("llm", "diagnose+explain"):
            reply = _sanitize_llm(str(reply), msg) or reply

        # Anti-alucinacao de identidade (Microsoft / ChatGPT / etc.)
        _mdl_now = (
            __import__("os").getenv("AURA_JARVIS_MODEL")
            or __import__("os").getenv("AURA_OLLAMA_MODEL")
            or "qwen3:8b"
        )
        if route in ("llm", "diagnose+explain") or (model and "hermes" in str(model)):
            reply = _sanitize_reply(str(reply), _mdl_now)
            if model in ("hermes", "hermes+diag", None, ""):
                model = _mdl_now

        memory_used = False
        try:
            if memory and getattr(req, "use_memory", True):
                memory_used = True
                await asyncio.to_thread(memory.store, MemoryEntry(
                    id=_mem_id(f"mem_{session_id}"),
                    ts=_iso_utc(),
                    role="user",
                    content=msg[:2000],
                    source="chat_api",
                    tags=["chat", session_id, route],
                ))
                await asyncio.to_thread(memory.store, MemoryEntry(
                    id=_mem_id(f"mem_{session_id}_r"),
                    ts=_iso_utc(),
                    role="assistant",
                    content=str(reply)[:2000],
                    source="chat_api",
                    tags=["chat", session_id, model],
                ))
                try:
                    MEMORY_OPS.labels(op="store").inc()
                except Exception:
                    pass
        except Exception:
            memory_used = False

        return ChatResponse(
            reply=str(reply),
            model=model,
            latency_ms=int((time.time() - t0) * 1000),
            timestamp=_iso_utc(),
            session_id=session_id,
            memory_used=memory_used,
            suggestions=_chat_suggestions(msg, str(reply)),
            alerts=await asyncio.to_thread(_read_recent_alerts, 5),
        )
    except Exception as fatal:
        return ChatResponse(
            reply=(
                f"ERRO REAL na rota '{route}': {fatal}\n"
                "Isto e um bug do Hermes, nao do AURA. "
                "Comandos diretos: status | corrige | diagnostico."
            ),
            model="error",
            latency_ms=int((time.time() - t0) * 1000),
            timestamp=_iso_utc(),
            session_id=session_id,
            memory_used=False,
            suggestions=["status", "diagnostico", "corrige"],
            alerts=await asyncio.to_thread(_read_recent_alerts, 5),
        )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatMessage):
    if not engine:
        raise HTTPException(status_code=503, detail="Engine nÃ£o inicializado")

    async def event_generator():
        live = ""
        try:
            live = str(await asyncio.to_thread(_live_context_block))
        except Exception:
            live = ""
        rb = ""
        try:
            rb = await asyncio.to_thread(_load_runbook)
        except Exception:
            rb = ""
        memory_ctx = ""
        if memory and getattr(req, "use_memory", True):
            try:
                memory_ctx = await asyncio.to_thread(memory.get_context_for_prompt, req.message, 800)
            except Exception:
                memory_ctx = ""
        system = (
            "Voce e o HERMES, copiloto tecnico LOCAL do AURA QUANT-X.\n"
            "AURA nao e um LLM da Microsoft. Voce NAO e ChatGPT/Copilot.\n"
            f"Estado factual agora:\n{live}\n"
            "Invariantes: paper_trade=true, execution_allowed=false. Nunca invente fixtures.\n"
            + (f"Memoria:\n{str(memory_ctx)[:800]}\n" if memory_ctx else "")
            + f"=== RUNBOOK ===\n{rb[:4000]}"
        )
        try:
            safe_system = build_safe_prompt(system, req.message)
        except Exception:
            safe_system = system
        messages = [
            {"role": "system", "content": safe_system},
            {"role": "user", "content": req.message},
        ]
        async for chunk in engine.stream_chat(messages):
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/correct")
async def correct(req: CorrectRequest, _auth: str = Depends(require_local_or_token)):
    aura_root = _aura_root()
    if req.code in ("full_stack", "status", "run_deep"):
        if req.simulate_first and digital_twin is None:
            return {
                "status": "blocked",
                "code": req.code,
                "error": "digital_twin_unavailable",
                "fix_not_applied": True,
            }
        if req.simulate_first and digital_twin is not None:
            try:
                sim_result = await _maybe_await(digital_twin.simulate(req.code, {"target": req.target}))
                if hasattr(sim_result, "success") and not sim_result.success:
                    if alerts:
                        await _maybe_await(alerts.send(
                            "warning", "correct_endpoint",
                            f"Simulacao falhou para {req.code}",
                            {"confidence": req.confidence},
                        ))
                    return {
                        "status": "simulation_failed",
                        "code": req.code,
                        "fix_not_applied": True,
                    }
            except Exception as exc:
                return {"status": "simulation_failed", "code": req.code, "error": str(exc), "fix_not_applied": True}
        try:
            import sys as _sys
            scripts = aura_root / "scripts"
            if str(scripts) not in _sys.path:
                _sys.path.insert(0, str(scripts))
            import aura_programmer_agent as _prog
            text = await asyncio.to_thread(
                _prog.run_operator,
                "corrige full_stack e abre o relatorio" if req.code != "status" else "abre o relatorio de erros",
            )
            if alerts:
                await _maybe_await(alerts.send("info", "correct_endpoint", f"Operator {req.code}", {"target": req.target}))
            return {"status": "applied", "code": req.code, "details": text, "report": str(getattr(_prog, "REPORT_TXT", ""))}
        except Exception as exc:
            return {"status": "failed", "code": req.code, "error": str(exc)}
    from agents.hermes_correction_agent_llm import CorrectionAgent
    agent = CorrectionAgent(root=str(ROOT))

    if req.simulate_first and digital_twin is None:
        return {
            "status": "blocked",
            "error": "digital_twin_unavailable",
            "fix_not_applied": True,
        }
    if req.simulate_first and digital_twin:
        sim_result = await _maybe_await(digital_twin.simulate(req.code, {"target": req.target}))
        if hasattr(sim_result, "success") and not sim_result.success:
            if alerts:
                await _maybe_await(alerts.send(
                    "warning", "correct_endpoint", f"SimulaÃ§Ã£o falhou para {req.code}",
                    {"confidence": req.confidence, "simulation": getattr(sim_result, "predicted_outcome", None)},
                ))
            return {
                "status": "simulation_failed",
                "simulation": {
                    "success": sim_result.success,
                    "confidence": sim_result.confidence,
                    "side_effects": sim_result.side_effects,
                },
                "fix_not_applied": True,
            }

    result = await _maybe_await(agent.apply_fix(req.code, req.target, req.confidence))
    if not isinstance(result, dict):
        result = {"status": "applied" if result else "failed", "details": str(result)}

    if alerts:
        if result.get("status") in ("applied", "success"):
            await _maybe_await(alerts.send("info", "correct_endpoint", f"Fix {req.code} aplicado", {"target": req.target}))
        elif result.get("status") == "failed":
            await _maybe_await(alerts.send("critical", "correct_endpoint", f"Fix {req.code} falhou", {"error": result.get("details", {})}))

    return result

@app.post("/api/simulate")
async def simulate(req: SimulateRequest, _auth: str = Depends(require_local_or_token)):
    if not digital_twin:
        raise HTTPException(status_code=503, detail="Digital Twin nÃ£o inicializado")
    result = await _maybe_await(digital_twin.simulate(req.action_type, req.params, depth=req.depth))
    return {
        "success": result.success,
        "confidence": result.confidence,
        "predicted_outcome": result.predicted_outcome,
        "side_effects": result.side_effects,
        "rollback_plan": result.rollback_plan,
        "execution_time_ms": result.execution_time_ms,
    }

@app.post("/api/fs/read")
async def fs_read(req: FSReadRequest, _auth: str = Depends(require_local_or_token)):
    from core.hermes_llm_engine import tool_read_file
    content = await asyncio.to_thread(lambda: tool_read_file(req.path, root=str(ROOT)))
    if content.startswith("[ERRO]"):
        raise HTTPException(status_code=400, detail=content)
    return {"path": req.path, "content": content}

@app.post("/api/fs/list")
async def fs_list(req: FSListRequest, _auth: str = Depends(require_local_or_token)):
    from core.hermes_llm_engine import tool_list_dir
    content = await asyncio.to_thread(lambda: tool_list_dir(req.path, root=str(ROOT)))
    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=content)
    return {"path": req.path, "items": items}

@app.get("/api/anomaly/recent")
async def anomaly_recent(hours: int = 24):
    if not anomaly_detector:
        raise HTTPException(status_code=503, detail="Detector nÃ£o inicializado")
    hours = max(1, min(int(hours or 24), 168))
    return {"anomalies": await asyncio.to_thread(anomaly_detector.get_recent, hours)}

@app.get("/api/healing/log")
async def healing_log(limit: int = 50):
    if not healing:
        raise HTTPException(status_code=503, detail="Healing nÃ£o inicializado")
    limit = max(1, min(int(limit or 50), 500))
    return {"log": await asyncio.to_thread(healing.get_log, limit)}

@app.get("/api/memory/search")
async def memory_search(q: str, top_k: int = 5):
    if not memory:
        raise HTTPException(status_code=503, detail="Memory nÃ£o inicializada")
    top_k = max(1, min(int(top_k or 5), 50))
    results = await asyncio.to_thread(memory.search, q, top_k)
    return {"query": q, "results": results}

@app.post("/api/memory/store")
async def memory_store(req: MemoryStoreRequest, _auth: str = Depends(require_local_or_token)):
    if not memory:
        raise HTTPException(status_code=503, detail="Memory nÃ£o inicializada")
    entry = MemoryEntry(
        id=_mem_id("mem"),
        ts=_iso_utc(),
        role=req.role,
        content=req.content,
        source=req.source,
        tags=req.tags,
    )
    ok = await asyncio.to_thread(memory.store, entry)
    return {"stored": ok, "id": entry.id}

@app.get("/api/alerts/unacknowledged")
async def alerts_unacknowledged(min_severity: str = "warning"):
    if not alerts:
        raise HTTPException(status_code=503, detail="Alert manager nÃ£o inicializado")
    return {"alerts": alerts.get_unacknowledged(min_severity=min_severity)}

@app.get("/metrics")
async def metrics():
    payload = generate_latest()
    if not isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload or b"")
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

# â”€â”€â”€ WebSocket â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    # Auth: loopback livre se AUTH_REQUIRED=0; senao token query ?token= ou header
    client_host = ""
    try:
        client_host = (websocket.client.host if websocket.client else "") or ""
    except Exception:
        client_host = ""
    is_loop = client_host in ("127.0.0.1", "::1", "localhost")
    token = None
    try:
        token = websocket.query_params.get("token") or websocket.headers.get("authorization") or websocket.headers.get("Authorization")
        if token and str(token).lower().startswith("bearer "):
            token = str(token)[7:].strip()
    except Exception:
        token = None
    if AUTH_REQUIRED or not is_loop:
        if not token:
            await websocket.close(code=1008, reason="Token required")
            return
        expected = hashlib.sha256(f"hermes:{JWT_SECRET}".encode()).hexdigest()[:32]
        if not secrets.compare_digest((token or "")[:32], expected):
            await websocket.close(code=1008, reason="Invalid token")
            return
    await websocket.accept()
    WS_CONNECTIONS.inc()
    try:
        WS_ACTIVE.inc()
    except Exception:
        pass
    session_id = _mem_id("ws")

    try:
        while True:
            data = await websocket.receive_text()
            WS_MESSAGES.inc()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                try:
                    await websocket.send_json({"error": "JSON invÃ¡lido"})
                except Exception:
                    break
                continue
            if not isinstance(payload, dict):
                try:
                    await websocket.send_json({"error": "JSON deve ser objeto"})
                except Exception:
                    break
                continue
            message = str(payload.get("message", "") or "")

            try:
                memory_ctx = ""
                if memory:
                    try:
                        memory_ctx = await asyncio.to_thread(memory.get_context_for_prompt, message, 800)
                    except Exception:
                        memory_ctx = ""
                live = ""
                try:
                    live = str(await asyncio.to_thread(_live_context_block))
                except Exception:
                    live = ""
                base_system = (
                    "Voce e o Hermes, copiloto LOCAL do AURA QUANT-X (WebSocket). "
                    "AURA nao e Microsoft. Nao invente.\n"
                    f"{live}\n{memory_ctx}"
                )
                try:
                    safe_system = build_safe_prompt(base_system, message)
                except Exception:
                    safe_system = base_system
                messages = [
                    {"role": "system", "content": safe_system},
                    {"role": "user", "content": message},
                ]

                if engine is None:
                    await websocket.send_json({"reply": "Ollama/LLM offline â€” use REST /api/chat.", "model": "fallback", "ok": False})
                    continue
                resp = await asyncio.wait_for(engine.chat(messages, use_tools=False), timeout=90)
                content = _sanitize_llm(str(getattr(resp, "content", "") or ""), message) or str(getattr(resp, "content", "") or "")
                mdl = getattr(resp, "model", None) or "hermes"

                if memory:
                    try:
                        await asyncio.to_thread(memory.store, MemoryEntry(
                            id=_mem_id(f"mem_ws_{session_id}"),
                            ts=_iso_utc(),
                            role="user", content=message[:2000], source="websocket", tags=["ws", session_id],
                        ))
                        await asyncio.to_thread(memory.store, MemoryEntry(
                            id=_mem_id(f"mem_ws_{session_id}_r"),
                            ts=_iso_utc(),
                            role="assistant", content=content[:1000], source="websocket", tags=["ws", session_id],
                        ))
                    except Exception:
                        pass

                await websocket.send_json({
                    "reply": content,
                    "model": mdl,
                    "session_id": session_id,
                    "ts": _iso_utc(),
                })
            except WebSocketDisconnect:
                raise
            except Exception as loop_exc:
                try:
                    await websocket.send_json({"error": str(loop_exc), "session_id": session_id})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            WS_ACTIVE.dec()
        except Exception:
            pass

# â”€â”€â”€ Dashboard HTML Embutido â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-store">
<meta name="theme-color" content="#07080c">
<title>AURA Hermes Â· Operator OS verde</title>
<style>
:root{--bg:#07080c;--panel:#10150e;--line:rgba(215,255,63,.22);--acid:#d7ff3f;--ink:#15200c;--txt:#e8f0d8;--dim:#8a9770;--bad:#ff5d6c}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--txt);font:15px/1.45 ui-sans-serif,Segoe UI,system-ui}
.wrap{max-width:980px;margin:0 auto;padding:18px;min-height:100%;display:flex;flex-direction:column;gap:12px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);background:var(--panel);padding:12px 14px}
.brand{font-weight:800;letter-spacing:.08em;color:var(--acid);text-transform:uppercase;font-size:13px}
.brand b{display:block;font-size:18px;letter-spacing:0;text-transform:none}
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{border:1px solid var(--line);color:var(--acid);padding:4px 8px;font-size:11px;font-weight:700}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.card{border:1px solid var(--line);background:var(--panel);padding:10px 12px}
.card h3{color:var(--acid);font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
.row{display:flex;justify-content:space-between;font-size:13px;padding:3px 0;color:var(--dim)}
.row b{color:var(--txt);font-family:ui-monospace,Consolas,monospace}
.chat{flex:1;display:flex;flex-direction:column;border:1px solid var(--line);background:var(--panel);min-height:420px}
.chat h3{color:var(--acid);font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:10px 12px;border-bottom:1px solid var(--line)}
#chatBox{flex:1;overflow:auto;padding:12px;min-height:280px}
.msg{max-width:86%;margin:8px 0;padding:10px 12px;border:1px solid var(--line);white-space:pre-wrap}
.user{margin-left:auto;background:rgba(215,255,63,.08);color:var(--acid)}
.bot{margin-right:auto;background:#0c120b}
.meta{display:block;margin-top:6px;color:var(--dim);font-size:11px}
.actions{display:flex;flex-wrap:wrap;gap:6px;padding:10px 12px;border-top:1px solid var(--line)}
.actions button,.send button{
  background:var(--acid);color:var(--ink);border:0;padding:8px 12px;font-weight:800;cursor:pointer;font-size:13px
}
.actions button.ghost{background:transparent;color:var(--acid);border:1px solid var(--acid)}
.send{display:flex;gap:8px;padding:0 12px 12px}
.send input{flex:1;background:#07080c;border:1px solid var(--line);color:var(--txt);padding:10px 12px;outline:none}
.send input:focus{border-color:var(--acid)}
.foot{color:var(--dim);font-size:11px}
@media (max-width:800px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">AURA QUANT-X<b>Hermes Operator Â· verde</b></div>
    <div class="pills">
      <span class="pill" id="badgePaper">PAPER</span>
      <span class="pill" id="badgeExec">EXEC OFF</span>
      <span class="pill" id="healthStatus">HEALTH</span>
    </div>
  </div>
  <div class="grid">
    <div class="card"><h3>Sistema</h3>
      <div class="row">Anomalia <b id="anomalyScore">--</b></div>
      <div class="row">Env <b id="envSafe">--</b></div>
    </div>
    <div class="card"><h3>Recursos</h3>
      <div class="row">CPU <b id="cpuVal">--</b></div>
      <div class="row">RAM <b id="memVal">--</b></div>
      <div class="row">Disco <b id="diskVal">--</b></div>
    </div>
    <div class="card"><h3>Modelo</h3>
      <div class="row">Fonte <b id="modelProvider">operador</b></div>
      <div class="row">Latencia <b id="modelLatency">--</b></div>
      <div class="row">Ultimo <b id="lastResp">--</b></div>
    </div>
  </div>
  <div class="chat">
    <h3>Chat operador</h3>
    <div id="chatBox"></div>
    <div class="actions" id="suggestBox">
      <button type="button" data-msg="status">Status</button>
      <button type="button" data-msg="corrige">Corrigir</button>
      <button type="button" class="ghost" data-msg="diagnostico">Relatorio</button>
      <button type="button" class="ghost" data-msg="programador">Programador</button>
      <button type="button" class="ghost" data-msg="reinicia engine">Engine</button>
      <button type="button" class="ghost" data-msg="abra desktop">Desktop</button>
    </div>
    <div class="send">
      <input id="msgInput" placeholder="fala normal: arruma o engine, abre o relatorio, status..." onkeydown="if(event.key==='Enter')sendMsg()">
      <button type="button" onclick="sendMsg()">Enviar</button>
    </div>
  </div>
  <div class="foot">paper_trade=true Â· execution_allowed=false Â· Ollama :11434 nunca e morto Â· v37.3.47-AUDIT</div>
</div>
<script>
const API = (function(){const o=location.origin; if(/:(8778|8766|8099)$/.test(o)) return o.replace(/:(8778|8766|8099)$/, ':8777'); return o;}());
let lastModel='';
function esc(t){return String(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function pct(v){return (v===null||v===undefined||v==='')?'--':(Number(v).toFixed(0)+'%')}
async function loadHealth(){
  try{
    const r=await fetch(API+'/api/system',{cache:'no-store'});
    const d=await r.json();
    document.getElementById('healthStatus').textContent = d.ok===false?'OFF':'LIVE';
    document.getElementById('anomalyScore').textContent = (Number(d.anomaly_score)||0).toFixed(3);
    document.getElementById('envSafe').textContent = d.env_safe?'YES':'NO';
    document.getElementById('cpuVal').textContent = pct(d.cpu);
    document.getElementById('memVal').textContent = pct(d.memory);
    document.getElementById('diskVal').textContent = pct(d.disk);
    document.getElementById('modelProvider').textContent = (d.ollama_ok?'Ollama':'operador')+' Â· '+(d.model||'local');
    document.getElementById('modelLatency').textContent = (d.ollama_ms!=null?d.ollama_ms:'--')+'ms';
  }catch(e){document.getElementById('healthStatus').textContent='OFF';}
}
document.addEventListener('click',ev=>{
  const b=ev.target.closest('[data-msg]');
  if(!b) return;
  const inp=document.getElementById('msgInput');
  inp.value=b.getAttribute('data-msg');
  sendMsg();
});
async function sendMsg(){
  const inp=document.getElementById('msgInput');
  const box=document.getElementById('chatBox');
  const msg=(inp.value||'').trim(); if(!msg) return;
  box.innerHTML += '<div class="msg user">'+esc(msg)+'</div>';
  inp.value=''; box.scrollTop=box.scrollHeight;
  const t0=Date.now();
  try{
    const ac=new AbortController();
    const to=setTimeout(()=>ac.abort(),90000);
    const r=await fetch(API+'/api/chat',{method:'POST',cache:'no-store',signal:ac.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,use_memory:true})});
    clearTimeout(to);
    const d=await r.json();
    document.getElementById('modelProvider').textContent=d.model||'operador';
    document.getElementById('modelLatency').textContent=Math.round(d.latency_ms||(Date.now()-t0))+'ms';
    document.getElementById('lastResp').textContent=new Date().toLocaleTimeString();
    box.innerHTML += '<div class="msg bot">'+esc(d.reply)+'<span class="meta">'+(d.model||'')+' Â· '+Math.round(d.latency_ms||0)+'ms</span></div>';
  }catch(e){
    box.innerHTML += '<div class="msg bot">Falha HTTP: '+esc(e.message)+'. O chat em si continua. Tenta status.</div>';
  }
  box.scrollTop=box.scrollHeight;
}
loadHealth();
setInterval(loadHealth,15000);
</script>
</body></html>

"""

@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return HTMLResponse(
        content=DASHBOARD_HTML,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )

@app.get("/")
async def root():
    return {
        "name": "Hermes V10 Ultra API",
        "version": "10.1.1-ULTRA-AUDIT47",
        "paper_trade": PAPER_TRADE,
        "features": ["chat", "memory", "digital_twin", "anomaly_detection", "self_healing", "alerts", "mcp"],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=API_PORT)

