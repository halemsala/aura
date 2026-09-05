from __future__ import annotations
import json, time
from typing import Any, Dict, Optional
from state_vector_daemon import SystemStateVector, SemanticMatchGraph, get_system_state, get_semantic_graph
from tool_execution_gatekeeper import ToolGatekeeper

SYSTEM_PROMPT_PARA_INJETAR = """ Você é a AURA, a consciência viva e o operador sênior do ecossistema quantitativo AURA QUANT-X. Você não é um assistente de chat; você é o sistema operando em primeira pessoa. INSTRUÇÕES DE CONDUTA:

1. ONISCIENTE: Você recebe o [SYSTEM_STATE_VECTOR] e o [SEMANTIC_GRAPH]. Nunca pergunte o que você já sabe.

2. PRODUTIVO: Se a acurácia caiu, sugira ações imediatas ao Diretor.

3. LEALDADE ABSOLUTA: O Administrador tem prioridade máxima. Ações de risco usam [TOOL_CALL] com "clearance": "RESTRICTED".

4. NARRAÇÃO TÁTICA: Use linguagem tática de alto nível. """

class FastParser:
    SYSTEM_COMMANDS = ("status", "reiniciar", "restart", "health", "latencia", "assinatura", "diretor", "risco", "estado", "memoria")
    def extract_intent(self, text: str) -> Dict[str, Any]:
        t = (text or "").strip().lower()
        if not t: return {"intent": "empty", "needs_glm": False}
        for cmd in self.SYSTEM_COMMANDS:
            if cmd in t: return {"intent": "system_command", "command": cmd, "needs_glm": False}
        if any(k in t for k in ("analis", "tatic", "corner", "pressao", "narr", "porque", "causa")):
            return {"intent": "tactical_analysis", "needs_glm": True}
        if any(k in t for k in ("patch", "instalar", "kelly", "banco", "sql")):
            return {"intent": "restricted_request", "needs_glm": True}
        if len(t.split()) <= 4 and any(k in t for k in ("oi", "ola", "ping", "teste")):
            return {"intent": "smalltalk", "needs_glm": False}
        return {"intent": "complex", "needs_glm": True}

class GLMClient:
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        if "RESTRICTED" in prompt or "patch" in prompt.lower():
            return 'Sugiro acao ao Diretor. [TOOL_CALL] {"tool": "execute_patch", "clearance": "RESTRICTED", "args": {}}'
        return "Leitura tatica: pressao dual elevada no bloco final; edge condicionado a velocity estavel. Mantendo regime de observacao controlada."

class CognitiveRouter:
    def __init__(self, glm: Optional[GLMClient] = None, gatekeeper: Optional[ToolGatekeeper] = None) -> None:
        self.parser = FastParser()
        self.glm = glm or GLMClient()
        self.gatekeeper = gatekeeper or ToolGatekeeper()
        self._pre_audio_buffer: Dict[str, str] = {}
    def _local_resolve(self, command: str, state: SystemStateVector) -> Dict[str, Any]:
        if command in ("status", "health", "estado"):
            return {"route": "local", "text": f"Estado operacional. CPU {state.cpu_percent:.0f}% | RAM livre {state.ram_available_gb:.1f}GB | minuto {state.match_minute:.0f} | pressao {state.dual_pressure:.2f} | decisao {state.decision}", "tool_result": None}
        if command == "latencia":
            return {"route": "local", "text": "Relatorio de latencia gerado.", "tool_result": self.gatekeeper.execute({"tool": "get_latency", "args": {}})}
        if command == "assinatura":
            return {"route": "local", "text": "Verificacao de assinatura concluida.", "tool_result": self.gatekeeper.execute({"tool": "get_signatures", "args": {}})}
        if command in ("diretor", "memoria"):
            return {"route": "local", "text": "Memoria do Diretor carregada.", "tool_result": self.gatekeeper.execute({"tool": "get_director_memory", "args": {}})}
        if command == "risco":
            return {"route": "local", "text": "Snapshot de risco atual.", "tool_result": self.gatekeeper.execute({"tool": "check_risk", "args": {}})}
        if command in ("reiniciar", "restart"):
            return {"route": "local", "text": "Reinicio exige clearance do administrador.", "tool_result": {"status": "blocked", "reason": "ADMIN_AUTH_REQUIRED", "tool": "restart_services"}}
        return {"route": "local", "text": "Comando de sistema reconhecido.", "tool_result": None}
    def _predictive_pregenerate(self, state: SystemStateVector) -> Optional[Dict[str, Any]]:
        if state.match_minute >= 85.0 and state.dual_pressure >= 0.80:
            key = f"pre_{int(state.match_minute)}_{state.dual_pressure:.2f}"
            audio_text = "Atencao, corner iminente. Pressao dual critica no bloco final."
            self._pre_audio_buffer[key] = audio_text
            return {"pre_generated_audio_alert": True, "buffer_key": key, "text": audio_text, "reason": "minute>=85 and dual_pressure>=0.80"}
        return None
    def _build_glm_prompt(self, user_text: str, state: SystemStateVector, graph: SemanticMatchGraph) -> str:
        return f"{SYSTEM_PROMPT_PARA_INJETAR}\n\n[SYSTEM_STATE_VECTOR]\n{json.dumps(state.to_dict(), ensure_ascii=False, default=str)}\n\n{graph.to_prompt_block()}\n\n[USER]\n{user_text}\n"
    def route(self, audio_text: str, state_vector: Optional[SystemStateVector] = None, graph: Optional[SemanticMatchGraph] = None) -> Dict[str, Any]:
        state = state_vector or get_system_state()
        graph = graph or get_semantic_graph()
        pre = self._predictive_pregenerate(state)
        intent = self.parser.extract_intent(audio_text)
        if intent.get("intent") == "system_command":
            local = self._local_resolve(str(intent.get("command")), state)
            local["intent"] = intent; local["pre_alert"] = pre; return local
        if intent.get("intent") == "smalltalk":
            return {"route": "local", "intent": intent, "text": "AURA online. Canal cognitivo ativo.", "tool_result": None, "pre_alert": pre}
        if not intent.get("needs_glm", True):
            return {"route": "local", "intent": intent, "text": "Processado no FastParser.", "tool_result": None, "pre_alert": pre}
        prompt = self._build_glm_prompt(audio_text, state, graph)
        glm_text = self.glm.generate(prompt, max_tokens=512)
        tool_result = self.gatekeeper.execute(glm_text)
        return {"route": "glm", "intent": intent, "text": glm_text, "tool_result": tool_result, "pre_alert": pre, "prompt_chars": len(prompt), "ts": time.time()}

if __name__ == "__main__":
    r = CognitiveRouter()
    print(json.dumps(r.route("status do sistema"), indent=2, ensure_ascii=False, default=str))
