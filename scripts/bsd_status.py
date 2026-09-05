#!/usr/bin/env python3
"""Gera data/bsd_status.json para a interface consumir."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bridge.bsd_feed import BSDConfig, BSDFeed

STATUS = ROOT / "data" / "bsd_status.json"
DIV_REPORT = ROOT / "data" / "bsd_divergence_report.json"

def main():
    cfg = BSDConfig.load()
    feed = BSDFeed(cfg)
    live_count = 0
    err = None
    try:
        live = feed.get_live_events() if feed.enabled else []
        live_count = len(live)
    except Exception as e:
        err = str(e)

    div = {}
    if DIV_REPORT.exists():
        try:
            div = json.loads(DIV_REPORT.read_text(encoding="utf-8"))
        except Exception:
            pass

    status = {
        "enabled": cfg.enabled,
        "key_configured": bool(cfg.api_key),
        "role": "complementary",
        "primary_source": "sokkerpro",
        "live_events": live_count,
        "divergence": {
            "total_samples": div.get("total", 0),
            "corner_mismatches": div.get("corner_mismatches", 0),
            "mismatch_rate": div.get("mismatch_rate", 0),
        },
        "error": err,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "ui_hints": {
            "card_title": "BSD Complementary Feed",
            "card_status": "OK" if cfg.enabled and not err else "OFF/ERROR",
            "menu": "Configurações → Fontes de Dados → BSD",
        },
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
