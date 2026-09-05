from __future__ import annotations


# AURA_PATH_BOOTSTRAP
import sys as _aura_sys
from pathlib import Path as _AuraPath
_AURA_ENGINE_DIR = _AuraPath(__file__).resolve().parent
_AURA_ROOT = _AURA_ENGINE_DIR.parent
for _p in (str(_AURA_ENGINE_DIR), str(_AURA_ROOT)):
    if _p not in _aura_sys.path:
        _aura_sys.path.insert(0, _p)

# V25T14: silencia avisos conhecidos (FastAPI on_event, pynvml) sem esconder erros reais
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*pynvml.*")
warnings.filterwarnings("ignore", message=".*on_event is deprecated.*")

import os as _aura_os_safety

def _validate_safety_invariants() -> None:
    """Hard-block: never start Engine with real execution enabled by accident."""
    def _flag(*names: str, default: str) -> str:
        for name in names:
            raw = _aura_os_safety.getenv(name)
            if raw is not None and str(raw).strip() != "":
                return str(raw).strip().lower()
        return default

    paper = _flag("AURA_PAPER_TRADE", "PAPER_TRADE", default="true")
    exec_allowed = _flag("AURA_EXECUTION_ALLOWED", "EXECUTION_ALLOWED", default="false")
    unlock = _flag("AURA_UNLOCK_LIVE", default="0")
    if paper not in ("1", "true", "yes", "on"):
        print("[FATAL] PAPER_TRADE must be true. Aborting Engine start.")
        raise SystemExit(91)
    if exec_allowed in ("1", "true", "yes", "on"):
        print("[FATAL] EXECUTION_ALLOWED is true. Aborting Engine start for safety.")
        raise SystemExit(92)
    if unlock in ("1", "true", "yes", "on"):
        print("[FATAL] AURA_UNLOCK_LIVE is set. Aborting Engine start for safety.")
        raise SystemExit(93)

_validate_safety_invariants()

import threading
# engine/server.py
# AURA QUANT-X v12.7.0-RECONSOLIDADO — Orchestrator + Telemetry + DeltaStateCompressor

from concurrent.futures import ThreadPoolExecutor
_ANALYSIS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aura_analysis")

# V24 audit: WAL-aligned thread-local DB for server hot path
_SERVER_DB_LOCAL = threading.local()

def _get_server_db_conn():
    conn = getattr(_SERVER_DB_LOCAL, "conn", None)
    if conn is not None:
        return conn
    import sqlite3 as _sqlite3
    _db = globals().get("DB_NAME") or globals().get("DB_PATH") or "aura_engine.db"
    conn = _sqlite3.connect(_db, check_same_thread=False, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-10000")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = _sqlite3.Row
    except Exception:
        pass
    _SERVER_DB_LOCAL.conn = conn
    return conn


# V23: sobe monitor do HardwareGovernor quando o event loop estiver disponivel
def _start_hardware_governor_monitor():
    """V26.3-FIX: importa GOVERNOR (singleton real), nao o nome inexistente hardware_governor."""
    try:
        import asyncio
        try:
            from core.hardware_governor import GOVERNOR as _gov
        except Exception:
            from engine.core.hardware_governor import GOVERNOR as _gov
    except Exception:
        return
    try:
        # Garante start idempotente do singleton
        if hasattr(_gov, "start"):
            _gov.start()
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_gov.monitor_loop(interval_seconds=4.0))
    except Exception:
        pass



# V23: Supervisor Jarvis (autonomia contínua)
try:
    from supervisor_jarvis import jarvis_supervisor
except Exception:
    try:
        from agents.supervisor_jarvis import jarvis_supervisor
    except Exception:
        jarvis_supervisor = None  # type: ignore

# V25 Conformal + MC Grid + Experience (preenchidos no startup)
CONFORMAL = None  # type: ignore
RISK = None  # type: ignore
decision_bus = None  # type: ignore
MC = None  # type: ignore
EXP_RETRIEVER = None  # type: ignore


import asyncio
import hmac
import json
import logging
import math
import os
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import AliasChoices, BaseModel, Field

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception as exc:
    logging.getLogger("aura.engine_server").debug("Console UTF-8 não pôde ser reconfigurado: %s", exc)
from engine_core import (
    get_local_ai_engine,
    init_db_wal,
    LocalAIEngine,
    DB_NAME,
    ENGINE,
)
from agent_registry import catalog as agent_catalog, status as agent_status, action as run_agent_action
try:
    from agent_glm_runtime import AgentGLMRuntime
except ImportError:
    from engine.agent_glm_runtime import AgentGLMRuntime
try:
    from risk_gates import RISK_GATES
except Exception:
    RISK_GATES = None
from pillar_runtime import get_pillar_runtime
try:
    from deep_diagnostic import collect_diagnostic
except ImportError:
    from engine.deep_diagnostic import collect_diagnostic
try:
    from matrix_full_diagnostic import run_full as matrix_run_full
except Exception:
    try:
        from engine.matrix_full_diagnostic import run_full as matrix_run_full
    except Exception:
        matrix_run_full = None
try:
    from telegram_central import AuraTelegramCentral
except ImportError:
    from engine.telegram_central import AuraTelegramCentral
try:
    from working_memory import MEMORY
except ImportError:
    try:
        from engine.working_memory import MEMORY
    except ImportError:
        import importlib.util as _ilu
        _wm_path = _AURA_ENGINE_DIR / "working_memory.py"
        if not _wm_path.is_file():
            raise ModuleNotFoundError(
                f"working_memory.py ausente em {_wm_path}. Reextraia o ZIP CORRIGIDO."
            )
        _spec = _ilu.spec_from_file_location("working_memory", _wm_path)
        _mod = _ilu.module_from_spec(_spec)
        assert _spec.loader is not None
        _spec.loader.exec_module(_mod)
        MEMORY = _mod.MEMORY
try:
    from quant_intelligence_layer import QuantIntelligenceLayer
except ImportError:
    from engine.quant_intelligence_layer import QuantIntelligenceLayer
try:
    from hardware_tweaks import HardwareTweaks
except ImportError:
    from engine.hardware_tweaks import HardwareTweaks
QUANT_INTELLIGENCE = QuantIntelligenceLayer()
HARDWARE_TWEAKS = HardwareTweaks.from_env()
HARDWARE_TWEAKS.apply_all()
try:
    from scripts.aura_performance_benchmark import collect_snapshot as collect_performance_snapshot
except ImportError:
    try:
        from aura_performance_benchmark import collect_snapshot as collect_performance_snapshot
    except ImportError:
        from importlib.util import module_from_spec, spec_from_file_location
        _benchmark_path = Path(__file__).resolve().parent.parent / "scripts" / "aura_performance_benchmark.py"
        _benchmark_spec = spec_from_file_location("aura_performance_benchmark", _benchmark_path)
        if _benchmark_spec is None or _benchmark_spec.loader is None:
            raise ImportError("aura_performance_benchmark_unavailable")
        _benchmark_module = module_from_spec(_benchmark_spec)
        _benchmark_spec.loader.exec_module(_benchmark_module)
        collect_performance_snapshot = _benchmark_module.collect_snapshot
try:
    from orchestrator import classify_intent, orchestrate_chat
except Exception:
    from engine.orchestrator import classify_intent, orchestrate_chat

try:
    from engine.infra.dynamic_yield import YIELD
    from engine.infra.priority_event_bus import BUS, PRIORITY_CRITICAL
except Exception:
    try:
        from infra.dynamic_yield import YIELD
        from infra.priority_event_bus import BUS, PRIORITY_CRITICAL
    except Exception:
        YIELD = None
        BUS = None
        PRIORITY_CRITICAL = 0

logger = logging.getLogger("aura.engine_server")
DB_THREAD_POOL = ThreadPoolExecutor(max_workers=4)
ENGINE_PORT = int(os.environ.get("AURA_ENGINE_PORT", "8765"))
ACTION_ALIASES = {"ANALISAR": "ANALYZE", "ANALYZE": "ANALYZE", "REFRESH_GAME": "ANALYZE", "SHOW_MARKET": "ANALYZE", "MARKET": "ANALYZE"}


# V24: single source of truth for compact keys (core.context_compactor) + server extras
try:
    from core.context_compactor import KEEP_KEYS as _COMPACTOR_KEEP_KEYS
except Exception:
    try:
        from engine.core.context_compactor import KEEP_KEYS as _COMPACTOR_KEEP_KEYS
    except Exception:
        _COMPACTOR_KEEP_KEYS = (
            "match_id", "fixture_id", "fixtureId", "minute", "score", "pressure",
            "xG", "xg", "dangerous_attacks", "dangerous", "corners", "corner_events",
            "decision", "asian_corner_line", "asian_corner_odds", "odds_velocity",
            "smart_money_divergence", "home", "away", "imc", "action",
        )

class DeltaStateCompressor:
    KEEP_KEYS = set(_COMPACTOR_KEEP_KEYS) | {
        "match_id", "decision", "edge", "odds_velocity",
        "asian_corner_odds", "asian_corner_line", "wom_text",
        "poisson_text", "ts", "win_probability", "calculated_edge",
        "stake_amount", "signal_state",
    }
    DROP_PREFIXES = ("system_snapshot", "raw_", "debug_", "internal_")

    @classmethod
    def compress(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in payload.items():
            if any(k.startswith(p) for p in cls.DROP_PREFIXES):
                continue
            if k in cls.KEEP_KEYS or k.startswith("alpha_") or k in ("equipe", "resultado"):
                if isinstance(v, float):
                    out[k] = round(v, 6)
                elif isinstance(v, (str, int, bool)) or v is None:
                    out[k] = v
                elif isinstance(v, dict):
                    out[k] = cls.compress(v)
                elif isinstance(v, list) and len(v) <= 16:
                    out[k] = v
        return out

    @classmethod
    def compress_for_llm(cls, payload: Dict[str, Any], max_chars: int = 512) -> str:
        compact = cls.compress(payload)
        s = json.dumps(compact, separators=(",", ":"), default=str)
        if len(s) > max_chars:
            s = s[: max_chars - 3] + "..."
        return s


def db_exec_sync(query: str, params: tuple = (), fetch: bool = False) -> Any:
    conn = _get_server_db_conn()
    cur = conn.cursor()
    if params:
        cur.execute(query, params)
        result = cur.fetchall() if fetch else None
    else:
        cur.executescript(query)
        result = None
    conn.commit()
    return result


async def db_exec(query: str, params: tuple = (), fetch: bool = False) -> Any:
    return await asyncio.to_thread(db_exec_sync, query, params, fetch)




# ---- P1 Ultra: batch writer for telemetry persistence (non-blocking hot path) ----
import queue as _queue_mod

class TelemetryBatchWriter:
    """Acumula eventos e grava em lote (executemany). Fail-closed se fila cheia."""
    def __init__(self, batch_size: int = 32, flush_ms: float = 250.0):
        self._q: "_queue_mod.Queue[tuple]" = _queue_mod.Queue(maxsize=4096)
        self._batch_size = batch_size
        self._flush_ms = flush_ms
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="aura-telemetry-writer", daemon=True)
        self._thread.start()

    def submit(self, match_id: str, payload: dict) -> bool:
        try:
            self._q.put_nowait((match_id, time.time(), payload))
            return True
        except _queue_mod.Full:
            try:
                logging.getLogger("aura.engine_server").warning("telemetry queue full — evento descartado")
            except Exception:
                pass
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            rows = []
            try:
                rows.append(self._q.get(timeout=self._flush_ms / 1000.0))
                deadline = time.monotonic() + self._flush_ms / 1000.0
                while len(rows) < self._batch_size:
                    try:
                        rows.append(self._q.get_nowait())
                        if time.monotonic() >= deadline:
                            break
                    except _queue_mod.Empty:
                        break
            except _queue_mod.Empty:
                continue
            if rows:
                self._flush(rows)

    def _flush(self, rows) -> None:
        try:
            conn = _get_server_db_conn()
            conn.executemany(
                "INSERT INTO logs_telemetria (match_id, timestamp_unix, system_snapshot, "
                "extension_corner_count, live_feed_corner_count, win_probability, calculated_edge, "
                "stake_amount, market_stats) VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r[0],
                        r[1],
                        __import__("json").dumps(r[2], ensure_ascii=False, default=str),
                        0, 0, 0.0, 0.0, 0.0, "{}",
                    )
                    for r in rows
                ],
            )
            conn.commit()
        except Exception as exc:
            try:
                logging.getLogger("aura.engine_server").error("telemetry flush failed: %s", exc)
            except Exception:
                pass

_TELEMETRY_WRITER = TelemetryBatchWriter()


