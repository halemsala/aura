from __future__ import annotations
import asyncio, json, sqlite3, threading, time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import psutil
try:
    import zmq
    ZMQ_OK = True
except ImportError:
    ZMQ_OK = False

@dataclass
class SystemStateVector:
    ts: float = 0.0
    cpu_percent: float = 0.0
    ram_available_gb: float = 0.0
    ram_percent: float = 0.0
    zmq_telemetry_count: int = 0
    zmq_external_count: int = 0
    last_telemetry: Dict[str, Any] = field(default_factory=dict)
    last_external_signal: Dict[str, Any] = field(default_factory=dict)
    director_memory: List[Dict[str, Any]] = field(default_factory=list)
    surrogate_signal_count: int = 0
    match_minute: float = 0.0
    dual_pressure: float = 0.0
    odds_velocity: float = 0.0
    decision: str = "HOLD"
    pre_alert_ready: bool = False
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SemanticMatchGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, str]] = []
    def add_event(self, minute: float, event: str, cause: str = "", effect: str = "") -> None:
        key = f"time_{int(minute)}"
        self.nodes[key] = {"minute": minute, "event": event, "ts": time.time()}
        if cause:
            self.edges.append({"from": cause, "to": key, "rel": "causa"})
        if effect:
            self.edges.append({"from": key, "to": effect, "rel": "efeito"})
    def to_prompt_block(self) -> str:
        if not self.nodes:
            return "[SEMANTIC_GRAPH] vazio"
        lines = ["[SEMANTIC_GRAPH]"]
        for k, v in sorted(self.nodes.items(), key=lambda x: x[1].get("minute", 0)):
            lines.append(f"  {k}: event={v.get('event')} minute={v.get('minute')}")
        for e in self.edges[-20:]:
            lines.append(f"  edge {e.get('from')} -[{e.get('rel')}]-> {e.get('to')}")
        return "\n".join(lines)

_GLOBAL_STATE = SystemStateVector()
_GLOBAL_GRAPH = SemanticMatchGraph()
_STATE_LOCK = threading.Lock()

def get_system_state() -> SystemStateVector:
    with _STATE_LOCK:
        return SystemStateVector(**_GLOBAL_STATE.to_dict())

def get_semantic_graph() -> SemanticMatchGraph:
    return _GLOBAL_GRAPH

class StateVectorDaemon:
    def __init__(self, db_path: str = "aura_quant_x.db", poll_interval: float = 2.0) -> None:
        self.db_path = db_path
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._zmq_telemetry_count = 0
        self._zmq_external_count = 0
        self._last_telemetry: Dict[str, Any] = {}
        self._last_external: Dict[str, Any] = {}
        # V23 audit: single read connection reused every poll (WAL + query_only)
        self._db_conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.Lock()
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="state-vector-daemon", daemon=True)
        self._thread.start()
        if ZMQ_OK:
            threading.Thread(target=self._zmq_loop, name="state-zmq", daemon=True).start()
    def stop(self) -> None:
        self._stop.set()
    def _get_db(self) -> Optional[sqlite3.Connection]:
        with self._db_lock:
            if self._db_conn is not None:
                try:
                    self._db_conn.execute("SELECT 1")
                    return self._db_conn
                except Exception:
                    try:
                        self._db_conn.close()
                    except Exception:
                        pass
                    self._db_conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=2.0, check_same_thread=False)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA query_only=ON")
                conn.execute("PRAGMA busy_timeout=2000")
                self._db_conn = conn
                return conn
            except Exception:
                return None

    def _read_director_memory(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            conn = self._get_db()
            if conn is None:
                return rows
            cur = conn.cursor()
            cur.execute("SELECT timestamp, problem_context, action_taken, outcome FROM director_memory ORDER BY id DESC LIMIT 5")
            for r in cur.fetchall():
                rows.append({"timestamp": r[0], "problem_context": r[1], "action_taken": r[2], "outcome": r[3]})
        except Exception:
            pass
        return rows
    def _count_surrogate(self) -> int:
        try:
            conn = self._get_db()
            if conn is None:
                return 0
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM external_ai_surrogate WHERE signal_detected = 1")
            n = int(cur.fetchone()[0]); return n
        except Exception:
            return 0
    def _zmq_loop(self) -> None:
        if not ZMQ_OK: return
        try:
            ctx = zmq.Context.instance()
            sub = ctx.socket(zmq.SUB)
            sub.setsockopt_string(zmq.SUBSCRIBE, "")
            sub.connect("tcp://127.0.0.1:5555"); sub.connect("tcp://127.0.0.1:5556")
            while not self._stop.is_set():
                if sub.poll(300):
                    try:
                        msg = sub.recv_string(flags=zmq.NOBLOCK)
                    except Exception:
                        continue
                    if "external_signal" in msg:
                        self._zmq_external_count += 1
                        try:
                            self._last_external = json.loads(msg.split("::", 1)[-1])
                        except Exception:
                            self._last_external = {"raw": msg[:200]}
                    else:
                        self._zmq_telemetry_count += 1
                        try:
                            payload = msg.split("::", 1)[-1] if "::" in msg else msg
                            self._last_telemetry = json.loads(payload)
                            minute = float(self._last_telemetry.get("match_minute") or self._last_telemetry.get("minute") or 0)
                            event = str(self._last_telemetry.get("event") or self._last_telemetry.get("decision") or "tick")
                            _GLOBAL_GRAPH.add_event(minute, event)
                        except Exception:
                            self._last_telemetry = {"raw": msg[:200]}
            sub.close(0)
        except Exception:
            pass
    def _compile_state(self) -> SystemStateVector:
        vm = psutil.virtual_memory()
        tel = self._last_telemetry or {}
        minute = float(tel.get("match_minute") or tel.get("minute") or 0.0)
        pressure = float(tel.get("dual_pressure") or tel.get("pressure") or 0.0)
        velocity = float(tel.get("odds_velocity") or 0.0)
        decision = str(tel.get("decision") or "HOLD")
        return SystemStateVector(
            ts=time.time(), cpu_percent=float(psutil.cpu_percent(interval=0.0)),
            ram_available_gb=round(vm.available / (1024 ** 3), 3), ram_percent=float(vm.percent),
            zmq_telemetry_count=self._zmq_telemetry_count, zmq_external_count=self._zmq_external_count,
            last_telemetry=dict(tel), last_external_signal=dict(self._last_external),
            director_memory=self._read_director_memory(), surrogate_signal_count=self._count_surrogate(),
            match_minute=minute, dual_pressure=pressure, odds_velocity=velocity, decision=decision,
            pre_alert_ready=(minute >= 85.0 and pressure >= 0.80),
        )
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                state = self._compile_state()
                with _STATE_LOCK:
                    for k, v in state.to_dict().items():
                        setattr(_GLOBAL_STATE, k, v)
            except Exception:
                pass
            self._stop.wait(self.poll_interval)
    async def run_async(self) -> None:
        await asyncio.to_thread(self._loop)

if __name__ == "__main__":
    d = StateVectorDaemon(); d.start(); time.sleep(2)
    print(json.dumps(get_system_state().to_dict(), indent=2, default=str)); d.stop()
