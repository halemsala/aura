"""Fetch text only from operator allowlisted URLs. Default allow_scrape=False."""
from __future__ import annotations
from urllib.parse import urlparse
from .config import TelegramIntelConfig

class AllowlistedFetcher:
    def __init__(self, cfg: TelegramIntelConfig | None = None):
        self.cfg = cfg or TelegramIntelConfig.from_env()

    def _allowed(self, url: str) -> bool:
        if not self.cfg.allow_scrape:
            return False
        if not self.cfg.scrape_allowlist:
            return False
        return any(url.startswith(a) for a in self.cfg.scrape_allowlist)

    def fetch_text(self, url: str) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "reason": "disabled", "text": ""}
        if not self._allowed(url):
            return {"ok": False, "reason": "url_not_allowlisted_or_scrape_off", "text": ""}
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "AURA-TelegramIntel-OptIn/0.1"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            # Minimal extract — operator should replace with robust parser per site
            text = " ".join(raw.split())[:8000]
            return {"ok": True, "reason": "fetched", "text": text, "host": urlparse(url).netloc}
        except Exception as e:
            return {"ok": False, "reason": f"fetch_failed:{e}", "text": ""}
