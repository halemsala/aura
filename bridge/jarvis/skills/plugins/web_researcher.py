# bridge/jarvis/skills/plugins/web_researcher.py
"""
Skill: Web Researcher
Pesquisa na web usando DuckDuckGo.
Requer: pip install duckduckgo-search
"""
import logging
from typing import Dict

logger = logging.getLogger("aura.skill.web")


class Skill:
    def __init__(self):
        self.description = "Pesquisa na web para aprender. Acoes: search_tutorial."

    def run(self, action: str, args: Dict) -> str:
        if action == "search_tutorial":
            query = args.get("query", "")
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=3))
                    if not results:
                        return "Nenhum resultado encontrado na web."
                    response = "Resultados da pesquisa:\n"
                    for r in results:
                        response += f"- {r['title']}: {r['body']}\n"
                    return response
            except Exception as e:
                return f"Erro ao pesquisar: {e}."
        return "Acao de pesquisa nao reconhecida."