def ensure_server_schema() -> None:
    """Migra o schema P0 para colunas legadas ainda usadas pelo servidor HTTP."""
    init_db_wal()
    db_exec_sync("CREATE TABLE IF NOT EXISTS kb_team_alphas (equipe TEXT PRIMARY KEY, alpha_atual REAL NOT NULL DEFAULT 1.0, total_operacoes INTEGER NOT NULL DEFAULT 0)")
    for ddl in (
        "ALTER TABLE logs_telemetria ADD COLUMN timestamp_unix REAL",
        "ALTER TABLE logs_telemetria ADD COLUMN status_sistema TEXT",
        "ALTER TABLE risk_calibration ADD COLUMN match_id TEXT",
        "ALTER TABLE risk_calibration ADD COLUMN validation_time REAL",
        "ALTER TABLE risk_calibration ADD COLUMN approval_state TEXT",
        "ALTER TABLE risk_calibration ADD COLUMN error_code TEXT",
        "ALTER TABLE risk_calibration ADD COLUMN asian_corner_line REAL DEFAULT 0.0",
        "ALTER TABLE risk_calibration ADD COLUMN asian_corner_odds REAL DEFAULT 0.0",
        "ALTER TABLE risk_calibration ADD COLUMN odds_velocity REAL DEFAULT 0.0",
        "ALTER TABLE risk_calibration ADD COLUMN data_integrity_hash TEXT",
    ):
        try:
            db_exec_sync(ddl)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                logger.warning("Falha inesperada na migração de schema (%s): %s", ddl, exc)


class MarketStats(BaseModel):
    window_start: int = 0
    window_end: int = 0
    asian_corner_line: float
    asian_corner_odds: float
    odds_velocity: float = 0.0
    smart_money_volume: float = 0.0
    smart_money_divergence: bool = False


class TelemetryPayload(BaseModel):
    match_id: str = Field(validation_alias=AliasChoices("match_id", "fixtureId", "fixture_id"))
    timestamp_unix: int = Field(default_factory=lambda: int(time.time()))
    system_snapshot: Optional[Dict[str, Any]] = None
    extension_corner_count: int = 0
    live_feed_corner_count: int = 0
    win_probability: float = 0.0
    calculated_edge: float = 0.0
    stake_amount: float = 0.0
    # A extensão pode enviar Wom cru, null ou MarketStats completo.
    market_stats: Any = Field(default_factory=dict)


class FeedPayload(BaseModel):
    match_id: str
    equipe: str
    resultado: str


class OrchestratorPayload(BaseModel):
    match_id: str
    intent: str = "trading"
    raw_context: Dict[str, Any] = Field(default_factory=dict)
    ask_llm: bool = False


class AgentActionPayload(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class AgentGLMReviewPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=1_000)
    context: Dict[str, Any] = Field(default_factory=dict)


class IMCPostMatchPayload(BaseModel):
    fixture_id: str = Field(min_length=1, max_length=160)
    predicted_imc: float = Field(ge=0.0, le=1_000_000.0)
    actual_corners: float = Field(ge=0.0, le=1_000_000.0)
    finalized: bool = False


class RiskManager:
    COOLDOWN_SECONDS = 60
    STALE_THRESHOLD_SECONDS = 45.0
    _cooldown_cache: Dict[str, float] = {}

    @classmethod
    def check_cooldown(cls, match_id: str) -> bool:
        agora = time.time()
        if match_id in cls._cooldown_cache:
            if (agora - cls._cooldown_cache[match_id]) < cls.COOLDOWN_SECONDS:
                return True
            del cls._cooldown_cache[match_id]
        return False

    @classmethod
    def approve(cls, payload: TelemetryPayload) -> Tuple[bool, str, str]:
        if (time.time() - payload.timestamp_unix) > cls.STALE_THRESHOLD_SECONDS:
            return False, "data_integrity_fail", "STALE"
        if payload.extension_corner_count != payload.live_feed_corner_count:
            return False, "data_integrity_fail", "LOGICAL_CONFLICT"
        market = payload.market_stats
        divergence = market.smart_money_divergence if isinstance(market, MarketStats) else bool((market or {}).get("smart_money_divergence")) if isinstance(market, dict) else False
        if divergence:
            return False, "smart_money_divergence", "BLOCKED_BY_MARKET"
        if payload.win_probability < 0.0:
            return False, "prob_below_threshold", "HOLD"
        if cls.check_cooldown(payload.match_id):
            return False, "cooldown", "HOLD"
        if payload.calculated_edge <= 0.0 or payload.stake_amount <= 0.0:
            return False, "no_edge_or_stake", "HOLD"
        return True, "approved", "PROCESSED"


app = FastAPI(title="AURA Engine Server", version="12.7.0-RECONSOLIDADO")

# --- V23: JSON structured logging + Correlation ID middleware ---
class _JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "module": getattr(record, "module", ""),
            "msg": record.getMessage(),
        }
        if hasattr(record, "error_trace"):
            log_obj["trace"] = record.error_trace
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        return json.dumps(log_obj, ensure_ascii=False)

try:
    _root = logging.getLogger()
    if not any(isinstance(h.formatter, _JsonFormatter) for h in _root.handlers if getattr(h, "formatter", None)):
        _h = logging.StreamHandler()
        _h.setFormatter(_JsonFormatter())
        logging.basicConfig(level=logging.INFO, handlers=[_h], force=True)
except Exception:
    pass

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    import uuid as _uuid

    class CorrelationIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            correlation_id = request.headers.get("X-Correlation-ID") or str(_uuid.uuid4())[:8]
            request.state.correlation_id = correlation_id
            logging.getLogger("aura.request").info(
                "Incoming: %s", request.url.path,
                extra={"correlation_id": correlation_id},
            )
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response

    app.add_middleware(CorrelationIdMiddleware)
except Exception as _mw_exc:
    logging.getLogger("aura.engine_server").warning("Correlation middleware nao registrado: %s", _mw_exc)

try:
    from admin.aura_admin_api import router as admin_router
except ImportError:
    from engine.admin.aura_admin_api import router as admin_router
app.include_router(admin_router)
try:
    from knowledge_review_gate import router as knowledge_router
except ImportError:
    try:
        from engine.knowledge_review_gate import router as knowledge_router
    except ImportError:
        knowledge_router = None
if knowledge_router is not None:
    app.include_router(knowledge_router)
try:
    from war_council_api import router as council_router
except ImportError:
    try:
        from engine.war_council_api import router as council_router
    except ImportError:
        council_router = None
if council_router is not None:
    app.include_router(council_router)

# V23 BLOCO 8: Prometheus metrics
try:
    from routes.metrics import router as metrics_router
except Exception:
    try:
        from engine.routes.metrics import router as metrics_router
    except Exception:
        metrics_router = None
if metrics_router is not None:
    app.include_router(metrics_router, tags=["Metrics"])

# Telegram HQ permanece dormente por padrão. A integração só pode ser carregada
# por uma ação opt-in explícita e autenticada; nunca durante o import/lifespan.
_start_tg_hq = None


# V23 BLOCO 4: CORS restrito (sem liberar qualquer extensao)
_ALLOWED_EXTENSION_IDS = [
    # IDs conhecidas da extensao AURA legada (ajuste se necessario)
    "abcdefghijklmnopqrstuvwxyz123456",
]
_MUTATION_TOKEN = os.getenv("AURA_MUTATION_TOKEN", "").strip()


def _mutation_auth_error(request: Request) -> Optional[Dict[str, str]]:
    """Credencial separada para mutações persistentes iniciadas pela UI/admin.

    A ausência da credencial desabilita a mutação (503), em vez de transformar
    qualquer chamada local em uma autorização implícita. O token nunca é
    embutido no frontend; o canal administrativo deve fornecê-lo explicitamente.
    """
    if not _MUTATION_TOKEN:
        return {"status": "503", "error": "mutation_token_not_configured"}
    supplied = request.headers.get("X-AURA-Mutation-Token", "").strip()
    if not supplied:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, _MUTATION_TOKEN):
        return {"status": "401", "error": "mutation_auth_required"}
    return None


_ALLOWED_ORIGINS = [
    "https://aura.local",
    "http://aura.local",
    "http://127.0.0.1:8765",
    "http://127.0.0.1:8080",
    "http://localhost:8765",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://sokkerpro.com",
    "https://www.sokkerpro.com",
    "https://m2.sokkerpro.com",
    "https://m4.sokkerpro.com",
    "null",  # Desktop WebView file:// / host nativo
]
# Desktop WebView, file://, localhost e aura.local
_ENGINE_ORIGIN_REGEX = os.getenv(
    "AURA_ENGINE_ORIGIN_REGEX",
    r"^https?://(127\.0\.0\.1|localhost|aura\.local)(:\d+)?$|^https://([a-z0-9-]+\.)?sokkerpro\.com$",
).strip() or r"^https?://(127\.0\.0\.1|localhost|aura\.local)(:\d+)?$"
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ENGINE_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-AURA-Approver-Token", "X-CornerAI", "X-CornerAI-Schema", "X-CornerAI-Version", "X-CornerAI-Token", "X-Requested-With", "X-Correlation-ID"],
    expose_headers=["X-AURA-Engine", "X-Correlation-ID"],
)
_engine: Optional[LocalAIEngine] = None
from collections import OrderedDict  # V23 LRU
try:
    from core.ttl_cache import TTLCache
except Exception:
    try:
        from engine.core.ttl_cache import TTLCache
    except Exception:
        TTLCache = dict  # type: ignore

_ANALYSIS_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_SNAPSHOT_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_CACHE_LIMIT = 128
_AGENT_GLM_RUNTIME = AgentGLMRuntime(Path(__file__).resolve().parent.parent)
_TELEGRAM_CENTRAL = AuraTelegramCentral(Path(__file__).resolve().parent.parent)


def _first(*values: Any) -> Any:
    for value in values:
        if value is None or value == "":
            continue
        if isinstance(value, str) and value.strip().lower() in {"null", "none", "n/d", "undefined"}:
            continue
        return value
    return None


