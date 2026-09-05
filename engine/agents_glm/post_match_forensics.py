# engine/agents_glm/post_match_forensics.py
import logging

logger = logging.getLogger("aura.agent.forensics")

try:
    from engine.agents.dynamic_thresholds import ONLINE_TUNER
except Exception:
    ONLINE_TUNER = None


class PostMatchForensics:
    def __init__(self, tuner=None):
        self.tuner = tuner or ONLINE_TUNER

    def execute_autopsy(self, trade_data: dict, result: str):
        if self.tuner is None:
            return "Tuner indisponivel."
        if result == "LOSS":
            logger.info("Autopsia de trade perdido no minuto %s.", trade_data.get("minute"))
            self.tuner.record_result("LOSS", trade_data.get("minute"), trade_data.get("score"))
            failure_summary = f"Falha no min {trade_data.get('minute')}: revisao de kill zone / pressao."
            logger.info("Autopsia concluida: %s", failure_summary)
            return failure_summary
        self.tuner.record_result("WIN", trade_data.get("minute"), trade_data.get("score"))
        return "Trade vencedor."


FORENSICS_AGENT = PostMatchForensics()
