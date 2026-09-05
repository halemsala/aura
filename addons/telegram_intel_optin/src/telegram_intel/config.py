from __future__ import annotations
import os
from dataclasses import dataclass

def _b(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")

@dataclass(frozen=True)
class TelegramIntelConfig:
    enabled: bool
    token: str
    chat_id: str
    publish_paper_only: bool
    allow_scrape: bool
    scrape_allowlist: tuple[str, ...]
    max_per_hour: int
    dry_run: bool

    @staticmethod
    def from_env() -> "TelegramIntelConfig":
        allow = os.environ.get("AURA_TELEGRAM_SCRAPE_ALLOWLIST", "")
        urls = tuple(u.strip() for u in allow.split(",") if u.strip())
        return TelegramIntelConfig(
            enabled=_b("AURA_TELEGRAM_INTEL_ENABLED", False),
            token=os.environ.get("AURA_TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.environ.get("AURA_TELEGRAM_CHAT_ID", "").strip(),
            publish_paper_only=_b("AURA_TELEGRAM_PUBLISH_PAPER_ONLY", True),
            allow_scrape=_b("AURA_TELEGRAM_ALLOW_SCRAPE", False),
            scrape_allowlist=urls,
            max_per_hour=int(os.environ.get("AURA_TELEGRAM_MAX_REQUESTS_PER_HOUR", "20")),
            dry_run=_b("AURA_TELEGRAM_DRY_RUN", True),
        )

    def ready_to_publish(self) -> bool:
        return bool(self.enabled and self.token and self.chat_id and not self.dry_run)
