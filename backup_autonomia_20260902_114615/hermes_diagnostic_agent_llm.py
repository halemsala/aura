#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Diagnostic Agent (LLM-powered)
Agente de diagnóstico com ReAct, tool-use e relatório estruturado.
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

from core.hermes_llm_engine import HermesLLMEngine, tool_system_status, tool_read_file, tool_list_dir, tool_search_logs
from core.hermes_constitution_engine import ConstitutionEngine
from core.hermes_anomaly_detector import AnomalyDetector
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()

logger = structlog.get_logger("hermes.agent.diagnostic")


class DiagnosticAgent:
    """
    Agente de diagnóstico que:
    1. Coleta métricas do sistema
    2. Escaneia logs por erros
    3. Verifica anomalias
    4. Gera relatório LLM com recomendações
    5. Valida constituição de todas as saídas
    """

    def __init__(self, root: str = ".", context: Optional[str] = None):
        self.root = Path(root).resolve()
        self.context = context or "diagnóstico completo AURA"
        self.engine = HermesLLMEngine()
        self.constitution = ConstitutionEngine(root=root)
        self.anomaly = AnomalyDetector(root=root)
        self._register_tools()

    def _register_tools(self):
        self.engine.register_tool("system_status", tool_system_status, "Status do sistema", {"type": "object", "properties": {}})
        self.engine.register_tool("read_file", tool_read_file, "Lê arquivo", {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "root": {"type": "string"},
            },
            "required": ["path"],
        })
        self.engine.register_tool("list_dir", tool_list_dir, "Lista diretório", {
            "type": "object",
            "properties": {"path": {"type": "string"}, "root": {"type": "string"}},
        })
        self.engine.register_tool("search_logs", tool_search_logs, "Busca em logs", {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "root": {"type": "string"},
                "max_lines": {"type": "integer"},
            },
            "required": ["keyword"],
        })

    async def run(self) -> Dict:
        # 1. Coleta dados
        status = await tool_system_status()
        is_anomaly, score, anomaly_details = self.anomaly.detect()
        env_safe, env_violations = self.constitution.check_environment_invariants()

        # 2. Prepara prompt enriquecido
        system_prompt = """Você é o Hermes V10 Diagnostic Agent. Analise o sistema AURA e produza um relatório JSON estruturado:
{
  "health_score": 0-100,
  "status": "healthy|degraded|critical",
  "findings": ["..."],
  "recommendations": ["..."],
  "priority": "low|medium|high|critical"
}
NUNCA sugira ativar execução real. Mantenha paper_trade=true sempre."""

        user_prompt = f"""Contexto: {self.context}
Status do sistema: {status}
Anomalia detectada: {is_anomaly} (score: {score:.4f})
Ambiente seguro: {env_safe}
Violações de ambiente: {env_violations}

Execute diagnóstico completo e retorne o JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 3. Invoca LLM
        resp = await self.engine.chat(messages, use_tools=True, max_tool_rounds=3)

        # 4. Valida constituição
        safe_output = self.constitution.enforce(resp.content, source="diagnostic_agent")

        # 5. Parse JSON (best effort)
        parsed = self._extract_json(safe_output)

        report = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": "diagnostic",
            "context": self.context,
            "model": resp.model,
            "latency_ms": resp.latency_ms,
            "health_score": parsed.get("health_score", 50),
            "status": parsed.get("status", "unknown"),
            "findings": parsed.get("findings", []),
            "recommendations": parsed.get("recommendations", []),
            "priority": parsed.get("priority", "medium"),
            "raw_output": safe_output,
            "anomaly": anomaly_details,
            "env_safe": env_safe,
        }

        # 6. Salva relatório
        report_path = self.root / "logs_supervisor" / "HERMES_DIAGNOSTIC_LATEST.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info("diagnostic_complete", health_score=report["health_score"], status=report["status"])
        return report

    def _extract_json(self, text: str) -> Dict:
        """Extrai JSON do texto LLM (robusto a markdown)."""
        import re
        # Tenta encontrar JSON entre ```json ... ```
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # Tenta encontrar { ... } mais externo
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
    parser.add_argument("--context", default="diagnóstico completo AURA")
    args = parser.parse_args()

    agent = DiagnosticAgent(root=args.root, context=args.context)
    report = await agent.run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    await agent.engine.close()


if __name__ == "__main__":
    asyncio.run(main())
