from __future__ import annotations
import json, logging, re, sqlite3

logger = logging.getLogger("aura.tool_gatekeeper")
from typing import Any, Callable, Dict, Optional

RESTRICTED_TOOLS = {
    "execute_patch", "alter_kelly", "drop_table", "pip_install",
    "modify_db", "run_subprocess", "approve_director_force", "overwrite_engine",
}
AUTONOMOUS_TOOLS = {
    "read_logs", "check_risk", "get_state", "get_director_memory", "get_latency", "get_signatures",
}

class ToolGatekeeper:
    def __init__(self, db_path: str = "aura_quant_x.db") -> None:
        self.db_path = db_path
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "read_logs": self._read_logs, "check_risk": self._check_risk,
            "get_state": self._get_state, "get_director_memory": self._get_director_memory,
            "get_latency": self._get_latency, "get_signatures": self._get_signatures,
        }
    def parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        text = text.strip()
        m = re.search(r"\[TOOL_CALL\]\s*(\{.*?\})", text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except json.JSONDecodeError as exc:
                logger.debug("TOOL_CALL JSON inválido; tentando detecção textual: %s", exc)
        for name in list(RESTRICTED_TOOLS) + list(AUTONOMOUS_TOOLS):
            if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                return {"tool": name, "args": {}, "clearance": "RESTRICTED" if name in RESTRICTED_TOOLS else "AUTO"}
        return None
    def execute(self, tool_spec: Any) -> Dict[str, Any]:
        if isinstance(tool_spec, str):
            parsed = self.parse_tool_call(tool_spec)
            if parsed is None: return {"status": "no_tool", "raw": tool_spec[:300]}
            tool_spec = parsed
        tool = str(tool_spec.get("tool") or tool_spec.get("name") or "").strip().lower()
        args = tool_spec.get("args") or {}
        clearance = str(tool_spec.get("clearance") or "").upper()
        if tool in RESTRICTED_TOOLS or clearance == "RESTRICTED":
            return {"status": "blocked", "reason": "ADMIN_AUTH_REQUIRED", "tool": tool,
                    "message": "Acao restrita interceptada pelo Gatekeeper. Liberacao do administrador obrigatoria."}
        if tool not in AUTONOMOUS_TOOLS:
            return {"status": "blocked", "reason": "UNKNOWN_TOOL", "tool": tool}
        handler = self._handlers.get(tool)
        if handler is None:
            return {"status": "error", "reason": "HANDLER_MISSING", "tool": tool}
        try:
            return {"status": "ok", "tool": tool, "result": handler(args if isinstance(args, dict) else {})}
        except Exception as e:
            return {"status": "error", "tool": tool, "reason": str(e)}
    def _read_logs(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = str(args.get("path") or "runtime_engine.log")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return {"lines": [ln.rstrip() for ln in f.readlines()[-30:]]}
        except OSError as e:
            return {"error": str(e)}
    def _check_risk(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from state_vector_daemon import get_system_state
            st = get_system_state()
            return {"decision": st.decision, "odds_velocity": st.odds_velocity,
                    "dual_pressure": st.dual_pressure, "match_minute": st.match_minute}
        except Exception:
            return {"decision": "HOLD", "note": "state_unavailable"}
    def _get_state(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from state_vector_daemon import get_system_state
            return get_system_state().to_dict()
        except Exception as e:
            return {"error": str(e)}
    def _get_director_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.db_path, timeout=2.0)
            cur = conn.cursor()
            cur.execute("SELECT timestamp, problem_context, action_taken, outcome FROM director_memory ORDER BY id DESC LIMIT 10")
            rows = [{"timestamp": r[0], "problem": r[1], "action": r[2], "outcome": r[3]} for r in cur.fetchall()]
            conn.close(); return {"memory": rows}
        except Exception as e:
            return {"error": str(e)}
    def _get_latency(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from engine.infra.network_latency import collect_latency_report
            return collect_latency_report()
        except Exception as e:
            return {"error": str(e)}
    def _get_signatures(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from engine.infra.code_signature import verify_manifest
            return verify_manifest()
        except Exception as e:
            return {"error": str(e)}

if __name__ == "__main__":
    gk = ToolGatekeeper()
    print(gk.execute('[TOOL_CALL] {"tool": "check_risk", "args": {}}'))
    print(gk.execute('[TOOL_CALL] {"tool": "execute_patch", "clearance": "RESTRICTED"}'))
