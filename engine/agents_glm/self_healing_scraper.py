# engine/agents_glm/self_healing_scraper.py
import logging

logger = logging.getLogger("aura.agent.scraper")


class SelfHealingScraper:
    def __init__(self):
        self.fallback_keywords = {
            "corner": ["cantos", "escanteios", "corners", "ck"],
            "attack": ["ataques", "ataque", "attacks", "perigosos"],
        }

    def find_element_fuzzy(self, dom_nodes: list, target: str):
        target_lower = target.lower()
        for node in dom_nodes:
            if target_lower in str(node).lower():
                return node
        if target_lower in self.fallback_keywords:
            for keyword in self.fallback_keywords[target_lower]:
                for node in dom_nodes:
                    if keyword in str(node).lower():
                        logger.info("Fallback encontrado: '%s' para '%s'.", node, target)
                        return node
        return None


SCRAPER_FUZZY = SelfHealingScraper()
