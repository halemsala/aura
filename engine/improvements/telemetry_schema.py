# Itens 12, 58 — schema canônico + clamp de ranges
from __future__ import annotations
from typing import Any, Dict, Tuple

SCHEMA_VERSION = "v1"

RANGES = {
    "dangerous": (0.0, 100.0),
    "xg": (0.0, 10.0),
    "goals": (0.0, 20.0),
    "corners": (0.0, 40.0),
}


def clamp_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, (lo, hi) in RANGES.items():
        block = stats.get(key) or {}
        out[key] = {
            "home": float(min(hi, max(lo, float(block.get("home", 0) or 0)))),
            "away": float(min(hi, max(lo, float(block.get("away", 0) or 0)))),
        }
    return out


def validate_payload(raw: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Retorna (ok, erro, payload_normalizado)."""
    p = raw.get("dados", raw)
    fid = p.get("fixtureId") or p.get("fixture_id")
    if not fid:
        return False, "fixtureId ausente", {}
    ver = p.get("schema_version", SCHEMA_VERSION)
    if ver not in (SCHEMA_VERSION, "1", 1, None):
        # aceita ausente; rejeita futuro incompatível
        if ver and str(ver) not in (SCHEMA_VERSION, "1"):
            return False, f"schema_version não suportada: {ver}", {}
    stats = clamp_stats(p.get("stats") or {})
    home = p.get("home") or (p.get("teams") or {}).get("home") or "Home"
    away = p.get("away") or (p.get("teams") or {}).get("away") or "Away"
    odds = p.get("odds")
    try:
        odds_f = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_f = None
    if odds_f is not None and (odds_f < 1.01 or odds_f > 50):
        odds_f = None
    norm = {
        "schema_version": SCHEMA_VERSION,
        "fixtureId": str(fid),
        "home": str(home),
        "away": str(away),
        "clock": p.get("clock") or p.get("minute") or "0'",
        "stats": stats,
        "odds": odds_f,
        "raw_keys": list(p.keys()),
    }
    return True, "", norm
