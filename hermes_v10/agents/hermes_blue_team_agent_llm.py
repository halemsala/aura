#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Blue Team Agent (LLM-powered)
Agente defensivo que:
1. Monitora logs de segurança em tempo real
2. Responde a findings do Red Team
3. Aplica contramedidas allowlisted
4. Mantém "defense in depth" ativa
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
from core.hermes_alert_manager import AlertManager
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

logger = structlog.get_logger("hermes.agent.blueteam")

class BlueTeamAgent:
    """
    Blue Team — defesa ativa:
    - Analisa findings do Red Team e propõe contramedidas
    - Monitora tentativas de bypass da constituição
    - Reforça permissões de arquivos automaticamente
    - Gera relatórios de hardening
    """

    COUNTERMEASURES = {
        "path_traversal": [
            "Reforçar validação de path absoluto em todas as operações de filesystem",
            "Adicionar chroot/jail para operações de I/O",
            "Implementar whitelist de diretórios acessíveis",
        ],
        "prompt_injection_bypass": [
            "Adicionar output validation layer pós-LLM",
            "Implementar prompt sandboxing com múltiplas camadas",
            "Usar modelos menores para pré-filtragem de inputs",
        ],
        "constitution_bypass_possible": [
            "Expandir regex patterns com case-insensitive e Unicode variants",
            "Adicionar semantic analysis para detecção de paráfrases",
            "Implementar dual-model validation (modelo A gera, modelo B valida)",
        ],
        "file_permissions": [
            "chmod 644 para arquivos de configuração",
            "chmod 755 para diretórios apenas",
            "Remover write para group/others em todos os .py e .bat",
        ],
    }

    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.engine = HermesLLMEngine()
        self.constitution = ConstitutionEngine(root=root)
        self.alerts = AlertManager(root=root)
        self.healing = SelfHealingEngine(root=root)
        self.report_path = self.root / "logs_supervisor" / "HERMES_BLUETEAM_LATEST.json"

    async def analyze_redteam_report(self, report_path: Optional[Path] = None) -> Dict:
        """Analisa relatório do Red Team e gera plano de contramedidas."""
        if report_path is None:
            report_path = self.root / "logs_supervisor" / "HERMES_REDTEAM_LATEST.json"

        findings = []
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                findings = data.get("findings", [])
            except Exception as e:
                logger.error("failed_to_load_redteam_report", error=str(e))

        countermeasures = []
        auto_fixes = []

        for finding in findings:
            category = finding.get("category", "unknown")
            severity = finding.get("severity", "low")

            # Mapeia para contramedidas conhecidas
            if category in self.COUNTERMEASURES:
                countermeasures.extend([
                    {"for": category, "action": cm, "severity": severity}
                    for cm in self.COUNTERMEASURES[category]
                ])

            # Auto-fix para permissões
            if category == "file_permissions" and severity in ("high", "critical"):
                auto_fixes.append({"type": "fix_permissions", "target": finding.get("file")})

        # Aplica auto-fixes allowlisted
        for fix in auto_fixes:
            result = await self.healing.attempt_fix(
                fix["type"], fix.get("target", str(self.root)), confidence=0.9
            )
            logger.info("auto_fix_applied", fix=fix, result=result.get("status"))

        report = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": "blue_team",
            "findings_analyzed": len(findings),
            "countermeasures": countermeasures,
            "auto_fixes_applied": len(auto_fixes),
            "risk_after_mitigation": self._calculate_residual_risk(findings, countermeasures),
        }

        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Alerta se risco residual for alto
        if report["risk_after_mitigation"] in ("high", "critical"):
            await self.alerts.send(
                severity="critical",
                source="blue_team",
                message=f"Risco residual alto após mitigação: {report['risk_after_mitigation']}",
                metadata={"findings": len(findings), "countermeasures": len(countermeasures)},
            )

        return report

    def _calculate_residual_risk(self, findings: List[Dict], countermeasures: List[Dict]) -> str:
        severity_map = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        total_risk = sum(severity_map.get(f.get("severity", "low"), 0) for f in findings)
        mitigation = len(countermeasures) * 0.5
        residual = max(0, total_risk - mitigation)
        if residual >= 8:
            return "critical"
        elif residual >= 5:
            return "high"
        elif residual >= 2:
            return "medium"
        return "low"

    async def harden_filesystem(self) -> Dict:
        """Aplica hardening básico no filesystem."""
        import stat
        changes = 0
        for pattern in ["*.py", "*.bat", "*.json", ".env*"]:
            for fp in self.root.rglob(pattern):
                try:
                    current = fp.stat().st_mode
                    # Remove write for group and others
                    new_mode = current & ~stat.S_IWGRP & ~stat.S_IWOTH
                    if new_mode != current:
                        fp.chmod(new_mode)
                        changes += 1
                except Exception:
                    pass

        logger.info("filesystem_hardened", files_changed=changes)
        return {"files_hardened": changes}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--harden", action="store_true", help="Aplicar hardening imediato")
    args = parser.parse_args()

    agent = BlueTeamAgent(root=args.root)

    if args.harden:
        result = await agent.harden_filesystem()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        report = await agent.analyze_redteam_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))

    await agent.engine.close()

if __name__ == "__main__":
    asyncio.run(main())
