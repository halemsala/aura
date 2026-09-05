"""
AURA QUANT-X :: ReAct Orchestrator (V23 P1)
Structured outputs Pydantic + tools dinamicas. Advisory-only / paper-trade.

PATCH V23-P1 (itens 4.1 e 4.3 da auditoria):
1. Os tres executores mock (_mock_exec_risk / _mock_exec_market /
   _mock_exec_corner) agora chamam RISK_GATES.evaluate() e
   get_system_state() de verdade, em vez de retornar strings fixas. O
   agente passa a raciocinar sobre estado real do sistema.
2. ReActOrchestrator agora herda ReActAgentMixin (engine/core/react_agent.py)
   e usa AgentBudget (engine/agents/controlled_react.py) em vez de um
   try/except solto e um max_iterations desacoplado. A chamada ao LLM
   ganha retry com backoff exponencial automaticamente; falhas
   transitorias (timeout, rate limit) nao abortam mais na primeira
   tentativa.

Import de RISK_GATES e get_system_state e feito dentro das funcoes (nao
no topo do modulo) para preservar o comportamento fail-soft original:
se engine.risk_gates ou state_vector_daemon nao estiverem disponiveis no
processo que importa este orquestrador (ex.: testes isolados), o
orquestrador continua funcionando e reporta a indisponibilidade na
observacao em vez de falhar no import.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from engine.agents.controlled_react import AgentBudget
from engine.core.react_agent import ReActAgentMixin

logger = logging.getLogger("Aura.ReAct")


class ReActStep(BaseModel):
    thought: str = Field(..., description="Raciocinio passo a passo.")
    action: Optional[str] = Field(None, description="Ferramenta ou null se terminou.")
    action_input: Optional[Dict[str, Any]] = Field(None, description="Args JSON.")
    final_answer: Optional[str] = Field(None, description="Resposta final se action=null.")


class FinalAnswer(BaseModel):
    thought: str
    final_answer: str
    action: Literal[None] = None
    action_input: Literal[None] = None


class DynamicToolRegistry:
    def __init__(self):
        self._catalog = {
            "risco": self._get_risk_schema,
            "mercado": self._get_market_schema,
            "escanteio": self._get_corner_schema,
        }
        self._executors = {
            "calculate_risk": self._exec_risk,
            "get_market_odds": self._exec_market,
            "analyze_corners": self._exec_corner,
        }

    def _get_risk_schema(self) -> str:
        return json.dumps({"name": "calculate_risk", "parameters": {"match_id": "string", "stake": "float"}})

    def _get_market_schema(self) -> str:
        return json.dumps({"name": "get_market_odds", "parameters": {"match_id": "string"}})

    def _get_corner_schema(self) -> str:
        return json.dumps({"name": "analyze_corners", "parameters": {"match_id": "string"}})

    def get_relevant_schemas(self, query: str) -> str:
        q = (query or "").lower()
        schemas = [fn() for kw, fn in self._catalog.items() if kw in q]
        if not schemas:
            return "Nenhuma ferramenta especifica. Use conhecimento interno. paper_trade only."
        return "\n".join(schemas)

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        executor = self._executors.get(tool_name)
        if not executor:
            return f"ERRO: Ferramenta {tool_name} nao existe."
        try:
            return await executor(**(args or {}))
        except Exception as e:
            return f"ERRO FATAL NA FERRAMENTA: {e}"

    async def _exec_risk(self, match_id: str = "", stake: float = 0.0) -> str:
        """Chama RISK_GATES.evaluate() de verdade (engine/risk_gates.py).

        stake e recebido apenas para registro/observabilidade: RISK_GATES
        forca kelly=0.0/stake_pct=0.0 (Kelly hard-off, ver risk_gates.py),
        entao nenhum valor de stake enviado aqui influencia a decisao.
        """
        try:
            from engine.risk_gates import RISK_GATES
        except Exception as e:
            return f"risk_gates indisponivel neste processo ({type(e).__name__}); advisory only, execution_allowed=false"
        analysis = {"fixtureId": match_id, "signal": "HOLD"}
        payload = {"fixtureId": match_id, "requested_stake": stake}
        result = RISK_GATES.evaluate(analysis, payload)
        return (
            f"Risco paper-trade {match_id}: decision={result['decision']} "
            f"approved={result['approved']} failed_gates={result['failed_gates']} "
            f"cooldown_active={result['cooldown'].get('active')} "
            f"execution_allowed=false"
        )

    async def _exec_market(self, match_id: str = "") -> str:
        """Consulta o estado real do sistema (state_vector_daemon.py)."""
        try:
            from state_vector_daemon import get_system_state
        except Exception as e:
            return f"Odds indisponiveis: state_vector_daemon nao acessivel ({type(e).__name__}) ({match_id})."
        st = get_system_state()
        return (
            f"Estado atual ({match_id}): odds_velocity={st.odds_velocity:.3f} "
            f"dual_pressure={st.dual_pressure:.3f} match_minute={st.match_minute:.1f} "
            f"decision={st.decision}"
        )

    async def _exec_corner(self, match_id: str = "") -> str:
        """Consulta pressao/minuto reais para padrao de escanteio."""
        try:
            from state_vector_daemon import get_system_state
        except Exception as e:
            return f"Padrao escanteio indisponivel: state_vector_daemon nao acessivel ({type(e).__name__}) ({match_id})."
        st = get_system_state()
        return (
            f"Padrao escanteio ({match_id}): dual_pressure={st.dual_pressure:.3f} "
            f"match_minute={st.match_minute:.1f} pre_alert_ready={st.pre_alert_ready} "
            f"— consultar /api/ui/state e quant_brain para detalhe completo"
        )


class ReActOrchestrator(ReActAgentMixin):
    """
    Herda ReActAgentMixin: chamadas ao LLM ganham retry com backoff
    exponencial via self.react_call(), em vez do try/except solto original.
    REACT_MAX_ATTEMPTS/REACT_BACKOFF_BASE_S sao atributos de instancia lidos
    pelo mixin via getattr (ver engine/core/react_agent.py).
    """

    REACT_MAX_ATTEMPTS = 3
    REACT_BACKOFF_BASE_S = 0.5

    def __init__(
        self,
        llm_client=None,
        tool_registry: Optional[DynamicToolRegistry] = None,
        budget: Optional[AgentBudget] = None,
    ):
        self.llm = llm_client
        self.tools = tool_registry or DynamicToolRegistry()
        # PATCH: max_iterations solto substituido por AgentBudget
        # compartilhado com ControlledReactAgent (engine/agents/controlled_react.py),
        # em vez de duplicar o conceito de limite de passos.
        self.budget = budget or AgentBudget(max_steps=4, max_tool_calls=4)

    async def _call_llm(self, history: List[Dict[str, str]]) -> ReActStep:
        """act_fn para react_call(): uma tentativa de chamada ao LLM."""
        return await self.llm.generate(history, response_model=ReActStep)

    async def run(self, user_query: str, memory_context: str = "") -> str:
        history: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Voce e o agente AURA V23. paper_trade=true. execution_allowed=false.\n"
                    f"Memoria:\n{memory_context}"
                ),
            },
            {"role": "user", "content": user_query},
        ]
        if self.llm is None or not hasattr(self.llm, "generate"):
            # fallback sem LLM estruturado: uma iteracao advisory
            tools_available = self.tools.get_relevant_schemas(user_query)
            return (
                "ReAct sem cliente LLM estruturado. "
                "Use /api/glm_chat com AURA_SYSTEM_PROMPT. "
                f"Tools relevantes:\n{tools_available}"
            )

        steps = 0
        tool_calls = 0
        while steps < self.budget.max_steps:
            tools_available = self.tools.get_relevant_schemas(user_query)
            history[0]["content"] += f"\n\nFERRAMENTAS:\n{tools_available}\nResponda JSON ReActStep."

            # PATCH: chamada ao LLM agora passa por react_call() do mixin —
            # retry automatico com backoff exponencial em falha transitoria
            # (timeout, erro de parsing Pydantic pontual, rate limit), em
            # vez de abortar a conversa inteira no primeiro erro.
            trace = await self.react_call(
                tool_name="llm_generate",
                act_fn=lambda h=list(history): self._call_llm(h),
            )
            if not trace.final_ok:
                last_error = trace.attempts[-1].error if trace.attempts else "erro desconhecido"
                logger.warning("ReAct LLM falhou apos %d tentativas: %s", len(trace.attempts), last_error)
                return f"Erro LLM/Pydantic apos {len(trace.attempts)} tentativas: {last_error}"
            response: ReActStep = trace.attempts[-1].value

            if response.action is None:
                return (response.final_answer or response.thought or "").strip()

            if tool_calls >= self.budget.max_tool_calls:
                return "Limite de chamadas de ferramenta atingido (paper-trade)."

            history.append({"role": "assistant", "content": response.model_dump_json()})
            logger.info("ReAct %s: %s %s", steps + 1, response.action, response.action_input)
            observation = await self.tools.execute(response.action, response.action_input or {})
            history.append({"role": "user", "content": f"OBSERVACAO: {observation}"})
            tool_calls += 1
            steps += 1
        return "Limite de iteracoes atingido (paper-trade)."


react_orchestrator = ReActOrchestrator()
