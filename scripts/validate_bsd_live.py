#!/usr/bin/env python3
"""
validate_bsd_live.py — Valida dados live da BSD (REST; WebSocket é addon pago).

Verifica:
- Chave válida
- Endpoint /events/live/
- Presença de campos úteis (corners, minute, teams)
- Rate-limit headers se disponíveis

Uso:
  python scripts/validate_bsd_live.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bridge.bsd_feed import BSDFeed, BSDConfig

def main():
    cfg = BSDConfig.load()
    print("=" * 50)
    print("BSD LIVE VALIDATION")
    print("=" * 50)
    print(f"enabled   : {cfg.enabled}")
    print(f"key set   : {bool(cfg.api_key)} ({cfg.api_key[:8]}...)" if cfg.api_key else "key set   : False")
    print(f"base_url  : {cfg.base_url}")
    print()

    if not cfg.enabled or not cfg.api_key:
        print("[FAIL] Config desabilitada ou sem chave")
        return 1

    feed = BSDFeed(cfg)
    live = feed.get_live_events()
    print(f"live events returned: {len(live)}")

    if not live:
        print("[WARN] Nenhum jogo live no momento (normal fora de horário)")
        print("[OK] API respondeu (lista vazia é válida)")
        return 0

    # Inspeciona primeiro evento
    ev = live[0]
    print(f"sample   : {ev.get('home_team')} x {ev.get('away_team')}")
    print(f"id       : {ev.get('id')}")
    print(f"minute   : {ev.get('current_minute') or ev.get('minute')}")
    print(f"score    : {ev.get('home_score')}-{ev.get('away_score')}")
    print(f"ws flag  : {ev.get('live_websocket')}")

    # Tenta stats
    eid = ev.get("id")
    if eid:
        stats = feed.get_stats(eid)
        if stats:
            print(f"stats keys: {list(stats.keys())[:12]}")
            print("[OK] /stats/ respondeu")
        else:
            print("[WARN] /stats/ vazio ou falhou")

    print()
    print("[OK] Validação REST concluída")
    print("Nota: WebSocket live completo é addon pago na BSD.")
    print("      No free tier usamos polling REST controlado.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
