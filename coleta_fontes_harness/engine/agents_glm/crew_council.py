"""Trading Council.

Tenta CrewAI+Ollama se AURA_CREW_LLM=1 e as libs existirem.
Sempre oferece evaluate_trade() advisory. Sem execução financeira.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("aura.crew")

CREW_ENABLED = os.environ.get("AURA_CREW_LLM", "0").strip() in {"1", "true", "True"}


class TradingCouncil:
    def __init__(self):
        self.quant = None
        self.risk_manager = None
        self.backend = "local-fallback"
        if not CREW_ENABLED:
            logger.info("CrewAI LLM off (AURA_CREW_LLM!=1). Usando conselho local.")
            return
        try:
            from crewai import Agent
            from langchain_community.chat_models import ChatOllama

            llm = ChatOllama(model="llama3.2:3b", base_url="http://127.0.0.1:11434")
            self.quant = Agent(
                role="Analista Quantitativo de Escanteios",
                goal="Encontrar padroes matematicos e de pressao para Over de Escanteios.",
                backstory="Analista baseado em estatisticas de pressao, Hawkes e Poisson. Paper trade only.",
                llm=llm,
                verbose=False,
                allow_delegation=False,
            )
            self.risk_manager = Agent(
                role="Gestor de Risco Adversarial",
                goal="Identificar Kill Zones, linhas .0 perigosas e aplicar vetos.",
                backstory="Gestor de risco. Nunca autoriza ordem real.",
                llm=llm,
                verbose=False,
                allow_delegation=False,
            )
            self.backend = "crewai"
            logger.info("CrewAI council ligado (Ollama).")
        except Exception as exc:
            logger.warning("CrewAI/Ollama indisponivel, fallback local: %s", exc)
            self.backend = "local-fallback"

    def evaluate_trade(self, match_data: str) -> str:
        if self.backend != "crewai" or self.quant is None:
            return f"LOCAL_COUNCIL advisory: {match_data[:240]}"
        try:
            from crewai import Crew, Process, Task

            task_analysis = Task(
                description=(
                    f"Analise advisory (paper_trade=true): {match_data}. "
                    "Veredito: ENTRA ou AGUARDA. Nao execute ordem."
                ),
                agent=self.quant,
                expected_output="Veredito com justificativa matematica.",
            )
            task_risk = Task(
                description=(
                    "Revise a analise. Se houver Push, jogo travado ou Kill Zone, VETE. "
                    "execution_allowed permanece false."
                ),
                agent=self.risk_manager,
                expected_output="Aprovacao ou Veto com justificativa.",
            )
            council = Crew(
                agents=[self.quant, self.risk_manager],
                tasks=[task_analysis, task_risk],
                process=Process.sequential,
            )
            return str(council.kickoff())
        except Exception as exc:
            return f"Erro no Council LLM, fallback local: {exc}"


COUNCIL = TradingCouncil()
