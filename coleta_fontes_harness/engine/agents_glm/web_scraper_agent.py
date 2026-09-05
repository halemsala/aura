# engine/agents_glm/web_scraper_agent.py
"""Web scraper - WEB_SCRAPE_ENABLED=False por padrao."""
import logging

logger = logging.getLogger("aura.agent.scraper")

WEB_SCRAPE_ENABLED = False


class WebScraperAgent:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0 AuraQuantX/1.0"}

    def scrape_static_site(self, url: str) -> list:
        if not WEB_SCRAPE_ENABLED:
            logger.warning("WEB_SCRAPE_ENABLED=False.")
            return []
        try:
            import requests
            import trafilatura
            response = requests.get(url, headers=self.headers, timeout=10)
            clean_text = trafilatura.extract(response.text)
            if not clean_text:
                return []
            return [p.strip() for p in clean_text.split("\n") if len(p.strip()) > 30]
        except Exception as e:
            logger.error("Erro no scrape estatico: %s", e)
            return []

    def scrape_dynamic_site(self, url: str) -> list:
        if not WEB_SCRAPE_ENABLED:
            return []
        tips = []
        try:
            from playwright.sync_api import sync_playwright
            import trafilatura
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000)
                page.wait_for_selector("body")
                html = page.content()
                browser.close()
                clean_text = trafilatura.extract(html)
                if clean_text:
                    tips = [p.strip() for p in clean_text.split("\n") if len(p.strip()) > 30]
        except Exception as e:
            logger.error("Erro no scrape dinamico: %s", e)
        return tips


SCRAPER_AGENT = WebScraperAgent()