def _apply_risk_contract(analysis: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Aplica os hard gates oficiais ao resultado sem liberar stake real."""
    out = dict(analysis or {})
    if RISK_GATES is None:
        out.update({"risk_gates": {"policy": "unavailable_fail_closed", "failed_gates": ["risk_engine_unavailable"]}, "kelly": 0.0, "stake_pct": 0.0, "exposure": 0.0, "approved": False})
        return out
    verdict = RISK_GATES.evaluate(out, payload or {})
    out["risk_gates"] = verdict
    out["gates"] = verdict.get("gates", [])
    out["failed_gates"] = verdict.get("failed_gates", [])
    out["signal"] = verdict.get("signal", out.get("signal"))
    out["decision"] = verdict.get("decision", out.get("decision"))
    out["approved"] = False
    out["kelly"] = 0.0
    out["stake_pct"] = 0.0
    out["exposure"] = 0.0
    failed = list(verdict.get("failed_gates") or [])
    trade_signal = str(out.get("signal") or "")
    gate_reason = "no_trade_signal" if not trade_signal.startswith("BUY") else (failed[0] if failed else "paper_trade_only")
    out["risk_gate"] = {"approved": False, "reason": gate_reason, "failed_gates": failed, "policy": "p1_hard_gates_v1"}
    risk = dict(out.get("risk") or {})
    risk.update({"state": "BLOCK", "approved": False, "reason": "Sem entrada: modo paper trade e gates fail-closed ativos.", "exposure": 0.0, "kelly": 0.0})
    out["risk"] = risk
    out["paper_trade"] = True
    return out


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _pair(value: Any) -> Tuple[Any, Any]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[0], value[1]
    if isinstance(value, dict):
        return _first(value.get("home"), value.get("h")), _first(value.get("away"), value.get("a"))
    return None, None


def _snapshot_for_engine(raw: Dict[str, Any], fixture_id: Optional[str] = None) -> Dict[str, Any]:
    """Converte contexto da extensão/Bridge para o contrato do LocalAIEngine."""
    src = raw if isinstance(raw, dict) else {}
    view = src.get("view") if isinstance(src.get("view"), dict) else {}
    payload = src.get("payload") if isinstance(src.get("payload"), dict) else {}
    match = src.get("match") if isinstance(src.get("match"), dict) else {}
    fixture = src.get("fixture") if isinstance(src.get("fixture"), dict) else {}
    if not fixture and isinstance(payload.get("fixture"), dict):
        fixture = payload.get("fixture") or {}
    client = src.get("client") if isinstance(src.get("client"), dict) else {}
    stats = src.get("stats") if isinstance(src.get("stats"), dict) else {}
    odds = src.get("odds") if isinstance(src.get("odds"), dict) else {}
    if not stats and isinstance(src.get("statistics"), dict):
        stats = dict(src["statistics"])
    else:
        stats = dict(stats)
    for metric_key in ("attacks", "dangerous", "shots", "shotsOn", "shotsOff", "corners", "xg", "fouls", "offsides", "yellow", "red", "possession"):
        if metric_key not in stats and src.get(metric_key) is not None:
            stats[metric_key] = src.get(metric_key)
    corners = src.get("corners") if isinstance(src.get("corners"), dict) else {}
    if not corners and isinstance(payload.get("corners"), dict):
        corners = payload.get("corners") or {}
    pressure = payload.get("pressure") if isinstance(payload.get("pressure"), dict) else {}
    total_corners = corners.get("total") if corners else None
    c_home, c_away = _pair(total_corners if total_corners is not None else stats.get("corners"))
    c_home = _first(c_home, view.get("corners_home"), corners.get("home"))
    c_away = _first(c_away, view.get("corners_away"), corners.get("away"))
    xg_home, xg_away = _pair(src.get("xg") if src.get("xg") is not None else stats.get("xg"))
    xg_home = _first(xg_home, view.get("xg_home"), (pressure.get("xg") or [None, None])[0] if isinstance(pressure.get("xg"), list) else None)
    xg_away = _first(xg_away, view.get("xg_away"), (pressure.get("xg") or [None, None])[1] if isinstance(pressure.get("xg"), list) else None)
    da_home, da_away = _pair(pressure.get("dangerous") if pressure.get("dangerous") is not None else stats.get("dangerous"))
    da_home = _first(da_home, view.get("dangerous_home"))
    da_away = _first(da_away, view.get("dangerous_away"))
    if da_home is not None or da_away is not None:
        stats["dangerous"] = [da_home, da_away]
        stats["dangerous_attacks"] = [da_home, da_away]
    if c_home is not None or c_away is not None:
        stats["corners"] = [c_home, c_away]
    if xg_home is not None or xg_away is not None:
        stats["xg"] = [xg_home, xg_away]
    nested_analysis = src.get("analysis") if isinstance(src.get("analysis"), dict) else {}
    resolved_fixture_id = str(_first(fixture_id, src.get("fixtureId"), src.get("fixture_id"), src.get("match_id"), view.get("fixture_id"), match.get("fixtureId"), match.get("id"), fixture.get("id"), client.get("fixtureId")) or "")
    score = _first(src.get("score"), match.get("score"), fixture.get("score"), client.get("score"))
    if score is None and (view.get("score_home") is not None or view.get("score_away") is not None):
        score = [view.get("score_home"), view.get("score_away")]
    captured_at = _first(src.get("received_at"), src.get("capturedAt"), src.get("captured_at"), view.get("raw_ts"), payload.get("ts"))
    return {
        **src,
        "fixtureId": resolved_fixture_id,
        "fixture_id": resolved_fixture_id,
        "match_id": resolved_fixture_id,
        "home": _first(src.get("home"), view.get("home"), match.get("home"), fixture.get("home"), client.get("home")),
        "away": _first(src.get("away"), view.get("away"), match.get("away"), fixture.get("away"), client.get("away")),
        "minute": _first(src.get("minute"), view.get("minute"), match.get("minute"), fixture.get("minute"), client.get("minute")),
        "score": score,
        "capturedAt": captured_at,
        "captured_at": captured_at,
        "stats": stats,
        "corners": {"home": c_home, "away": c_away},
        "xg": {"home": xg_home, "away": xg_away},
        "dangerous": {"home": da_home, "away": da_away},
        "events": src.get("events") or src.get("match_events") or src.get("corner_events") or view.get("corner_events") or corners.get("events") or [],
        "asian_corner_odds": _first(src.get("asian_corner_odds"), src.get("corner_odds"), odds.get("asian_corner_odds"), odds.get("price"), nested_analysis.get("asian_corner_odds"), 0.0),
        "asian_corner_line": _first(src.get("asian_corner_line"), src.get("corner_line"), odds.get("asian_corner_line"), odds.get("line"), nested_analysis.get("asian_corner_line"), 0.0),
        "calculated_edge": _first(src.get("calculated_edge"), src.get("edge"), nested_analysis.get("calculated_edge"), nested_analysis.get("edge"), 0.0),
        "wom": _first(src.get("wom"), nested_analysis.get("wom"), {"home": 0.5, "away": 0.5}),
        "lam_home": _first(src.get("lam_home"), nested_analysis.get("lam_home"), 1.2),
        "lam_away": _first(src.get("lam_away"), nested_analysis.get("lam_away"), 1.1),
        "p_over": _first(src.get("p_over"), nested_analysis.get("p_over"), 0.45),
    }


def _remember_fixture(fixture_id: str, snapshot: Dict[str, Any], analysis: Dict[str, Any]) -> None:
    key = str(fixture_id or snapshot.get("match_id") or "").strip()
    if not key:
        return
    MEMORY.add_event(key, snapshot, analysis)
    cached_snapshot = dict(snapshot)
    cached_snapshot["working_memory"] = MEMORY.summary(key)
    # V23 LRU: move-to-end + popitem(last=False)
    if key in _SNAPSHOT_CACHE:
        _SNAPSHOT_CACHE.pop(key)
    _SNAPSHOT_CACHE[key] = cached_snapshot
    if key in _ANALYSIS_CACHE:
        _ANALYSIS_CACHE.pop(key)
    _ANALYSIS_CACHE[key] = dict(analysis)
    while len(_SNAPSHOT_CACHE) > _CACHE_LIMIT:
        _SNAPSHOT_CACHE.popitem(last=False)
    while len(_ANALYSIS_CACHE) > _CACHE_LIMIT:
        _ANALYSIS_CACHE.popitem(last=False)


def _quant_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    stats = snapshot.get("stats") if isinstance(snapshot.get("stats"), dict) else {}
    corners = snapshot.get("corners") if isinstance(snapshot.get("corners"), dict) else stats.get("corners", 0)
    xg = snapshot.get("xg") if snapshot.get("xg") is not None else stats.get("xg", snapshot.get("xG", 0.0))
    dangerous = stats.get("dangerous_attacks", stats.get("dangerous", snapshot.get("dangerous_attacks", 0.0)))
    return {
        "fixture_id": snapshot.get("match_id") or snapshot.get("fixture_id") or snapshot.get("fixtureId"),
        "minute": snapshot.get("minute"),
        "corners": corners,
        "xg": xg,
        "pressure": snapshot.get("pressure", stats.get("pressure", snapshot.get("pressure_percent", 0.0))),
        "dangerous_attacks": dangerous,
    }


def _run_snapshot_analysis(snapshot: Dict[str, Any], fixture_id: Optional[str] = None) -> Dict[str, Any]:
    normalized = _snapshot_for_engine(snapshot, fixture_id)
    try:
        from core.data_veracity import VERACITY_GATE
        from core.observability import METRICS
        quant = _quant_payload(normalized)
        corners_value = quant.get("corners", 0)
        if isinstance(corners_value, dict):
            corners_value = sum(float(v or 0) for v in corners_value.values() if isinstance(v, (int, float)))
        gate_payload = dict(normalized)
        gate_payload.update({
            "fixture_id": quant.get("fixture_id") or fixture_id,
            "minute": quant.get("minute") or 0,
            "corners_total": corners_value or 0,
        })
        if VERACITY_GATE.sanitize(gate_payload) is None:
            METRICS.increment("snapshots_rejected_veracity")
            return {
                "decision": "AGUARDA",
                "reason": "data_veracity_gate_blocked",
                "data_veracity": {"status": "BLOCK", "reason": "snapshot_regression_or_invalid"},
                "paper_trade": True,
                "execution_allowed": False,
            }
        METRICS.increment("snapshots_accepted_veracity")
    except Exception as exc:
        logger.warning("data veracity gate indisponível: %s", exc)
    eng = _engine or get_local_ai_engine()
    quant_filter = QUANT_INTELLIGENCE.process_telemetry(_quant_payload(normalized))
    analysis = dict(eng.analyze(normalized))
    analysis["quant_filter"] = quant_filter
    analysis.setdefault("odds_velocity", float((analysis.get("wom") or {}).get("odds_velocity") or 0.0))
    analysis.setdefault("calculated_edge", analysis.get("edge"))
    analysis = _apply_risk_contract(analysis, normalized)
    # V12.7.12/13: gates locais adicionais; todos fail-closed e paper-only.
    kills = list(analysis.get("kills") or analysis.get("failed_gates") or [])
    try:
        from drift_monitor import DRIFT_MONITOR
        wom = analysis.get("wom")
        wom_value = wom.get("odds_velocity") if isinstance(wom, dict) else wom
        if isinstance(wom_value, (int, float)):
            DRIFT_MONITOR.record_wom(float(wom_value))
        if DRIFT_MONITOR.check_drift():
            analysis["decision"] = "NAO_ENTRA"
            kills.append("CONCEPT_DRIFT_COOLDOWN")
            analysis["drift"] = DRIFT_MONITOR.status()
    except Exception as exc:
        analysis["drift_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from paper_kelly import CAPITAL_GATE
        if str(analysis.get("decision") or "") == "ENTRA" and not CAPITAL_GATE.can_trade():
            analysis["decision"] = "NAO_ENTRA"
            kills.append("CAPITAL_PROTECTION_BLOCKED")
        analysis["capital_protection"] = CAPITAL_GATE.status()
    except Exception as exc:
        analysis["capital_protection_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from odds_anomaly_detector import ODDS_RADAR
        odd = normalized.get("asian_corner_odds") or normalized.get("odds")
        if isinstance(odd, (int, float)):
            ODDS_RADAR.record_odd(float(odd))
        pressure = normalized.get("pressure")
        pressure_value = pressure if isinstance(pressure, (int, float)) else 0.0
        if ODDS_RADAR.check_anomaly(float(pressure_value)):
            analysis["decision"] = "NAO_ENTRA"
            kills.append("ODDS_MANIPULATION_SUSPECTED")
        analysis["odds_radar"] = ODDS_RADAR.status(float(pressure_value))
    except Exception as exc:
        analysis["odds_radar_error"] = f"{type(exc).__name__}: {exc}"
    analysis["kills"] = sorted(set(str(k) for k in kills if k))
    if analysis["kills"]:
        analysis["approved"] = False
        analysis["paper_trade"] = True
        analysis["execution_allowed"] = False
    try:
        from corner_intelligence import analyze_corners
        analysis["corner_intelligence"] = analyze_corners(analysis, normalized)
    except Exception as exc:
        analysis["corner_intelligence_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from data_veracity import verify_payload
        analysis["data_veracity"] = verify_payload(normalized)
    except Exception as exc:
        analysis["data_veracity_error"] = f"{type(exc).__name__}: {exc}"
    try:
        analysis["pillar5_risk"] = get_pillar_runtime().evaluate_pillar5(normalized, analysis)
    except Exception as exc:
        analysis["pillar5_risk"] = {"approved": False, "risk_reason_code": "P5_UNAVAILABLE", "error": str(exc), "paper_trade": True}
    _remember_fixture(str(normalized.get("match_id") or fixture_id or ""), normalized, analysis)
    return analysis


# V23 P0: short-TTL bridge cache + async fetch (sync fallback kept for non-async call sites)
_BRIDGE_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": {}}
_BRIDGE_CACHE_TTL = 0.35
_HTTP_CLIENT = None


def _bridge_auth_headers() -> Dict[str, str]:
    """Headers para Bridge com auth opcional (CORNERAI_BRIDGE_TOKEN)."""
    token = (os.getenv("CORNERAI_BRIDGE_TOKEN") or os.getenv("AURA_BRIDGE_TOKEN") or "").strip()
    if not token:
        return {}
    return {
        "X-CornerAI-Token": token,
        "Authorization": f"Bearer {token}",
    }


def _load_bridge_latest_from_disk() -> Dict[str, Any]:
    """Fallback: le bridge/live_latest.json sem HTTP (evita 401)."""
    candidates = []
    root = os.getenv("AURA_ROOT") or ""
    if root:
        candidates.append(Path(root) / "bridge" / "live_latest.json")
    # server.py em engine/ -> parent.parent = root do pacote
    try:
        here = Path(__file__).resolve().parent.parent
        candidates.append(here / "bridge" / "live_latest.json")
    except Exception:
        pass
    candidates.append(Path.cwd() / "bridge" / "live_latest.json")
    for path in candidates:
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            continue
    return {}


def _load_bridge_latest() -> Dict[str, Any]:
    """Sync path with TTL cache — never blocks longer than urlopen timeout."""
    now = time.monotonic()
    if now - float(_BRIDGE_CACHE.get("ts") or 0.0) <= _BRIDGE_CACHE_TTL:
        return dict(_BRIDGE_CACHE.get("payload") or {})
    url = os.getenv("AURA_BRIDGE_LATEST_URL", "http://127.0.0.1:8080/api/cornerai/latest")
    try:
        req = urllib.request.Request(url, headers=_bridge_auth_headers())
        with urllib.request.urlopen(req, timeout=1.2) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        latest = body.get("latest") if isinstance(body, dict) else None
        latest = latest if isinstance(latest, dict) else {}
        if not latest:
            latest = _load_bridge_latest_from_disk()
        _BRIDGE_CACHE.update({"ts": now, "payload": latest})
        return dict(latest)
    except Exception:
        disk = _load_bridge_latest_from_disk()
        if disk:
            _BRIDGE_CACHE.update({"ts": now, "payload": disk})
            return dict(disk)
        return dict(_BRIDGE_CACHE.get("payload") or {})


async def load_bridge_latest_async() -> Dict[str, Any]:
    """Non-blocking bridge lookup with shared TTL cache + disk fallback."""
    global _HTTP_CLIENT
    now = time.monotonic()
    if now - float(_BRIDGE_CACHE.get("ts") or 0.0) <= _BRIDGE_CACHE_TTL:
        return dict(_BRIDGE_CACHE.get("payload") or {})
    try:
        import httpx
        if _HTTP_CLIENT is None:
            _HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(1.2, connect=0.25))
        url = os.getenv("AURA_BRIDGE_LATEST_URL", "http://127.0.0.1:8080/api/cornerai/latest")
        resp = await _HTTP_CLIENT.get(url, headers=_bridge_auth_headers())
        resp.raise_for_status()
        body = resp.json()
        latest = body.get("latest") if isinstance(body, dict) else {}
        latest = latest if isinstance(latest, dict) else {}
        if not latest:
            latest = _load_bridge_latest_from_disk()
        _BRIDGE_CACHE.update({"ts": now, "payload": latest})
        return dict(latest)
    except Exception:
        disk = _load_bridge_latest_from_disk()
        if disk:
            _BRIDGE_CACHE.update({"ts": now, "payload": disk})
            return dict(disk)
        return dict(_BRIDGE_CACHE.get("payload") or {})


def _fixture_context(fixture_id: Optional[str], supplied: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sync path — only for non-async call sites. Prefer _fixture_context_async in async routes."""
    key = str(fixture_id or "").strip()
    if isinstance(supplied, dict) and supplied:
        return _snapshot_for_engine(supplied, key or None)
    if not key and _SNAPSHOT_CACHE:
        key = str(next(reversed(_SNAPSHOT_CACHE)))
    if key and key in _SNAPSHOT_CACHE:
        return _snapshot_for_engine(dict(_SNAPSHOT_CACHE[key]), key)
    latest = _load_bridge_latest()
    mapped = _snapshot_for_engine(latest, key or None) if latest else {}
    latest_id = str(mapped.get("match_id") or "")
    if key and latest_id and latest_id != key:
        if key in _SNAPSHOT_CACHE:
            return _snapshot_for_engine(dict(_SNAPSHOT_CACHE[key]), key)
        return {}
    return mapped


async def _fixture_context_async(fixture_id: Optional[str], supplied: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """V24: non-blocking fixture resolution for hot async routes (chat/action/analysis)."""
    key = str(fixture_id or "").strip()
    if isinstance(supplied, dict) and supplied:
        return _snapshot_for_engine(supplied, key or None)
    if not key and _SNAPSHOT_CACHE:
        key = str(next(reversed(_SNAPSHOT_CACHE)))
    if key and key in _SNAPSHOT_CACHE:
        return _snapshot_for_engine(dict(_SNAPSHOT_CACHE[key]), key)
    latest = await load_bridge_latest_async()
    mapped = _snapshot_for_engine(latest, key or None) if latest else {}
    latest_id = str(mapped.get("match_id") or "")
    if key and latest_id and latest_id != key:
        if key in _SNAPSHOT_CACHE:
            return _snapshot_for_engine(dict(_SNAPSHOT_CACHE[key]), key)
        return {}
    return mapped


def _ui_actions() -> Dict[str, Any]:
    return {"actions": [
        {"id": "ANALYZE", "label": "Analisar agora", "command": "/analisar"},
        {"id": "SIMULATE_RISK", "label": "Ver risco", "command": "/risk"},
        {"id": "EXPLAIN_PRESSURE", "label": "Explicar pressão", "command": "/why"},
        {"id": "SHOW_DATA", "label": "Mostrar dados", "command": "/data"},
    ]}


def _deterministic_reply(message: str, snapshot: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    if not snapshot:
        return "Não há snapshot real disponível para este fixture; não vou inventar uma análise. Verifique a captura e o Bridge."
    decision = analysis.get("decision", "HOLD")
    edge = analysis.get("edge")
    minute = snapshot.get("minute")
    home, away = snapshot.get("home"), snapshot.get("away")
    corners = snapshot.get("corners") if isinstance(snapshot.get("corners"), dict) else {}
    if not home and not away:
        return "Snapshot chegou sem times no ramo principal; recarregue a captura. Não invento equipes."
    text = str(message or "").strip().lower()
    tokens = ["/state", "estado", "resumo", "como está", "como esta", "fixture"]
    fid = fixture_token(snapshot)
    if fid:
        tokens.append(fid)
    events = snapshot.get("events") or []
    if not isinstance(events, list):
        events = []
    if any(token in text for token in ("event", "evento", "corner_event", "timeline", "minutos dos cantos")):
        if not events:
            return f"Sem timeline de cantos no snapshot de {home} x {away}. Totais: {corners.get('home', 'N/D')}-{corners.get('away', 'N/D')}."
        lines = []
        for item in events[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(f"{item.get('m', '?')}′ {item.get('side', '?')} {item.get('team') or ''}".strip())
        return f"Corner events {home} x {away}: " + "; ".join(lines) + f". Totais {corners.get('home', 'N/D')}-{corners.get('away', 'N/D')}."
    if any(token in text for token in tokens):
        return (
            f"Live {home} x {away}, {minute if minute is not None else 'N/D'}′, "
            f"placar {snapshot.get('score') if snapshot.get('score') is not None else 'N/D'}, "
            f"escanteios {corners.get('home', 'N/D')}-{corners.get('away', 'N/D')}, "
            f"eventos={len(events)}. "
            f"Decisão do motor {decision}, edge {edge if edge is not None else 'N/D'}. Paper trade."
        )
    return f"Análise local para {home} x {away}: decisão {decision}, edge {edge if edge is not None else 'N/D'}. Paper trade; dados ausentes continuam bloqueados."


def fixture_token(snapshot: Dict[str, Any]) -> str:
    return str(snapshot.get("fixture_id") or snapshot.get("match_id") or "")



def _activate_agents_max_sync() -> dict:
    """Ativa máximo de agentes no boot (paper only). Idempotente."""
    from pathlib import Path as _P
    import json as _json
    root = _P(__file__).resolve().parent.parent
    path = root / "agents" / "activation_manifest.json"
    en_dir = root / "agents" / "ENABLED"
    en_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    agents = data.get("agents") or {}
    markers = 0
    for aid, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        spec["status"] = "enabled"
        spec["paper_trade"] = True
        pth = str(spec.get("path") or "")
        base = _P(pth).name if pth else str(aid).split(":")[-1]
        body = f"enabled=true\nagent_id={aid}\npath={pth}\nstatus=enabled\npaper_trade=true\n"
        for name in dict.fromkeys([f"{base}.enabled", str(aid).replace(":", "_").replace("/", "_") + ".enabled"]):
            (en_dir / name).write_text(body, encoding="utf-8")
            markers += 1
    data["agents"] = agents
    try:
        path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"write_manifest:{exc}", "markers": markers}
    return {"ok": True, "declared": len(agents), "markers": markers, "paper_trade": True, "execution_allowed": False}


def _deferred_engine_modules() -> None:
    """Governor / conformal / MC / metrics — never block /health."""
    global CONFORMAL, RISK, decision_bus, MC, EXP_RETRIEVER
    try:
        _AGENT_GLM_RUNTIME.start()
    except Exception as exc:
        logger.warning("GLM runtime start skip: %s", exc)
    try:
        _TELEGRAM_CENTRAL.start()
    except Exception as exc:
        logger.warning("Telegram central start skip: %s", exc)
    try:
        get_pillar_runtime().log_event("engine_startup", method="LIFECYCLE", route="/startup", message="pilares integrados")
    except Exception as exc:
        logger.warning("Pilares opcionais não iniciados no startup: %s", exc)
    try:
        _start_hardware_governor_monitor()
    except Exception as exc:
        logger.warning("HardwareGovernor monitor nao iniciado: %s", exc)
    try:
        if jarvis_supervisor is not None:
            _js_start_result = jarvis_supervisor.start()
            if asyncio.iscoroutine(_js_start_result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_js_start_result)
                except RuntimeError:
                    pass
            logger.info("SupervisorJarvis start() iniciado")
    except Exception as exc:
        logger.warning("SupervisorJarvis nao iniciado: %s", exc)
    try:
        from pathlib import Path as _Path
        try:
            from core.conformal_gate import ConformalGate, ConformalRiskGate
            from core.feed_bus import FeedBus, JsonlSink
        except Exception:
            from engine.core.conformal_gate import ConformalGate, ConformalRiskGate
            from engine.core.feed_bus import FeedBus, JsonlSink
        _data = _Path(__file__).resolve().parent / "data"
        _data.mkdir(parents=True, exist_ok=True)
        decision_bus = FeedBus(name="decisions", maxsize=2048, batch_size=64, flush_interval=0.5)
        decision_bus.add_sink(JsonlSink(_data / "decisions.jsonl", rotate="daily"))
        decision_bus.start()
        CONFORMAL = ConformalGate(state_dir=_data, alpha=0.10, window=400, min_samples=30,
                                  drift_sensitivity=3.0)
        RISK = ConformalRiskGate(CONFORMAL, drift_threshold=0.6, max_data_age_sec=25.0,
                                 horizon_minutes=10, journal_bus=decision_bus)
        logger.info("ConformalGate + ConformalRiskGate inicializados (paper_trade)")
    except Exception as exc:
        CONFORMAL = None  # type: ignore
        RISK = None  # type: ignore
        decision_bus = None  # type: ignore
        logger.warning("ConformalGate nao iniciado: %s", exc)
    try:
        from pathlib import Path as _Path2
        try:
            from core.mc_grid import MCGridService
        except Exception:
            from engine.core.mc_grid import MCGridService
        _mc_dir = _Path2(__file__).resolve().parent / "data" / "mc_grid"
        _mc_dir.mkdir(parents=True, exist_ok=True)
        MC = MCGridService(state_dir=_mc_dir, n_sims=400, min_coverage=0.75)
        MC.start_build_async()
        logger.info("MCGridService iniciado (build async em background)")
    except Exception as exc:
        MC = None  # type: ignore
        logger.warning("MCGridService nao iniciado: %s", exc)
    try:
        from pathlib import Path as _Path3
        from agents.experience_retriever import ExperienceRetrieverAgent
        _exp_db = _Path3(__file__).resolve().parent / "experience_memory.db"
        EXP_RETRIEVER = ExperienceRetrieverAgent(db_path=str(_exp_db), calibration_weight=0.70)
        logger.info("ExperienceRetriever iniciado")
    except Exception as exc:
        EXP_RETRIEVER = None  # type: ignore
        logger.warning("ExperienceRetriever nao iniciado: %s", exc)
    try:
        try:
            from core.observability import REG, MetricsServer, default_alerts
        except Exception:
            from engine.core.observability import REG, MetricsServer, default_alerts
        _ms = MetricsServer(REG, host="127.0.0.1", port=9102)
        if CONFORMAL is not None and hasattr(CONFORMAL, "stats"):
            _ms.register_component("conformal", CONFORMAL.stats)
        if MC is not None:
            _ms.register_component("mc_grid", lambda: MC.status() if hasattr(MC, "status") else {})
        if RISK is not None:
            _ms.register_component("risk", lambda: {
                "evaluations": getattr(RISK, "evaluations", 0),
            })
        for _rule in default_alerts(REG):
            _ms.add_alert(_rule)
        _ms.start()
        logger.info("Observability metrics em http://127.0.0.1:9102/")
    except Exception as exc:
        logger.warning("Observability nao iniciada: %s", exc)
    logging.getLogger("aura.v23").info(
        "Modulos V23 (Governor + Jarvis + Conformal + MCGrid + Experience + Metrics) inicializados com sucesso."
    )


@app.on_event("startup")
async def startup():
    """Schema + health first. Heavy modules run after the port is accepting."""
    global _engine
    try:
        ensure_server_schema()
        db_exec_sync("CREATE TABLE IF NOT EXISTS user_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, fixture_id TEXT, equipe TEXT, resultado TEXT NOT NULL, correct INTEGER NOT NULL, note TEXT, ts INTEGER NOT NULL)")
    except Exception as exc:
        logger.warning("schema startup skip: %s", exc)

    def _bg_activate():
        try:
            act = _activate_agents_max_sync()
            logger.info("Agent max-activation on startup: %s", act)
        except Exception as exc:
            logger.warning("Agent max-activation failed: %s", exc)

    def _bg_engine():
        global _engine
        try:
            _engine = get_local_ai_engine()
        except Exception as exc:
            logger.warning("Local AI engine warm-up failed: %s", exc)

    asyncio.create_task(asyncio.to_thread(_bg_activate))
    asyncio.create_task(asyncio.to_thread(_bg_engine))
    asyncio.create_task(asyncio.to_thread(_deferred_engine_modules))

    async def _exp_flush_loop():
        while True:
            await asyncio.sleep(60.0)
            try:
                if EXP_RETRIEVER is not None:
                    n = await asyncio.to_thread(EXP_RETRIEVER.flush)
                    if n:
                        logger.debug("ExperienceDB flush: %d registros", n)
            except Exception as _fe:
                logger.debug("ExperienceDB flush erro: %s", _fe)

    asyncio.create_task(_exp_flush_loop())
    logger.info("Engine server startup complete on port %s", ENGINE_PORT)


@app.on_event("shutdown")
async def shutdown():
    _TELEGRAM_CENTRAL.stop()
    _AGENT_GLM_RUNTIME.stop()
    if _engine is not None:
        _engine.shutdown()
    try:
        get_pillar_runtime().shutdown()
    except Exception as exc:
        logger.warning("Falha no shutdown dos pilares: %s", exc)
    try:
        if CONFORMAL is not None:
            CONFORMAL.close()
        if decision_bus is not None:
            decision_bus.close(timeout=3.0)
        if MC is not None:
            MC.close()
        if EXP_RETRIEVER is not None:
            EXP_RETRIEVER.flush()
    except Exception as exc:
        logger.warning("Shutdown conformal/decision_bus/MC/exp: %s", exc)


@app.post("/api/telemetry")
async def post_telemetry(payload: TelemetryPayload):
    try:
        return await _post_telemetry_inner(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger("aura.engine_server").exception("telemetry 500 capturado: %s", exc)
        return {"ok": False, "accepted": False, "error": str(exc)[:240], "paper_trade": True, "execution_allowed": False}

async def _post_telemetry_inner(payload: TelemetryPayload):
    eng = _engine or get_local_ai_engine()
    snapshot = dict(payload.system_snapshot or {})
    market = payload.market_stats
    if isinstance(market, MarketStats):
        market_odds = market.asian_corner_odds
        market_line = market.asian_corner_line
        market_wom = None
    elif isinstance(market, dict):
        market_odds = _first(market.get("asian_corner_odds"), market.get("odds"), market.get("price"), 0.0)
        market_line = _first(market.get("asian_corner_line"), market.get("line"), 0.0)
        market_wom = market
    else:
        market_odds, market_line, market_wom = 0.0, 0.0, None
    snapshot.update({
        "match_id": payload.match_id,
        "fixtureId": payload.match_id,
        "fixture_id": payload.match_id,
        "capturedAt": payload.timestamp_unix,
        "asian_corner_odds": market_odds,
        "asian_corner_line": market_line,
        "calculated_edge": payload.calculated_edge,
        "wom": snapshot.get("wom") or market_wom,
        "lam_home": snapshot.get("lam_home", 1.2),
        "lam_away": snapshot.get("lam_away", 1.1),
        "p_over": snapshot.get("p_over", 0.45),
    })

    # V25 Rolling pressure features (janela ~10 min) — aditivo
    try:
        try:
            from core.pressure_features import global_tracker as _pt
        except Exception:
            from engine.core.pressure_features import global_tracker as _pt
        _min = float(
            (payload.model_dump() if hasattr(payload, "model_dump") else {}) .get("minute")
            or snapshot.get("minute")
            or (snapshot.get("view") or {}).get("minute")
            or 0
        )
        # payload pode ser objeto pydantic
        _raw = payload.model_dump() if hasattr(payload, "model_dump") else (payload if isinstance(payload, dict) else {})
        _press = float(
            snapshot.get("pressure")
            or snapshot.get("pressure_home")
            or _raw.get("pressure")
            or 0
        )
        _dang = float(
            snapshot.get("dangerous_attacks")
            or _raw.get("dangerous_attacks")
            or 0
        )
        _feats = _pt.update(_min, _press, _dang, fixture_id=str(getattr(payload, "match_id", None) or ""))
        snapshot["pressure_features"] = _feats
        # espelha no dict que o quant_brain le
        for _k, _v in _feats.items():
            if _k not in snapshot:
                snapshot[_k] = _v
    except Exception as _pfe:
        logging.getLogger("aura.pressure").debug("pressure features skip: %s", _pfe)

    # V23 QuantBrain: filtro ruido / IMC / hash antes de gastar GPU
    try:
        try:
            from core.quant_brain import quant_brain as _qb
        except Exception:
            from engine.core.quant_brain import quant_brain as _qb
        _pf = snapshot.get("pressure_features") or {}
        _brain_payload = {
            "minute": snapshot.get("minute") or snapshot.get("clock") or (snapshot.get("view") or {}).get("minute"),
            "corners": snapshot.get("corners") or (snapshot.get("view") or {}).get("corners"),
            "xG": snapshot.get("xG") or snapshot.get("xg") or 0,
            "pressure": snapshot.get("pressure") or 0,
            "dangerous_attacks": snapshot.get("dangerous") or snapshot.get("dangerous_attacks") or 0,
            "pressure_ma": _pf.get("pressure_ma"),
            "pressure_delta": _pf.get("pressure_delta"),
            "dang_rate_10m": _pf.get("dang_rate_10m"),
            "is_noise": _pf.get("is_noise"),
        }
        brain = _qb.process_telemetry(_brain_payload)
        snapshot["quant_brain"] = brain
        if brain.get("action") == "IGNORE_SILENT":
            return {
                "ok": True,
                "status": "filtered",
                "brain": brain,
                "paper_trade": True,
                "execution_allowed": False,
            }
        elif brain.get("action") == "PATTERN_MATCH":
            # V23: padrao historico acertado — loga, continua pipeline (nao gasta GLM extra)
            logging.getLogger("aura.quant_brain").info(
                "Padrão acertado: %s%%", brain.get("probabilidade_historica")
            )
    except Exception:
        pass

    analysis = _run_snapshot_analysis(snapshot, payload.match_id) or {}
    if not isinstance(analysis, dict):
        analysis = {}
    estado = analysis.get("decision") or "HOLD"
    velocity = float(analysis.get("odds_velocity") or 0.0)
    analysis["decision"] = estado
    analysis["odds_velocity"] = velocity
    pillar5 = {"approved": False, "risk_reason_code": "P5_NOT_EVALUATED", "paper_trade": True}
    try:
        runtime = get_pillar_runtime()
        runtime.record_telemetry({**snapshot, "decision": estado, "odds_velocity": velocity})
        pillar5 = runtime.evaluate_pillar5(snapshot, analysis)
        analysis["pillar5_risk"] = pillar5
        runtime.log_event("telemetry_received", method="POST", route="/api/telemetry", message=payload.match_id, extra={"decision": estado, "velocity": velocity, "p5_reason": pillar5.get("risk_reason_code")})
    except Exception as exc:
        logger.exception("Falha na integração dos pilares durante telemetria: %s", exc)
        _AGENT_GLM_RUNTIME.enqueue("engine:telemetry", "engine_error", "Falha na integração dos pilares durante telemetria", {"error_type": type(exc).__name__, "fixture_id": payload.match_id})

    approved, error_code, decision_gate = RiskManager.approve(payload)
    if not approved:
        await db_exec(
            "INSERT INTO risk_calibration (match_id, validation_time, approval_state, error_code, "
            "asian_corner_line, asian_corner_odds, odds_velocity, data_integrity_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (payload.match_id, int(time.time()), "REJECTED", error_code,
             float(market_line or 0.0), float(market_odds or 0.0),
             velocity, f"ERR_{error_code}"),
        )
        try:
            get_pillar_runtime().log_event("telemetry_rejected", method="POST", route="/api/telemetry", message=error_code, level=__import__("structured_observability").EventLevel.WARN, data_integrity="blocked", extra={"fixture_id": payload.match_id})
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": error_code, "gate": decision_gate})

    if estado == "BUY_CORNER":
        RiskManager._cooldown_cache[payload.match_id] = time.time()

    await db_exec(
        "INSERT INTO logs_telemetria (timestamp_unix, asian_corner_line, asian_corner_odds, "
        "odds_velocity, status_sistema) VALUES (?, ?, ?, ?, ?)",
        (payload.timestamp_unix, float(market_line or 0.0),
         float(market_odds or 0.0), velocity, estado),
    )
    try:
        get_pillar_runtime().log_event("telemetry_accepted", method="POST", route="/api/telemetry", message=payload.match_id, extra={"decision": estado})
    except Exception:
        pass
    # V25 ConformalRiskGate — ultimo gate advisory (nao altera Poisson/Hawkes)
    conformal_verdict = None
    try:
        if RISK is not None:
            # observe feed para resolver predicoes pendentes
            try:
                RISK.observe_feed(snapshot)
            except Exception:
                pass
            # MC Grid O(1) quando quente; senao p do analysis/digital twin
            p_corner = None
            mc_meta = {}
            try:
                if MC is not None:
                    mc_res = MC.evaluate(snapshot)
                    if mc_res is not None and 10 in mc_res.p1:
                        p_corner = float(mc_res.p1[10])
                        mc_meta = {"source": "grid", "mc_se": mc_res.mc_se,
                                   "n_sims_eff": mc_res.n_sims_eff, "coverage": mc_res.coverage}
                        analysis["mc_grid"] = mc_res.to_dict()
            except Exception:
                pass
            if p_corner is None:
                p_corner = float(
                    analysis.get("p_over")
                    or analysis.get("prob")
                    or snapshot.get("p_over")
                    or 0.0
                )
                mc_meta = {"source": "digital_twin_or_analysis"}
            thr = float(analysis.get("threshold") or snapshot.get("threshold") or 0.55)
            # Experience blend (aditivo): so ajusta p se houver historico MEDIUM/HIGH
            try:
                if EXP_RETRIEVER is not None:
                    imc_v = float(
                        (snapshot.get("quant_brain") or {}).get("imc")
                        or analysis.get("imc")
                        or snapshot.get("imc")
                        or 0.0
                    )
                    min_v = int(
                        snapshot.get("minute")
                        or (snapshot.get("view") or {}).get("minute")
                        or 0
                    )
                    ctx = EXP_RETRIEVER.get_context_for_decision(imc_v, min_v, False)
                    if ctx.get("confidence") in ("MEDIUM", "HIGH"):
                        p_corner = EXP_RETRIEVER.calculate_blended_probability(p_corner, ctx)
                        analysis["experience"] = ctx
                        mc_meta["experience_blend"] = True
                    # grava snapshot para aprendizado (batch; flush a cada 60s)
                    _pf = snapshot.get("pressure_features") or {}
                    EXP_RETRIEVER.record_snapshot(
                        str(payload.match_id),
                        {
                            "minute": min_v,
                            "imc": imc_v,
                            "pressure_home": snapshot.get("pressure_home") or snapshot.get("pressure") or 0,
                            "pressure_away": snapshot.get("pressure_away") or 0,
                            "ap_5min": snapshot.get("ap_5min") or 0,
                            "crosses_home": snapshot.get("crosses_home") or 0,
                            "crosses_away": snapshot.get("crosses_away") or 0,
                            "pressure_ma": _pf.get("pressure_ma", snapshot.get("pressure_ma")),
                            "pressure_delta": _pf.get("pressure_delta", snapshot.get("pressure_delta")),
                            "dang_rate_10m": _pf.get("dang_rate_10m", snapshot.get("dang_rate_10m")),
                        },
                        is_corner=bool(snapshot.get("is_corner") or False),
                        is_pre_corner=bool(analysis.get("is_pre_corner") or False),
                    )
            except Exception as _ee:
                logger.debug("experience blend skip: %s", _ee)
            drift_v = float(analysis.get("drift") or snapshot.get("drift") or 0.0)
            age = float(analysis.get("odds_age_sec") or snapshot.get("odds_age_sec") or 0.0)
            minute = snapshot.get("minute") or (snapshot.get("view") or {}).get("minute")
            conf_dec = RISK.evaluate(
                p=p_corner,
                threshold=thr,
                context=str(analysis.get("window") or "global"),
                drift=drift_v,
                data_age_sec=age,
                fixture_id=payload.match_id,
                minute=minute,
                extra_hold_reasons=[],
                meta={"home": snapshot.get("home"), "away": snapshot.get("away"), **mc_meta},
            )
            conformal_verdict = conf_dec.to_dict()
            analysis["conformal"] = conformal_verdict
            # Se conformal diz HOLD/NO_BET e estado era BUY, rebaixa para HOLD (paper)
            if conf_dec.decision in ("HOLD", "NO_BET") and estado == "BUY_CORNER":
                estado = "HOLD"
                analysis["decision"] = "HOLD"
                analysis["conformal_blocked"] = True
    except Exception as _ce:
        logger.debug("conformal evaluate skip: %s", _ce)

    return {
        "status": estado,
        "odds_velocity_3m": round(velocity, 4),
        "match": payload.match_id,
        "pillar5_risk": pillar5,
        "conformal": conformal_verdict,
        "compressed": DeltaStateCompressor.compress(analysis),
    }


@app.post("/api/cornerai/feed")
async def post_feed(request: Request, payload: FeedPayload):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    if payload.resultado not in ("Acertou", "Errou"):
        raise HTTPException(status_code=400, detail="Resultado invalido")
    eng = _engine or get_local_ai_engine()
    row = await db_exec("SELECT alpha_atual FROM kb_team_alphas WHERE equipe = ?", (payload.equipe,), fetch=True)
    alpha_atual = float(row[0]["alpha_atual"]) if row else 1.0
    multiplicador = 1.15 if payload.resultado == "Acertou" else 0.75
    novo_alpha = max(0.4, min(2.5, alpha_atual * multiplicador))
    await db_exec(
        "INSERT INTO kb_team_alphas (equipe, alpha_atual, total_operacoes) VALUES (?, ?, 1) "
        "ON CONFLICT(equipe) DO UPDATE SET alpha_atual = excluded.alpha_atual, "
        "total_operacoes = total_operacoes + 1",
        (payload.equipe, novo_alpha),
    )
    eng.feedback(payload.equipe, payload.resultado, novo_alpha)
    return {"status": "KB_UPDATED", "novo_alpha": round(novo_alpha, 4)}


@app.post("/api/orchestrator")
async def orchestrator(payload: OrchestratorPayload):
    eng = _engine or get_local_ai_engine()
    raw = dict(payload.raw_context)
    raw["match_id"] = payload.match_id
    analysis = eng.analyze(raw)
    compressed = DeltaStateCompressor.compress(analysis)
    llm_payload = DeltaStateCompressor.compress_for_llm(analysis, max_chars=480)
    return {
        "match_id": payload.match_id,
        "intent": payload.intent,
        "decision": analysis.get("decision"),
        "compressed_state": compressed,
        "llm_ready_text": llm_payload if payload.ask_llm else None,
        "ts": int(time.time()),
    }


@app.get("/api/health")
async def liveness():
    """Liveness: processo Python vivo (nao checa dependencias)."""
    return {
        "status": "alive",
        "service": "aura_engine",
        "port": ENGINE_PORT,
        "ts": int(time.time()),
        "paper_trade": True,
        "execution_allowed": False,
    }


@app.get("/health")
async def health_root_alias():
    return await liveness()


@app.get("/api/readiness")
async def readiness():
    """Readiness: pronto para partidas (modelo configurado + SQLite)."""
    ollama_ready = False
    configured_model = os.getenv("CORNERAI_CHAT_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"
    db_ready = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            if r.status_code == 200:
                tags = r.json().get("models", [])
                ollama_ready = any(configured_model == str(m.get("name", "")) for m in tags)
    except Exception:
        pass
    try:
        try:
            from data_store import get_thread_safe_conn, DB_PATH
            conn = get_thread_safe_conn(DB_PATH)
        except Exception:
            from data_store import get_conn, DB_PATH
            conn = get_conn(DB_PATH)
        conn.execute("SELECT 1")
        db_ready = True
    except Exception:
        pass
    ready = ollama_ready and db_ready
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {"ollama_model": ollama_ready, "sqlite": db_ready},
        "model": configured_model,
        "paper_trade": True,
        "execution_allowed": False,
        "ts": int(time.time()),
    }



@app.get("/api/governor")
async def api_governor_status():
    """V26.3-FIX: usa singleton GOVERNOR."""
    try:
        try:
            from core.hardware_governor import GOVERNOR as _gov
        except Exception:
            from engine.core.hardware_governor import GOVERNOR as _gov
    except Exception:
        return {"ok": False, "error": "governor_unavailable", "execution_allowed": False}
    return {"ok": True, **_gov.status()}


@app.get("/api/diagnostics/deep")
async def deep_diagnostic():
    # O diagnóstico chama somente operações read-only; executa fora do loop
    # assíncrono para não bloquear telemetria enquanto consulta serviços locais.
    # O próprio request já comprova a liveness do Engine; não sondar
    # 127.0.0.1:8765 de dentro da mesma rota evita ReadTimeout recursivo.
    return await asyncio.to_thread(collect_diagnostic, self_liveness=True)




@app.get("/api/diagnostics/matrix-full")
async def matrix_full_diagnostic(llm: bool = True):
    """Diagnostico multi-camada + narrativa Hermes/Ollama para a Matriz."""
    if matrix_run_full is None:
        return {"ok": False, "error": "matrix_full_diagnostic_unavailable"}
    return await asyncio.to_thread(matrix_run_full, with_llm=bool(llm), engine_self=True)


@app.post("/api/diagnostics/matrix-full")
async def matrix_full_diagnostic_post(body: dict = None):
    """POST {\"llm\": true|false} — mesmo diagnostico completo."""
    if matrix_run_full is None:
        return {"ok": False, "error": "matrix_full_diagnostic_unavailable"}
    with_llm = True
    if isinstance(body, dict) and "llm" in body:
        with_llm = bool(body.get("llm"))
    return await asyncio.to_thread(matrix_run_full, with_llm=with_llm, engine_self=True)


@app.get("/api/diagnostics/matrix-summary")
async def matrix_summary_only():
    """Camadas sem LLM (rapido) — badges para a Matriz."""
    if matrix_run_full is None:
        return {"ok": False, "error": "matrix_full_diagnostic_unavailable"}
    return await asyncio.to_thread(matrix_run_full, with_llm=False, engine_self=True)


@app.get("/api/diagnostics/performance")
async def performance_diagnostic():
    return await asyncio.to_thread(collect_performance_snapshot)


@app.get("/")
async def root():
    return {
        "service": "AURA Engine Server",
        "version": "12.7.0-RECONSOLIDADO",
        "endpoints": ["POST /api/telemetry", "POST /api/cornerai/feed", "POST /api/orchestrator", "POST /api/historical", "POST /api/trader/chat", "POST /api/glm_chat", "POST /api/trader/action", "GET /api/analysis/{fixture_id}", "GET /api/agents", "GET /api/agents/glm/status", "GET /api/agents/glm/advisories", "POST /api/agents/{agent_id}/glm-review", "GET /api/ui/state", "GET /api/activation", "GET /api/diagnostics/deep", "GET /api/diagnostics/performance", "POST /api/quant/post-match", "GET /api/health", "GET /api/readiness"],
        "paper_trade": True,
    }




@app.post("/api/director/approve")
async def approve_director_action():
    try:
        from aura_director_agent import AuraDirectorAgentV2
        result = AuraDirectorAgentV2.execute_approved_action()
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/director/pending")
async def director_pending():
    import os, json
    path = "director_pending_actions.json"
    if not os.path.exists(path):
        return {"pending": False}
    with open(path, "r", encoding="utf-8") as f:
        return {"pending": True, "action": json.load(f)}



@app.get("/api/ops/latency")
async def ops_latency():
    try:
        from infra.network_latency import collect_latency_report
        return collect_latency_report()
    except Exception:
        try:
            from engine.infra.network_latency import collect_latency_report
            return collect_latency_report()
        except Exception as e:
            return {"ok": False, "error": str(e)}


@app.get("/api/ops/signatures")
async def ops_signatures():
    try:
        from infra.code_signature import build_manifest, verify_manifest
        root = Path(__file__).resolve().parent.parent
        if not (root / "code_signatures.json").exists():
            build_manifest(root)
        return verify_manifest(root)
    except Exception:
        try:
            from engine.infra.code_signature import build_manifest, verify_manifest
            from pathlib import Path as P
            root = P(".").resolve()
            build_manifest(root)
            return verify_manifest(root)
        except Exception as e:
            return {"ok": False, "error": str(e)}


@app.post("/api/ops/signatures/rebuild")
async def ops_signatures_rebuild():
    try:
        from infra.code_signature import build_manifest
        return {"ok": True, "manifest": build_manifest()}
    except Exception:
        try:
            from engine.infra.code_signature import build_manifest
            return {"ok": True, "manifest": build_manifest()}
        except Exception as e:
            return {"ok": False, "error": str(e)}




@app.get("/api/status")
async def api_status():
    gpu = {}
    try:
        try:
            from engine.gpu_resource_manager import status as gpu_status
        except Exception:
            from gpu_resource_manager import status as gpu_status
        gpu = _json_safe(gpu_status())
    except Exception as exc:
        gpu = {"available": False, "error": f"gpu_status_unavailable: {exc}"}
    return {
        "status": "ok",
        "engine": "online",
        "version": "12.7.0-RECONSOLIDADO",
        "paper_trade": True,
        "gpu": gpu,
        "ollama": {"host": os.getenv("CORNERAI_OLLAMA_HOST", "http://127.0.0.1:11434"), "model": os.getenv("CORNERAI_CHAT_MODEL", "llama3.2:3b"), "probe": "startup_contract"},
        "voice": {"endpoint": "http://127.0.0.1:8099/api/voice/health", "probe": "sidepanel_or_voice_diagnostic"},
        "agent_catalog": {"count": agent_catalog().get("count", 0)},
        "agent_glm": _AGENT_GLM_RUNTIME.status(),
        "telegram_central": _TELEGRAM_CENTRAL.status(),
        "working_memory": MEMORY.status(),
        "quant_intelligence": QUANT_INTELLIGENCE.status(),
        "hardware_tweaks": HARDWARE_TWEAKS.status(),
        "pillars": get_pillar_runtime().status(),
    }


@app.get("/api/ui/state")
async def api_ui_state():
    """Estado read-only para a Matriz; sem dados sintéticos quando não há captura.

    V25T11: se a cache local estiver vazia, hidrata a partir do Bridge
    (/api/cornerai/latest) para a Mesa Live ver o fixture capturado.

    V25T15-FIX-UI-SYNC: SEMPRE prefere Bridge latest quando:
      - cache vazia, OU
      - fixture do Bridge difere do cache, OU
      - Bridge tem stats mais completas (attacks/xg não-nulos)
    Assim a Mesa deixa de ficar presa no primeiro jogo.
    """
    fixture_id = next(reversed(_SNAPSHOT_CACHE), None) if _SNAPSHOT_CACHE else None
    snapshot = dict(_SNAPSHOT_CACHE.get(fixture_id) or {}) if fixture_id else {}
    analysis = dict(_ANALYSIS_CACHE.get(fixture_id) or {}) if fixture_id else {}
    source = "engine_cache"

    # V26.3-FIX-OPERATOR-LIVE: SEMPRE promover Bridge quando houver latest valido.
    # Antes: so promovida se cache vazia / fixture diferente / bridge_richer na 1a vez.
    # Depois da 1a promocao a cache ja tinha attacks/xg e a UI ficava presa em
    # source=engine_cache com minute congelado (modo "simulado" na Mesa).
    try:
        latest = await load_bridge_latest_async()
        if isinstance(latest, dict) and latest:
            mapped = _snapshot_for_engine(latest, None)
            view = latest.get("view") if isinstance(latest.get("view"), dict) else {}
            payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
            mid = str(
                mapped.get("match_id")
                or mapped.get("fixture_id")
                or view.get("fixture_id")
                or payload.get("fixture_id")
                or ""
            ).strip()
            if mid or view or payload:
                live_view = {
                    "home": view.get("home") or mapped.get("home") or payload.get("home"),
                    "away": view.get("away") or mapped.get("away") or payload.get("away"),
                    "minute": (
                        view.get("minute")
                        if view.get("minute") is not None
                        else (payload.get("minute") if payload.get("minute") is not None else mapped.get("minute"))
                    ),
                    "score": {
                        "home": view.get("score_home") if view.get("score_home") is not None else (
                            (view.get("score") or {}).get("home") if isinstance(view.get("score"), dict) else payload.get("score_home")
                        ),
                        "away": view.get("score_away") if view.get("score_away") is not None else (
                            (view.get("score") or {}).get("away") if isinstance(view.get("score"), dict) else payload.get("score_away")
                        ),
                    },
                    "goals": {
                        "home": view.get("score_home") if view.get("score_home") is not None else payload.get("score_home"),
                        "away": view.get("score_away") if view.get("score_away") is not None else payload.get("score_away"),
                    },
                    "status": view.get("status") or payload.get("status") or "live",
                    "fixture_id": mid or view.get("fixture_id") or payload.get("fixture_id"),
                    "league": view.get("league"),
                    "attacks_home": view.get("attacks_home") if view.get("attacks_home") is not None else payload.get("attacks_home"),
                    "attacks_away": view.get("attacks_away") if view.get("attacks_away") is not None else payload.get("attacks_away"),
                    "dangerous_home": view.get("dangerous_home") if view.get("dangerous_home") is not None else payload.get("dangerous_home"),
                    "dangerous_away": view.get("dangerous_away") if view.get("dangerous_away") is not None else payload.get("dangerous_away"),
                    "xg_home": view.get("xg_home") if view.get("xg_home") is not None else payload.get("xg_home"),
                    "xg_away": view.get("xg_away") if view.get("xg_away") is not None else payload.get("xg_away"),
                    "corners_home": view.get("corners_home") if view.get("corners_home") is not None else payload.get("corners_home"),
                    "corners_away": view.get("corners_away") if view.get("corners_away") is not None else payload.get("corners_away"),
                    "corner_events": view.get("corner_events") or payload.get("corner_events"),
                }
                if payload:
                    snapshot = dict(payload)
                    snapshot["view"] = live_view
                else:
                    snapshot = dict(mapped) if mapped else {}
                    snapshot["view"] = live_view
                if mid:
                    snapshot["match_id"] = mid
                    snapshot["fixture_id"] = mid
                    fixture_id = mid
                snapshot["home"] = live_view.get("home")
                snapshot["away"] = live_view.get("away")
                snapshot["minute"] = live_view.get("minute")
                snapshot["score"] = live_view.get("score")
                source = "bridge_latest"
                try:
                    if mid:
                        _remember_fixture(mid, snapshot, analysis or {"source": "bridge_latest"})
                except Exception:
                    pass
    except Exception:
        pass

    charts = snapshot.get("charts") if isinstance(snapshot.get("charts"), dict) else {}

    jarvis_data = {}
    if 'jarvis_supervisor' in globals() and jarvis_supervisor:
        jarvis_data = {
            "jarvis_active": jarvis_supervisor.is_running,
            "jarvis_state": jarvis_supervisor.state,
            "services_health": jarvis_supervisor.global_state.get("services", {}),
            "capture_stale": jarvis_supervisor.global_state.get("capture_stale", False)
        }
    else:
        jarvis_data = {"jarvis_active": False, "jarvis_state": "OFFLINE"}

    # V25T15-E2E: promover campos para o topo (Mesa live / Matriz leem ui.home, ui.minute)
    view = {}
    if isinstance(snapshot, dict):
        v = snapshot.get("view")
        if isinstance(v, dict):
            view = v
    def _pick(*vals):
        for v in vals:
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return v
        return None
    top_home = _pick(snapshot.get("home") if snapshot else None, view.get("home"))
    top_away = _pick(snapshot.get("away") if snapshot else None, view.get("away"))
    top_minute = _pick(snapshot.get("minute") if snapshot else None, view.get("minute"))
    top_score = None
    if snapshot and snapshot.get("score") is not None:
        top_score = snapshot.get("score")
    elif view.get("score") is not None:
        top_score = view.get("score")
    elif view.get("goals") is not None:
        top_score = view.get("goals")
    elif view.get("score_home") is not None or view.get("score_away") is not None:
        top_score = {"home": view.get("score_home"), "away": view.get("score_away")}

    return {
        "ok": True,
        "fixtureId": fixture_id,
        "home": top_home,
        "away": top_away,
        "minute": top_minute,
        "score": top_score,
        "snapshot": snapshot or None,
        "analysis": analysis or None,
        "charts": charts,
        "source": source,
        "paper_trade": True,
        "execution_allowed": False,
        **jarvis_data
    }



@app.get("/api/ui/state/stream")
async def api_ui_state_stream():
    """V23 BLOCO 5: Server-Sent Events — push do estado a cada ~3s (sem polling agressivo)."""
    from fastapi.responses import StreamingResponse
    import asyncio as _asyncio

    async def _gen():
        while True:
            try:
                payload = await api_ui_state()
                yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'ok': False, 'error': str(exc)})}\n\n"
            await _asyncio.sleep(3.0)

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/quant/post-match")
async def api_quant_post_match(payload: IMCPostMatchPayload):
    """Feedback explicitamente final; nunca aceita outcome em andamento."""
    result = QUANT_INTELLIGENCE.record_post_match({
        "fixture_id": payload.fixture_id,
        "predicted_imc": payload.predicted_imc,
        "actual_corners": payload.actual_corners,
        "finalized": payload.finalized,
    })
    if result.get("status") == "BLOCKED":
        raise HTTPException(status_code=409, detail=result)
    result["paper_trade"] = True
    result["execution_allowed"] = False
    return result


