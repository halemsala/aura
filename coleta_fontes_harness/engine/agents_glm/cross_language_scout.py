# engine/agents_glm/cross_language_scout.py
"""Scout GitHub - NETWORK_ENABLED=False por padrao."""
import logging

logger = logging.getLogger("aura.agent.scout")

NETWORK_ENABLED = False


class CrossLanguageScout:
    def __init__(self):
        self.github_api = "https://api.github.com/search/repositories"

    def harvest_alpha(self, topic: str = "football corners prediction model") -> str:
        if not NETWORK_ENABLED:
            return "NETWORK_ENABLED=False. Scout bloqueado (modo supervisao)."
        try:
            import requests
            params = {"q": topic, "sort": "stars", "order": "desc", "per_page": 3}
            headers = {"Accept": "application/vnd.github.v3+json"}
            response = requests.get(self.github_api, params=params, headers=headers, timeout=5)
            if response.status_code == 200:
                items = response.json().get("items", [])
                if items:
                    summary = "Novos modelos quantitativos encontrados:\n"
                    for item in items:
                        summary += (
                            f"- {item['full_name']} (Stars: {item['stargazers_count']}): "
                            f"{item.get('description')}\n"
                        )
                    logger.info("Scout retornou novos Alphas.")
                    return summary
            return "Nenhum modelo novo encontrado."
        except Exception as e:
            return f"Falha na busca externa: {e}"


SCOUT_AGENT = CrossLanguageScout()
