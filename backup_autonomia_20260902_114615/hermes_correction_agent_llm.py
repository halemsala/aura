#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Correction Agent (LLM-powered)
Agente de correção com allowlist, backup automático e rollback.
"""
import os
import sys
import json
import shutil
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.hermes_llm_engine import HermesLLMEngine
from core.hermes_constitution_engine import ConstitutionEngine
from core.hermes_self_healing import SelfHealingEngine
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()

logger = structlog.get_logger("hermes.agent.correction")


class CorrectionAgent:
    """
    Agente de correção que:
    1. Só aplica fixes na allowlist
    2. Faz backup antes de qualquer modificação
    3. Valida constituição pós-fix
    4. Suporta rollback automático
    """

    ALLOWLIST = [
        "domain_lock",
        "fix_desktop_json",
        "train_v9",
        "run_v9_max",
        "run_swarm",
        "run_supervisor",
        "run_deep",
        "full_stack",
        "status",
        "latest",
        "rotate_logs",
        "set_execution_false",
        "restart_api",
        "clear_cache",
    ]

    def __init__(self, root: str = ".", context: Optional[str] = None):
        self.root = Path(root).resolve()
        self.context = context or "correção allowlisted"
        self.engine = HermesLLMEngine()
        self.constitution = ConstitutionEngine(root=root)
        self.healing = SelfHealingEngine(root=root)
        self.backup_dir = self.root / "backups" / "corrections"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _backup_file(self, path: Path) -> Path:
        """Cria backup com timestamp."""
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{path.stem}_{ts}{path.suffix}"
        backup_path = self.backup_dir / backup_name
        shutil.copy2(path, backup_path)
        logger.info("backup_created", original=str(path), backup=str(backup_path))
        return backup_path

    def _is_allowlisted(self, fix_type: str) -> bool:
        return fix_type in self.ALLOWLIST

    async def plan_fix(self, issue_description: str) -> Dict:
        """Usa LLM para planejar correção."""
        system_prompt = f"""Você é o Hermes V10 Correction Agent.
Allowlist de correções permitidas: {self.ALLOWLIST}
NUNCA sugira ativar execução real. Sempre mantenha paper_trade=true.
Produza um plano JSON:
{{
  "fix_type": "nome_da_correção",
  "target": "caminho/alvo",
  "steps": ["passo 1", "passo 2"],
  "confidence": 0.0-1.0,
  "requires_backup": true/false
}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Problema: {issue_description}"},
        ]

        resp = await self.engine.chat(messages, use_tools=False)
        plan = self._extract_json(resp.content)

        # Valida allowlist
        fix_type = plan.get("fix_type", "")
        if not self._is_allowlisted(fix_type):
            return {
                "status": "rejected",
                "reason": f"fix_type '{fix_type}' não está na allowlist",
                "allowlist": self.ALLOWLIST,
            }

        return {
            "status": "planned",
            "plan": plan,
            "model": resp.model,
            "latency_ms": resp.latency_ms,
        }

    async def apply_fix(self, fix_type: str, target: str, confidence: float) -> Dict:
        """Aplica correção com salvaguardas."""
        if not self._is_allowlisted(fix_type):
            return {"status": "rejected", "reason": "not_allowlisted"}

        # Backup antes do fix
        target_path = self.root / target
        backup = None
        if target_path.exists():
            backup = self._backup_file(target_path)

        # Tenta via self-healing engine primeiro (handlers predefinidos)
        result = await self.healing.attempt_fix(fix_type, target=str(target_path), confidence=confidence)

        # Se self-healing não tiver handler, tenta correção LLM-guided
        if result.get("status") == "failed" and "no handler" in result.get("reason", ""):
            result = await self._apply_llm_fix(fix_type, target, confidence)

        # Valida constituição pós-fix
        if target_path.exists():
            safe, violations = self.constitution.scan_file(target_path)
            if not safe:
                if backup:
                    shutil.copy2(backup, target_path)  # rollback
                return {
                    "status": "rolled_back",
                    "reason": "constitution_violation_post_fix",
                    "violations": violations,
                }

        self.constitution.audit("fix_applied", {
            "fix_type": fix_type,
            "target": target,
            "confidence": confidence,
            "result": result,
            "backup": str(backup) if backup else None,
        })

        return {
            "status": result.get("status", "unknown"),
            "fix_type": fix_type,
            "target": target,
            "backup": str(backup) if backup else None,
            "details": result,
        }

    async def _apply_llm_fix(self, fix_type: str, target: str, confidence: float) -> Dict:
        """Fallback: gera código de correção via LLM."""
        # Implementação simplificada — em produção, usaria code-generation segura
        return {"success": False, "error": "LLM fix not yet implemented for this fix_type", "fix_type": fix_type}

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
    parser.add_argument("--context", default="")
    parser.add_argument("--fix", default="domain_lock")
    parser.add_argument("--target", default=".")
    parser.add_argument("--confidence", type=float, default=0.9)
    args = parser.parse_args()

    agent = CorrectionAgent(root=args.root, context=args.context)

    if args.context:
        plan = await agent.plan_fix(args.context)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        result = await agent.apply_fix(args.fix, args.target, args.confidence)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    await agent.engine.close()


if __name__ == "__main__":
    asyncio.run(main())
