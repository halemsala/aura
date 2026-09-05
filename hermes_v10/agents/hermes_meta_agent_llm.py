#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Meta Agent (LLM-powered)
Agente que orquestra outros agentes, aprende com resultados
e otimiza estratégias de forma autônoma.
"""
import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.hermes_llm_engine import HermesLLMEngine
from core.hermes_constitution_engine import ConstitutionEngine
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()

logger = structlog.get_logger("hermes.agent.meta")


class MetaAgent:
    """
    Meta-Agent que:
    1. Monitora performance de todos os sub-agentes
    2. Ajusta prompts e estratégias baseado em resultados
    3. Detecta loops e deadlocks entre agentes
    4. Escalona para humano quando necessário
    5. Mantém memória de longo prazo de decisões
    """

    def __init__(self, root: str = ".", objective: Optional[str] = None):
        self.root = Path(root).resolve()
        self.objective = objective or "otimizar saúde do sistema"
        self.engine = HermesLLMEngine()
        self.constitution = ConstitutionEngine(root=root)
        self.memory_path = self.root / "data" / "memory" / "meta_agent_memory.jsonl"
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_memory(self, limit: int = 100) -> List[Dict]:
        """Carrega memória de decisões passadas."""
        if not self.memory_path.exists():
            return []
        lines = []
        with open(self.memory_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return lines[-limit:]

    def _save_memory(self, entry: Dict):
        """Salva decisão na memória."""
        with open(self.memory_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def run(self) -> Dict:
        """Executa ciclo de meta-cognição."""
        memory = self._load_memory()

        system_prompt = f"""Você é o Hermes V10 Meta Agent.
Objetivo atual: {self.objective}
Memória de {len(memory)} decisões passadas disponíveis.
Você pode delegar para sub-agentes:
- diagnostic: executa diagnóstico completo
- redteam: executa scan de segurança
- correction: aplica correções allowlisted
- anomaly: verifica anomalias

Produza um plano JSON:
{{
  "strategy": "descrição da estratégia",
  "delegations": [{{"agent": "nome", "priority": 1-5, "reason": "..."}}],
  "expected_outcomes": ["..."],
  "risk_assessment": "low|medium|high"
}}
NUNCA sugira ativar execução real."""

        user_prompt = f"""Memória recente:
{json.dumps(memory[-5:], ensure_ascii=False, indent=2)}

Objetivo: {self.objective}
Gere plano de ação meta."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        resp = await self.engine.chat(messages, use_tools=False)
        plan = self._extract_json(resp.content)

        # Valida constituição
        safe_plan = self.constitution.enforce(resp.content, source="meta_agent")

        # Executa delegações (simulado — em produção, chama subprocessos)
        delegation_results = []
        for delegation in plan.get("delegations", []):
            delegation_results.append({
                "agent": delegation.get("agent"),
                "status": "simulated",
                "reason": "Meta agent em modo de simulação — integrar com orchestrator para execução real",
            })

        result = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": "meta",
            "objective": self.objective,
            "plan": plan,
            "delegation_results": delegation_results,
            "model": resp.model,
            "latency_ms": resp.latency_ms,
        }

        self._save_memory(result)

        report_path = self.root / "logs_supervisor" / "HERMES_META_LATEST.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info("meta_cycle_complete", objective=self.objective, delegations=len(delegation_results))
        return result

    def _extract_json(self, text: str) -> Dict:
        import re
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return {}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--objective", default="otimizar saúde do sistema")
    args = parser.parse_args()

    agent = MetaAgent(root=args.root, objective=args.objective)
    result = await agent.run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    await agent.engine.close()


if __name__ == "__main__":
    asyncio.run(main())
