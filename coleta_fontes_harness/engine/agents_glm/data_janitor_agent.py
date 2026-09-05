# engine/agents_glm/data_janitor_agent.py
import logging

logger = logging.getLogger("aura.agent.janitor")


class DataJanitorAgent:
    def __init__(self):
        self.limits = {
            "attack_pressure_diff": (-100, 100),
            "dangerous_attacks_home": (0, 200),
            "corner_rate_15min": (0, 15),
        }

    def sanitize_feed(self, raw_data: dict) -> dict:
        clean_data = {}
        for key, value in raw_data.items():
            if key in self.limits:
                min_val, max_val = self.limits[key]
                try:
                    num = float(value)
                except (TypeError, ValueError):
                    logger.warning("Janitor: valor nao numerico rejeitado %s=%s", key, value)
                    continue
                if not (min_val <= num <= max_val):
                    logger.warning("Anomalia rejeitada pelo Janitor: %s=%s", key, value)
                    continue
            clean_data[key] = value
        return clean_data


DATA_JANITOR = DataJanitorAgent()