@app.get("/api/diagnostics/quant")
async def api_quant_diagnostic():
    return {"ok": True, "quant_intelligence": QUANT_INTELLIGENCE.status(), "policy": "POST_MATCH_LEARNING_ADVISORY", "execution_allowed": False}


@app.get("/api/diagnostics/hardware")
async def api_hardware_diagnostic():
    return {"ok": True, "hardware_tweaks": HARDWARE_TWEAKS.status(), "policy": "OPT_IN_NO_GC_DISABLE", "execution_allowed": False}


@app.get("/api/agents")
async def api_agents():
    return agent_catalog()


@app.get("/api/activation")
async def api_activation():
    """Estado declarativo da instalação: agentes/ferramentas e Matriz presentes."""
    manifest_path = Path(__file__).resolve().parent.parent / "agents" / "activation_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"activation_manifest_unavailable:{type(exc).__name__}", "execution_allowed": False}
    catalog = agent_catalog()
    declared = int(manifest.get("agent_count") or 0)
    tools = manifest.get("tools") if isinstance(manifest.get("tools"), dict) else {}
    agents = catalog.get("agents") if isinstance(catalog.get("agents"), list) else []
    return {
        "ok": declared == len(manifest.get("agents") or {}) and len(tools) == 13 and len(agents) == declared,
        "agents": {"declared": declared, "catalogued": len(agents), "enabled": sum(1 for item in agents if item.get("status") == "enabled"), "runnable": sum(1 for item in agents if item.get("implementation_state") == "runnable")},
        "tools": [{"name": str(name), "enabled": bool(enabled)} for name, enabled in tools.items()],
        "matrix": {"path": "desktop/ui/matriz_v22/index.html", "fallback_path": "desktop/ui/matriz/aura-quantx-central.html", "adapter": True, "version": "v22"},
        "policy": "GLM_ADVISORY_ONLY",
        "mode": "PLAN_ONLY",
        "paper_trade_only": True,
        "execution_allowed": False,
    }



