# engine/agents_glm/red_team_adversary.py
"""Red Team Adversary - veto de decisoes (respeita Agent Control Hub)."""
import logging
from typing import Dict

logger = logging.getLogger("aura.agent.red_team")

try:
    from engine.agents.agent_control_hub import CONTROL_HUB
except Exception:
    CONTROL_HUB = None


class RedTeamAdversary:
    def __init__(self):
        self.veto_reasons = []

    def audit_decision(self, features: Dict, aura_decision: Dict) -> Dict:
        if CONTROL_HUB is not None and not CONTROL_HUB.is_active("red_team"):
            logger.info("Red Team pausado. Pulando auditoria.")
            return {"verdict": "APPROVED", "reasons": ["Auditoria manualmente desativada."]}

        self.veto_reasons = []
        ap_diff = features.get("attack_pressure_diff", 0)
        minute = features.get("minute", 0)
        odds = aura_decision.get("odd", 0)

        if odds in [9.00, 10.00, 11.00]:
            if ap_diff < 20:
                self.veto_reasons.append(
                    "Linha .0 com pressao insuficiente para Push ou Saida."
                )

        if features.get("score") == "0-0" and minute > 85:
            self.veto_reasons.append(
                "Kill Zone ativa: Risco altissimo de gol no lugar de escanteio."
            )

        if features.get("shots_off_target", 0) > features.get("corners", 0) * 3:
            self.veto_reasons.append(
                "Dominio esteril: Time chuta de longe, nao forca escanteio."
            )

        if self.veto_reasons:
            return {"verdict": "VETOED", "reasons": self.veto_reasons}
        return {"verdict": "APPROVED", "reasons": ["Tese solida, sem vetos criticos."]}


RED_TEAM = RedTeamAdversary()
