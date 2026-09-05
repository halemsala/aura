# engine/harvesters/playwright_harvester.py
from __future__ import annotations
import asyncio
import json
import hashlib
from typing import Any, Callable, Dict, List, Optional
from playwright.async_api import async_playwright, Page, Request, Response

def global_match_id(home: str, away: str, date_iso: str) -> str:
    raw = f"{home.strip().lower()}|{away.strip().lower()}|{date_iso[:10]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

class PlaywrightHarvester:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._captured: List[Dict[str, Any]] = []
        self._on_payload: Optional[Callable] = None

    def on_payload(self, cb: Callable):
        self._on_payload = cb

    async def intercept_page(self, url: str, url_filter: str = "") -> List[Dict[str, Any]]:
        self._captured = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()

            async def on_response(resp: Response):
                try:
                    u = resp.url
                    if url_filter and url_filter not in u:
                        return
                    if resp.status != 200:
                        return
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct and "text" not in ct:
                        return
                    body = await resp.text()
                    try:
                        data = json.loads(body)
                    except Exception:
                        data = {"raw": body[:500]}
                    item = {"url": u, "data": data, "ts": asyncio.get_event_loop().time()}
                    self._captured.append(item)
                    if self._on_payload:
                        self._on_payload(item)
                except Exception:
                    pass

            page.on("response", on_response)
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            await browser.close()
        return self._captured

# --- V23 BLOCO 6: browser Playwright reutilizado (nao reabre Chrome a cada harvest) ---
class PlaywrightSingleton:
    _playwright = None
    _browser = None
    _context = None

    @classmethod
    def get_browser(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(f"playwright_unavailable:{e}") from e
        if cls._browser is None:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=True)
            cls._context = cls._browser.new_context()
        return cls._browser, cls._context

    @classmethod
    def new_page(cls):
        _, ctx = cls.get_browser()
        return ctx.new_page()

    @classmethod
    def close(cls):
        try:
            if cls._browser:
                cls._browser.close()
        except Exception:
            pass
        try:
            if cls._playwright:
                cls._playwright.stop()
        except Exception:
            pass
        cls._browser = None
        cls._context = None
        cls._playwright = None