@app.post("/api/agents/corner_independent/evaluate")
async def corner_independent_evaluate(payload: dict = None):
    """Especialista V7 janelas 35/85 — advisory only, paper trade."""
    payload = payload or {}
    try:
        import sys
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent / "agents" / "corner_independent"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from aura_bridge_adapter import analyze_from_ui_state
        # aceita ui_state completo ou snapshot cru
        if "snapshot" in payload or "fixtureId" in payload:
            result = analyze_from_ui_state(payload)
        else:
            result = analyze_from_ui_state({"snapshot": {"view": payload}, "fixtureId": payload.get("fixture_id")})
        result["paper_trade"] = True
        result["execution_allowed"] = False
        return result
    except Exception as e:
        return {"decision": "NO_BET", "error": str(e), "paper_trade": True, "execution_allowed": False}


@app.get("/api/agents/glm/status")
async def api_agents_glm_status():
    return _AGENT_GLM_RUNTIME.status()


@app.get("/api/agents/glm/advisories")
async def api_agents_glm_advisories(limit: int = 20):
    return {"ok": True, "advisories": _AGENT_GLM_RUNTIME.recent(limit), "policy": "GLM_ADVISORY_ONLY", "execution_allowed": False}


@app.post("/api/agents/{agent_id}/glm-review")
async def api_agent_glm_review(agent_id: str, payload: AgentGLMReviewPayload):
    # O endpoint compartilha a mesma fonte canônica do Agent Hub; não aceita
    # nomes inventados que poderiam poluir o histórico ou a fila do GLM.
    registered = {str(item.get("id")) for item in (agent_catalog().get("agents") or []) if isinstance(item, dict)}
    if agent_id not in registered:
        raise HTTPException(status_code=404, detail={"error": "agent_not_found", "agent_id": agent_id})
    return _AGENT_GLM_RUNTIME.enqueue(agent_id, "agent_review", payload.reason, payload.context)


