# engine/surrogate_harvester.py
# AURA QUANT-X — External AI Surrogate Capture Agent
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, Optional

try:
    import zmq
    ZMQ_OK = True
except ImportError:
    ZMQ_OK = False

from playwright.async_api import async_playwright


class ExternalAIAgent:
    def __init__(self, target_url: str, credentials: dict, db_path: str = "aura_quant_local.db"):
        self.target_url = target_url
        self.credentials = credentials
        self.db_path = db_path
        self.context = None
        self.zmq_pub = None
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS external_ai_surrogate ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp REAL, target_site TEXT, page_state TEXT, "
            "signal_detected BOOLEAN, raw_html_snippet TEXT, "
            "corner_happened_next_10m INTEGER)"
        )
        conn.commit()
        conn.close()

    def _init_zmq(self):
        if not ZMQ_OK:
            return
        ctx = zmq.Context.instance()
        self.zmq_pub = ctx.socket(zmq.PUB)
        self.zmq_pub.setsockopt(zmq.LINGER, 0)
        self.zmq_pub.bind("tcp://127.0.0.1:5556")

    async def login(self):
        async with async_playwright() as p:
            self.context = await p.chromium.launch_persistent_context(
                user_data_dir="./auth_profile_target_site",
                headless=True,
                viewport={"width": 1280, "height": 720},
            )
            page = await self.context.new_page()
            await page.goto(self.target_url)
            await page.fill('input[name="email"]', self.credentials.get("email", ""))
            await page.fill('input[name="password"]', self.credentials.get("password", ""))
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")
            await self.context.close()

    async def monitor_and_capture(self):
        self._init_zmq()
        async with async_playwright() as p:
            self.context = await p.chromium.launch_persistent_context(
                user_data_dir="./auth_profile_target_site",
                headless=True,
            )
            page = await self.context.new_page()
            await page.goto(f"{self.target_url.rstrip('/')}/live-signals")
            print("[Surrogate] Monitoramento ativo. Aguardando sinais...")

            while True:
                try:
                    state_elements = await page.query_selector_all(".match-card, .stats-grid")
                    signal_button = await page.query_selector(".btn-enter, .signal-active-flag")
                    page_state = []
                    for el in state_elements:
                        text = await el.inner_text()
                        page_state.append(text.strip())
                    current_state_str = " | ".join(page_state)
                    has_signal = signal_button is not None

                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO external_ai_surrogate "
                        "(timestamp, target_site, page_state, signal_detected) VALUES (?, ?, ?, ?)",
                        (time.time(), self.target_url, current_state_str, has_signal),
                    )
                    conn.commit()
                    conn.close()

                    if has_signal and self.zmq_pub is not None:
                        payload = {
                            "source": "external_ai",
                            "state": current_state_str,
                            "signal": True,
                            "ts": time.time(),
                        }
                        self.zmq_pub.send_string(f"external_signal::{json.dumps(payload)}")
                        print("[Surrogate] SINAL CAPTURADO e publicado no ZMQ :5556")
                        await asyncio.sleep(60)

                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"[Surrogate] Erro no loop: {e}")
                    await asyncio.sleep(10)


if __name__ == "__main__":
    TARGET = "https://www.site-alvo-exemplo.com"
    CREDS = {"email": "seu_email@email.com", "password": "sua_senha"}
    agent = ExternalAIAgent(TARGET, CREDS)
    # asyncio.run(agent.login())
    asyncio.run(agent.monitor_and_capture())
