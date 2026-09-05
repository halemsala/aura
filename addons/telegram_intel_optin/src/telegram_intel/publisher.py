"""Publish helper — no-op unless enabled and not dry_run."""
from __future__ import annotations
from .config import TelegramIntelConfig

class TelegramPublisher:
    def __init__(self, cfg: TelegramIntelConfig | None = None):
        self.cfg = cfg or TelegramIntelConfig.from_env()

    def send_message(self, text: str) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "reason": "disabled", "side_effect": False}
        if self.cfg.dry_run:
            return {"ok": True, "reason": "dry_run", "preview": text[:500], "side_effect": False}
        if not self.cfg.token or not self.cfg.chat_id:
            return {"ok": False, "reason": "missing_token_or_chat_id", "side_effect": False}
        # Real HTTP only when explicitly enabled — operator installs httpx/requests in worker venv
        try:
            import urllib.request
            import json
            url = f"https://api.telegram.org/bot{self.cfg.token}/sendMessage"
            data = json.dumps({"chat_id": self.cfg.chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "reason": "sent", "side_effect": True, "response_len": len(body)}
        except Exception as e:
            return {"ok": False, "reason": f"send_failed:{e}", "side_effect": False}