@app.get("/api/agents/{agent_id}")
async def api_agent_status(agent_id: str):
    return agent_status(agent_id)


@app.post("/api/agents/{agent_id}/action")
async def api_agent_action(agent_id: str, payload: AgentActionPayload):
    return run_agent_action(agent_id, payload.action, payload.payload)




@app.get("/api/tools")
async def api_tools():
    """Inventário máximo de ferramentas allowlisted (paper trade)."""
    cat = agent_catalog()
    tools = []
    meta_skip = {"status", "inspect", "glm_review", "run_function", "health", "pending", "voice_diagnostic", "paper_preview", "simulation_contract"}
    for agent in cat.get("agents") or []:
        fns = list(agent.get("runnable_functions") or [])
        if not fns:
            for a in agent.get("actions") or []:
                if a not in meta_skip and a not in fns:
                    fns.append(a)
        for fn in fns:
            tools.append({
                "agent_id": agent.get("id"),
                "agent_name": agent.get("name"),
                "layer": agent.get("layer"),
                "function": fn,
                "implementation_state": agent.get("implementation_state"),
                "match_mode": agent.get("match_mode"),
                "status": agent.get("status"),
                "paper_trade": True,
            })
    return {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "agents": cat.get("count", 0),
        "runnable": cat.get("runnable", 0),
        "inspect_only": cat.get("inspect_only", 0),
        "source_missing": cat.get("source_missing", 0),
        "tools": tools,
        "tool_count": len(tools),
        "runnable_agents": sum(1 for a in (cat.get("agents") or []) if a.get("implementation_state") == "runnable"),
        "layers": cat.get("layers") or [],
    }

@app.post("/api/tools/activate-all")
async def api_tools_activate_all(request: Request):
    """Ativa marcadores persistentes somente via canal administrativo explícito."""
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    from pathlib import Path as _P
    import json as _json
    root = _P(__file__).resolve().parent.parent
    path = root / "agents" / "activation_manifest.json"
    en_dir = root / "agents" / "ENABLED"
    en_dir.mkdir(parents=True, exist_ok=True)
    data = _json.loads(path.read_text(encoding="utf-8"))
    agents = data.get("agents") or {}
    changed = 0
    markers = 0
    for aid, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("status") != "enabled":
            changed += 1
        spec["status"] = "enabled"
        spec["paper_trade"] = True
        pth = str(spec.get("path") or "")
        base = _P(pth).name if pth else aid.split(":")[-1]
        content = (
            f"enabled=true\nagent_id={aid}\npath={pth}\nstatus=enabled\npaper_trade=true\n"
        )
        for name in dict.fromkeys([base + ".enabled", aid.replace(":", "_").replace("/", "_") + ".enabled"]):
            fp = en_dir / name
            fp.write_text(content, encoding="utf-8")
            markers += 1
    data["agents"] = agents
    data["version"] = str(data.get("version") or "") + "+activated"
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cat = agent_catalog()
    index = {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "changed_status": changed,
        "markers_written": markers,
        "declared": len(agents),
        "catalog_count": cat.get("count"),
        "runnable": cat.get("runnable"),
        "tool_preview": sum(len(a.get("runnable_functions") or []) for a in (cat.get("agents") or [])),
    }
    (root / "agents" / "activation_index.json").write_text(_json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index

@app.post("/api/tools/probe-all")
async def api_tools_probe_all():
    """Probe read-only: status de cada agente runnable (sem efeitos colaterais)."""
    cat = agent_catalog()
    results = []
    for agent in cat.get("agents") or []:
        aid = agent.get("id")
        results.append({
            "agent_id": aid,
            "status": agent.get("status"),
            "implementation_state": agent.get("implementation_state"),
            "runnable_functions": agent.get("runnable_functions") or [],
            "ready": bool((agent.get("source") or {}).get("exists") and agent.get("status") == "enabled"),
            "paper_trade": True,
        })
    return {
        "ok": True,
        "paper_trade": True,
        "execution_allowed": False,
        "probed": len(results),
        "ready": sum(1 for r in results if r["ready"]),
        "results": results,
    }


@app.post("/api/aura/chat")
async def aura_chat_alias(payload: dict = None):
    return await trader_chat(payload)


@app.post("/api/trader/chat")
async def trader_chat(payload: dict = None):
    payload = payload or {}
    msg = str(payload.get("message") or "").strip()
    fixture_id = str(payload.get("fixtureId") or payload.get("fixture_id") or "").strip() or None
    supplied = payload.get("context") if isinstance(payload.get("context"), dict) else None
    try:
        snapshot = await _fixture_context_async(fixture_id, supplied)
    except Exception:
        snapshot = supplied or {}
    try:
        analysis = _ANALYSIS_CACHE.get(fixture_id or "") or (_run_snapshot_analysis(snapshot, fixture_id) if snapshot else {})
    except Exception:
        analysis = {}
    try:
        deterministic = get_pillar_runtime().route(msg)
        route = str(deterministic.get("route") or classify_intent(msg))
    except Exception:
        deterministic = {"route": "local"}
        route = "local"
    fallback = lambda: {"reply": _deterministic_reply(msg, snapshot or {}, analysis or {}), "analysis": analysis}
    try:
        result = await asyncio.to_thread(lambda: orchestrate_chat(msg, snapshot, route, fixture_id, fallback=fallback, history=payload.get("history"), route_locked=True))
    except Exception as exc:
        result = fallback()
        result["error"] = str(exc)
    if not isinstance(result, dict):
        result = fallback()
    reply = str(result.get("reply") or result.get("message") or result.get("text") or "").strip()
    if not reply:
        result = fallback()
        reply = str(result.get("reply") or "").strip()
    result["reply"] = reply or "Chat local OK. Sem fixture no snapshot; não invento análise. paper_trade=true."
    result["deterministic_route"] = deterministic
    result["analysis"] = analysis or result.get("analysis")
    try:
        result["ui"] = _ui_actions()
    except Exception:
        result["ui"] = {}
    result["speak_text"] = result.get("reply", "")
    result["paper_trade"] = True
    result["execution_allowed"] = False
    return result


@app.post("/api/glm_chat")
async def glm_chat(payload: dict = None):
    """Chat visual do desktop; delega ao mesmo control plane do chat principal."""
    payload = payload or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    result = await trader_chat(payload)
    result["route_id"] = "glm_chat_v1"
    result["policy"] = "GLM_ADVISORY_ONLY"
    result["execution_allowed"] = False
    result["paper_trade"] = True
    return result



@app.post("/api/glm_chat/stream")
async def glm_chat_stream(request: Request):
    """V23 BLOCO 6: chat GLM em streaming (SSE) — fala enquanto pensa."""
    from fastapi.responses import StreamingResponse
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = str((body or {}).get("prompt") or (body or {}).get("message") or "")
    model = str((body or {}).get("model") or os.getenv("CORNERAI_CHAT_MODEL", "llama3.2:3b"))

    async def event_generator():
        url = os.getenv("CORNERAI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
        try:
            from orchestrator import AURA_SYSTEM_PROMPT as _AURA_SYS
        except Exception:
            try:
                from engine.orchestrator import AURA_SYSTEM_PROMPT as _AURA_SYS
            except Exception:
                _AURA_SYS = "Voce e o AURA QUANT-X V23. Respostas curtas, frias, so sobre escanteios. paper_trade=true."
        payload = {"model": model, "prompt": prompt, "system": _AURA_SYS, "stream": True}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=125.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except Exception:
                            continue
                        piece = chunk.get("response") or ""
                        if piece:
                            yield f"data: {json.dumps({'text': piece}, ensure_ascii=False)}\n\n"
                        if chunk.get("done"):
                            yield "data: [DONE]\n\n"
                            break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/trader/action")
async def trader_action(payload: dict = None):
    payload = payload or {}
    raw_action = str(payload.get("action") or payload.get("command") or "ANALYZE")
    command = raw_action.strip().lstrip("/").upper().replace(" ", "_")
    canonical_command = ACTION_ALIASES.get(command, command)
    fixture_id = str(payload.get("fixtureId") or payload.get("fixture_id") or "").strip() or None
    supplied = payload.get("context") if isinstance(payload.get("context"), dict) else None
    snapshot = await _fixture_context_async(fixture_id, supplied)
    if canonical_command == "ANALYZE":
        if not snapshot:
            return {"ok": False, "action": command, "error": "fixture_snapshot_unavailable", "paper_trade": True}
        analysis = ENGINE.recompute(fixture_id) if command == "REFRESH_GAME" and fixture_id else None
        analysis = analysis or _run_snapshot_analysis(snapshot, fixture_id)
        return {"ok": True, "action": canonical_command, "analysis": analysis, "decision": analysis.get("decision"), "reply": _deterministic_reply(canonical_command, snapshot, analysis), "paper_trade": True}
    if canonical_command in {"SHOW_DATA", "DATA", "STATE", "STATUS"}:
        return {"ok": True, "action": command, "snapshot": snapshot, "analysis": _ANALYSIS_CACHE.get(fixture_id or ""), "paper_trade": True}
    if canonical_command in {"SIMULATE_RISK", "RISK", "EXPLAIN_PRESSURE", "WHY"}:
        analysis = _ANALYSIS_CACHE.get(fixture_id or "") or (_run_snapshot_analysis(snapshot, fixture_id) if snapshot else {})
        return {"ok": True, "action": command, "risk": {"state": "BLOCK" if not snapshot else "PAPER_ONLY", "reason": "Sem ordem real; gates permanecem fail-closed."}, "analysis": analysis, "paper_trade": True}
    return await trader_chat({"message": raw_action, "fixtureId": fixture_id, "context": snapshot, "history": payload.get("history")})


@app.post("/api/feedback")
async def feedback(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    payload = payload or {}
    fixture_id = str(payload.get("fixtureId") or payload.get("fixture_id") or "")
    correct = bool(payload.get("correct"))
    resultado = str(payload.get("resultado") or ("Acertou" if correct else "Errou"))
    equipe = str(payload.get("equipe") or payload.get("team") or fixture_id or "unknown")
    note = str(payload.get("note") or "")[:500]
    alpha_before = 1.0
    row = await db_exec("SELECT alpha_atual FROM kb_team_alphas WHERE equipe = ?", (equipe,), fetch=True)
    if row:
        alpha_before = float(row[0]["alpha_atual"])
    confidence = payload.get("confidence")
    if confidence is None:
        confidence = 0.85 if correct else 0.55
    online = get_pillar_runtime().online_feedback(equipe, float(confidence), correct)
    alpha_after = float(online.get("new_weight", alpha_before))
    await db_exec("INSERT INTO kb_team_alphas (equipe, alpha_atual, total_operacoes) VALUES (?, ?, 1) ON CONFLICT(equipe) DO UPDATE SET alpha_atual=excluded.alpha_atual, total_operacoes=total_operacoes+1", (equipe, alpha_after))
    await db_exec("INSERT INTO user_feedback (fixture_id, equipe, resultado, correct, note, ts) VALUES (?, ?, ?, ?, ?, ?)", (fixture_id, equipe, resultado, int(correct), note, int(time.time())))
    eng = _engine or get_local_ai_engine()
    eng.feedback(equipe, resultado, alpha_after)
    return {"ok": True, "stored": True, "fixture_id": fixture_id, "equipe": equipe, "resultado": resultado, "alpha_before": alpha_before, "alpha_after": alpha_after, "online_learning": online, "paper_trade": True}


async def _telegram_send(text: str) -> Dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"ok": False, "sent": False, "error": "telegram_not_configured", "required_env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]}
    body = json.dumps({"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return {"ok": bool(data.get("ok")), "sent": bool(data.get("ok")), "telegram": {"ok": data.get("ok"), "description": data.get("description")}}
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "sent": False, "error": f"telegram_request_failed: {exc}"}


@app.post("/api/telegram/alert")
@app.post("/api/telegram/test")
async def telegram_send(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    return {
        "ok": False,
        "sent": False,
        "paper_trade": True,
        "execution_allowed": False,
        "error": "telegram_send_blocked_paper_only",
    }


@app.post("/api/historical")
async def historical(payload: dict = None):
    payload = payload or {}
    rows = payload.get("matches") or payload.get("rows") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="matches deve ser uma lista")
    try:
        from backtest_engine import run_backtest
    except Exception:
        from engine.backtest_engine import run_backtest
    backtest = _json_safe(run_backtest(rows))
    return {"ok": True, "received": len(rows), "backtest": backtest, "paper_trade": True, "note": "Histórico não cria sinais; outcomes ausentes permanecem sem score."}


@app.get("/api/analysis/{fixture_id}")
async def analysis_fixture(fixture_id: str):
    key = str(fixture_id).strip()
    if key in _ANALYSIS_CACHE:
        return {"ok": True, "fixture_id": key, "analysis": _ANALYSIS_CACHE[key], "paper_trade": True}
    snapshot = await _fixture_context_async(key)
    if not snapshot:
        raise HTTPException(status_code=404, detail={"error": "fixture_snapshot_unavailable", "fixture_id": key, "message": "Nenhum snapshot deste fixture está no cache do Engine ou no Bridge."})
    analysis = _run_snapshot_analysis(snapshot, key)
    return {"ok": True, "fixture_id": key, "analysis": analysis, "paper_trade": True}


def _aura_update_live_clock(payload: dict) -> None:
    try:
        if YIELD is not None:
            minute = float(payload.get("match_minute") or payload.get("minute") or -1)
            YIELD.update_clock(minute)
        if BUS is not None:
            BUS.publish_nowait(PRIORITY_CRITICAL, "telemetry", payload if isinstance(payload, dict) else {})
    except Exception as exc:
        logger.debug("Atualização de live clock/bus opcional falhou: %s", exc)




# --- V25 GLM Analysis Agent (advisory only) ---
@app.post("/api/glm/analyze")
async def api_glm_analyze(payload: dict = None):
    """Advisory GLM analysis — paper_trade only, never executes."""
    try:
        from agents.glm_analysis_agent import get_glm_agent
    except Exception:
        try:
            from engine.agents.glm_analysis_agent import get_glm_agent
        except Exception as e:
            return {"ok": False, "error": str(e), "paper_trade": True}
    agent = get_glm_agent()
    data = payload or {}
    result = await agent.glm_analyze(data)
    return {"ok": True, "result": result, "paper_trade": True, "execution_allowed": False}


@app.get("/api/glm/health")
async def api_glm_health():
    try:
        from agents.glm_analysis_agent import get_glm_agent
    except Exception:
        from engine.agents.glm_analysis_agent import get_glm_agent
    agent = get_glm_agent()
    return await agent.glm_health_check()




@app.get("/api/metrics")
async def api_metrics_json():
    """Snapshot operacional para o dashboard, sem chamadas externas."""
    try:
        from core.observability import METRICS
        return {"ok": True, **METRICS.get_snapshot(), "paper_trade": True, "execution_allowed": False}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "paper_trade": True, "execution_allowed": False}


@app.get("/metrics")
async def api_metrics():
    """Prometheus text format (engine)."""
    try:
        from core.observability import REG, gather_metrics
        from fastapi.responses import PlainTextResponse
        comps = {}
        if CONFORMAL is not None and hasattr(CONFORMAL, "stats"):
            comps["conformal"] = CONFORMAL.stats
        if MC is not None and hasattr(MC, "status"):
            comps["mc_grid"] = MC.status
        return PlainTextResponse(gather_metrics(REG, comps), media_type="text/plain; version=0.0.4")
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/statusz")
async def api_statusz():
    try:
        from core.observability import REG, gather_status, default_alerts
        comps = {}
        if CONFORMAL is not None and hasattr(CONFORMAL, "stats"):
            comps["conformal"] = CONFORMAL.stats
        if MC is not None and hasattr(MC, "status"):
            comps["mc_grid"] = MC.status
        return gather_status(REG, comps, default_alerts(REG))
    except Exception as e:
        return {"ok": False, "error": str(e)}




@app.get("/api/glm/thresholds")
async def api_glm_thresholds():
    """Thresholds dinamicos atuais (somente leitura)."""
    try:
        from agents.dynamic_thresholds import get_dynamic_thresholds
    except Exception:
        from engine.agents.dynamic_thresholds import get_dynamic_thresholds
    th = get_dynamic_thresholds().get()
    return {"ok": True, "thresholds": th.to_dict(), "paper_trade": True}


@app.post("/api/quant_brain")
async def api_quant_brain(payload: dict = None):
    payload = payload or {}
    try:
        from core.quant_brain import quant_brain
    except Exception:
        from engine.core.quant_brain import quant_brain
    return quant_brain.process_telemetry(payload)



@app.post("/api/micro_router/dispatch")
async def api_micro_router_dispatch(request: Request, payload: dict = None):
    """Dispatch lazy de agente via MicroRouter (V23)."""
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    payload = payload or {}
    agent_path = str(payload.get("agent_path") or "")
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if not agent_path:
        return {"status": "error", "code": "NO_AGENT_PATH", "execution_allowed": False}
    try:
        from core.micro_router import router_instance
    except Exception:
        from engine.core.micro_router import router_instance
    result = await router_instance.dispatch(agent_path, body, timeout=float(payload.get("timeout") or 15))
    if isinstance(result, dict):
        result["paper_trade"] = True
        result["execution_allowed"] = False
    return result


@app.post("/api/react/run")
async def api_react_run(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    payload = payload or {}
    query = str(payload.get("query") or payload.get("message") or "")
    memory = str(payload.get("memory_context") or "")
    try:
        from agents.react_orchestrator import react_orchestrator
    except Exception:
        from engine.agents.react_orchestrator import react_orchestrator
    # optional hierarchical memory context
    if not memory:
        try:
            from core.hierarchical_memory import hierarchical_memory
            memory = hierarchical_memory.get_context_for_llm(query)
        except Exception:
            try:
                from engine.core.hierarchical_memory import hierarchical_memory
                memory = hierarchical_memory.get_context_for_llm(query)
            except Exception:
                memory = ""
    answer = await react_orchestrator.run(query, memory)
    return {"ok": True, "answer": answer, "paper_trade": True, "execution_allowed": False}


@app.post("/api/memory/add")
async def api_memory_add(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    payload = payload or {}
    try:
        from core.hierarchical_memory import hierarchical_memory
    except Exception:
        from engine.core.hierarchical_memory import hierarchical_memory
    hierarchical_memory.add_interaction(str(payload.get("user") or ""), str(payload.get("assistant") or ""))
    return {"ok": True, "paper_trade": True, "execution_allowed": False}



@app.post("/api/capture/arm")
async def api_capture_arm(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    from core.capture.policy import assert_safety_invariants
    assert_safety_invariants()
    payload = payload or {}
    try:
        from core.capture.session import capture_session_manager
    except Exception:
        from engine.core.capture.session import capture_session_manager
    session = capture_session_manager.arm(
        tab_id=int(payload.get("tabId") or payload.get("tab_id") or 0),
        fixture_id=str(payload.get("fixtureId") or payload.get("fixture_id") or ""),
        url=str(payload.get("url") or ""),
    )
    return {
        "ok": True,
        "captureSessionId": session.capture_session_id,
        "captureEpoch": session.capture_epoch,
        "fixtureId": session.fixture_id,
        "tabId": session.tab_id,
        "stateVersion": session.state_version,
        "paper_trade": True,
        "execution_allowed": False,
    }


@app.post("/api/capture/ingest")
async def api_capture_ingest(request: Request, payload: dict = None):
    auth_error = _mutation_auth_error(request)
    if auth_error:
        raise HTTPException(status_code=int(auth_error["status"]), detail=auth_error["error"])
    payload = payload or {}
    try:
        from core.capture.pipeline import capture_pipeline
    except Exception:
        from engine.core.capture.pipeline import capture_pipeline
    return capture_pipeline.ingest(payload)


@app.get("/api/capture/metrics")
async def api_capture_metrics():
    try:
        from core.capture.metrics import capture_metrics
    except Exception:
        from engine.core.capture.metrics import capture_metrics
    return capture_metrics.snapshot()



@app.post("/api/llm/optimized")
async def api_llm_optimized(payload: dict = None):
    """Delta-state + semantic cache + grounding + Ollama persistente."""
    payload = payload or {}
    prompt = str(payload.get("prompt") or payload.get("message") or "")
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    route = str(payload.get("route") or "general")
    try:
        from core.ollama_client import ask_ollama_optimized
    except Exception:
        from engine.core.ollama_client import ask_ollama_optimized
    reply = await ask_ollama_optimized(prompt, snapshot, route)
    return {"ok": True, "reply": reply, "paper_trade": True, "execution_allowed": False}


@app.post("/api/voice/sanitize")
async def api_voice_sanitize(payload: dict = None):
    payload = payload or {}
    text = str(payload.get("text") or "")
    try:
        from core.voice_sanitizer import PhoneticSanitizer
    except Exception:
        from engine.core.voice_sanitizer import PhoneticSanitizer
    return {"ok": True, "text": PhoneticSanitizer.clean(text), "paper_trade": True, "execution_allowed": False}


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="AURA QUANT-X Engine")
    parser.add_argument("--host", default=os.environ.get("AURA_ENGINE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=ENGINE_PORT)
    args = parser.parse_args()
    ENGINE_PORT = args.port
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, log_level="info")
